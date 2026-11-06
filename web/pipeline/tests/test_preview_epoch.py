from __future__ import annotations
import asyncio
import copy
import importlib
import os
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from collector_epoch import RuntimeCache, accepts_payload, epoch_key, preview_epoch, send

class Cache:
    def __init__(self):
        self.values = {}
        self.calls = []
    def get(self, key):
        self.calls.append(('get', key))
        return copy.deepcopy(self.values.get(key))
    def set(self, key, value, options=None):
        self.calls.append(('set', key, copy.deepcopy(options)))
        self.values[key] = copy.deepcopy(value)
    def delete(self, key):
        self.calls.append(('delete', key))
        self.values.pop(key, None)

class PreviewEpochTests(unittest.TestCase):
    def setUp(self):
        self.raw = Cache()
        f = types.ModuleType('vercel.functions')
        f.RuntimeCache = Mock(return_value=self.raw)
        q = types.ModuleType('vercel.queue')
        q.send = AsyncMock(return_value='queue-message')
        self.native_cache = f.RuntimeCache
        self.native_send = q.send
        self.stubs = patch.dict(sys.modules, {'vercel.functions': f, 'vercel.queue': q})
        self.stubs.start(); self.addCleanup(self.stubs.stop)
        self.env = patch.dict(os.environ, {'VERCEL_ENV':'preview','MCAI_PREVIEW_EPOCH':'cycle-a'})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_every_key_family_and_tags_are_isolated_from_old_and_other_epochs(self):
        families = ['collector-runtime-state', 'collector-active-cycle', 'collector-incremental-active',
                    'collector-incremental-chain', 'collector-regional-ln-records', 'collector-source-health',
                    'collector-incremental-ledger:teda', 'collector-incremental-bucket:teda',
                    'collector-incremental-pending:teda', 'collector-incremental-pending-barrier:teda',
                    'verified-snapshot:published']
        a = RuntimeCache()
        for key in families:
            self.raw.set(key, 'legacy')
            self.assertIsNone(a.get(key))
            options = {'ttl':60,'tags':['shared-tag']}
            a.set(key, {'epoch':'a'}, options)
            self.assertEqual(options['tags'], ['shared-tag'])
            self.assertEqual(self.raw.values[key], 'legacy')
        with patch.dict(os.environ, {'MCAI_PREVIEW_EPOCH':'cycle-b'}):
            b = RuntimeCache()
            for key in families:
                self.assertIsNone(b.get(key))
                b.set(key, 'b')
                b.delete(key)
                self.assertEqual(a.get(key), {'epoch':'a'})
        a.delete(families[0])
        self.assertEqual(self.raw.values[families[0]], 'legacy')
        self.assertTrue(any(c[0]=='set' and c[2] and c[2]['tags']==[epoch_key('shared-tag','cycle-a')] for c in self.raw.calls))

    def test_production_and_legacy_preview_keep_original_keys(self):
        for env in ({'VERCEL_ENV':'production','MCAI_PREVIEW_EPOCH':'invalid/ignored'},
                    {'VERCEL_ENV':'preview','MCAI_PREVIEW_EPOCH':''},
                    {'VERCEL_ENV':'development','MCAI_PREVIEW_EPOCH':'cycle-a'}):
            with patch.dict(os.environ, env):
                self.assertIsNone(preview_epoch())
                self.assertIs(RuntimeCache(), self.raw)
                self.assertTrue(accepts_payload({'schema_version':'0.1'}))
                self.assertFalse(accepts_payload({'preview_epoch':'cycle-a'}))

    def test_invalid_preview_epoch_fails_before_cache_or_enqueue(self):
        for value in ('../legacy','A','x'*49):
            with patch.dict(os.environ, {'MCAI_PREVIEW_EPOCH':value}):
                with self.assertRaisesRegex(ValueError, 'PREVIEW_EPOCH_INVALID'):RuntimeCache()
                with self.assertRaisesRegex(ValueError, 'PREVIEW_EPOCH_INVALID'):asyncio.run(send('topic',{}))
        self.native_cache.assert_not_called();self.native_send.assert_not_awaited()

    def test_send_labels_payload_and_idempotency_without_changing_input(self):
        payload={'schema_version':'0.1','mode':'incremental_tick'}
        asyncio.run(send('topic',payload,idempotency_key='tick:1',delay=7))
        args,options=self.native_send.call_args
        self.assertEqual(args,('topic',{**payload,'preview_epoch':'cycle-a'}))
        self.assertEqual(payload,{'schema_version':'0.1','mode':'incremental_tick'})
        self.assertEqual(options,{'idempotency_key':epoch_key('tick:1','cycle-a'),'delay':7})
        with self.assertRaisesRegex(ValueError,'PREVIEW_QUEUE_EPOCH_MISMATCH'):
            asyncio.run(send('topic',{'preview_epoch':'cycle-b'}))
        with patch.dict(os.environ,{'VERCEL_ENV':'production'}):
            asyncio.run(send('topic',payload,idempotency_key='prod'))
        self.assertEqual(self.native_send.call_args.kwargs['idempotency_key'],'prod')

    def test_foreign_messages_never_touch_runtime_or_mutation_lease(self):
        sys.modules.pop('collector_queue', None)
        worker=importlib.import_module('collector_queue')
        # Capture the actual producer's complete tick envelope before changing
        # only the epoch, so rejection cannot be explained by malformed fields.
        before_window = datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)
        scheduled = worker.first_tick_after_deep(before_window)
        asyncio.run(worker._enqueue_incremental_tick(scheduled, now=before_window))
        valid = copy.deepcopy(self.native_send.call_args.args[1])
        legacy = {key:value for key,value in valid.items() if key != 'preview_epoch'}
        payloads=[legacy, {**valid, 'preview_epoch':'cycle-b'},
                  {'schema_version':'0.1','mode':'incremental','preview_epoch':'cycle-b'},
                  {'schema_version':'0.1','stage':'publish','preview_epoch':'cycle-old'}]
        with patch.object(worker,'RuntimeCache',side_effect=AssertionError('cache touched')), patch.object(
            worker,'recover_expired_deep_cycle',side_effect=AssertionError('lease touched')), patch.object(
            worker,'_process_incremental_tick_payload',new_callable=AsyncMock) as tick:
            for payload in payloads:asyncio.run(worker.process_collector_payload(payload))
            tick.assert_not_awaited()
            asyncio.run(worker.process_collector_payload(valid))
            tick.assert_awaited_once()
