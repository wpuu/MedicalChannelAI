from __future__ import annotations

import asyncio
import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from test_collector_native_reliability import MemoryCache, runtime, queue
from collector_namespace import ACTIVE_CYCLE_KEY, META_KEY, deep_message_lease_disposition
from collector_schedule import SCHEDULE_VERSION, scheduled_cycle, valid_cycle, running_stage_is_live

WEB = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('scheduled_start', WEB / 'api/collector-run.py')
start = importlib.util.module_from_spec(spec)
spec.loader.exec_module(start)

MORNING = datetime(2026, 10, 3, 0, 43, tzinfo=timezone.utc)
NOON = datetime(2026, 10, 3, 4, 51, tzinfo=timezone.utc)


class TwiceDailySearchTests(unittest.TestCase):
    def setUp(self):
        self.clock_patch = patch.object(queue, 'datetime')
        clock = self.clock_patch.start()
        clock.now.return_value = MORNING
        clock.fromisoformat.side_effect = datetime.fromisoformat
        self.addCleanup(self.clock_patch.stop)
        self.cache = MemoryCache()
        self.mid, self.ma = scheduled_cycle(MORNING, 'morning')
        self.nid, self.na = scheduled_cycle(NOON, 'noon')

    def lease(self, cycle_id, anchor):
        self.cache.set(ACTIVE_CYCLE_KEY, {'cycle_id': cycle_id, 'cycle_as_of': anchor.isoformat()})

    def test_two_separate_daily_crons_and_deployment_disabled(self):
        config = json.loads((WEB / 'vercel.json').read_text())
        self.assertEqual(config['crons'], [
            {'path': '/api/collector-run?period=morning', 'schedule': '20 0 * * *'},
            {'path': '/api/collector-run?period=noon', 'schedule': '20 4 * * *'},
        ])
        self.assertIs(config['git']['deploymentEnabled']['fix/tjmugh-verification-20261002'], False)

    def test_hourly_jitter_has_stable_named_identity(self):
        for delta in (-20, 0, 59):
            when = MORNING.replace(minute=20) + timedelta(minutes=delta)
            cid, anchor = scheduled_cycle(when, 'morning')
            self.assertEqual(cid, self.mid)
            self.assertEqual(anchor, when)
            self.assertTrue(valid_cycle(cid, anchor))

    def test_early_hour_never_forges_future_snapshot_time(self):
        now = MORNING.replace(minute=1)
        _, anchor = scheduled_cycle(now, 'morning')
        self.assertLessEqual(anchor, now)

    def test_period_missing_unknown_and_naive_are_rejected(self):
        for period in ('', 'night', 'noon'):
            with self.assertRaises(ValueError):
                scheduled_cycle(MORNING, period)
        with self.assertRaises(ValueError):
            scheduled_cycle(MORNING.replace(tzinfo=None), 'morning')

    def test_late_morning_trigger_is_rejected_at_noon(self):
        with self.assertRaises(ValueError):
            scheduled_cycle(NOON, 'morning')

    def test_noon_and_next_day_get_distinct_ids(self):
        self.assertNotEqual(self.mid, self.nid)
        self.assertNotEqual(self.mid, scheduled_cycle(MORNING + timedelta(days=1), 'morning')[0])

    def test_cycle_payload_period_must_match_time(self):
        self.assertFalse(valid_cycle(self.mid, NOON))
        self.assertFalse(valid_cycle('prod:2026-10-03', MORNING))
        self.assertFalse(valid_cycle(self.mid, MORNING.replace(tzinfo=None)))

    def test_same_period_start_retry_preserves_first_clock_and_key(self):
        sent = AsyncMock(return_value='offline-id')
        with patch.object(start, 'RuntimeCache', return_value=self.cache), patch.object(start, 'send', sent), patch.object(start, 'datetime') as clock:
            clock.now.return_value = MORNING
            clock.fromisoformat.side_effect = datetime.fromisoformat
            first = asyncio.run(start._enqueue_start('OFFLINE', 'morning'))
            clock.now.return_value = MORNING + timedelta(minutes=5)
            second = asyncio.run(start._enqueue_start('OFFLINE', 'morning'))
        self.assertEqual(first[2], second[2])
        self.assertEqual(sent.await_args_list[0].kwargs['idempotency_key'], sent.await_args_list[1].kwargs['idempotency_key'])
        self.assertEqual(sent.await_args_list[0].args[1]['cycle_as_of'], sent.await_args_list[1].args[1]['cycle_as_of'])
        self.assertEqual(sent.await_args.args[1]['schedule_version'], SCHEDULE_VERSION)

    def test_completed_period_trigger_does_not_send_again(self):
        self.cache.set(META_KEY, {'cycle_id': self.mid, 'cycle_as_of': self.ma.isoformat(), 'stages': {'publish': {'status': 'COMPLETED'}}})
        with patch.object(start, 'RuntimeCache', return_value=self.cache), patch.object(start, 'send', new_callable=AsyncMock) as send, patch.object(start, 'datetime') as clock:
            clock.now.return_value = MORNING
            clock.fromisoformat.side_effect = datetime.fromisoformat
            result = asyncio.run(start._enqueue_start('OFFLINE', 'morning'))
        self.assertEqual(result[0], 'ALREADY_ENDED')
        send.assert_not_awaited()

    def test_noon_starts_after_morning_completion(self):
        self.cache.set(META_KEY, {'cycle_id': self.mid, 'cycle_as_of': self.ma.isoformat(), 'stages': {'publish': {'status': 'COMPLETED'}}})
        with patch.object(start, 'RuntimeCache', return_value=self.cache), patch.object(start, 'send', new_callable=AsyncMock) as send, patch.object(start, 'datetime') as clock:
            clock.now.return_value = NOON
            clock.fromisoformat.side_effect = datetime.fromisoformat
            result = asyncio.run(start._enqueue_start('OFFLINE', 'noon'))
        self.assertEqual(result[2], self.nid)
        send.assert_awaited_once()

    def test_noon_runtime_does_not_reuse_completed_morning(self):
        self.lease(self.mid, self.ma)
        with patch.object(runtime, 'RuntimeCache', return_value=self.cache), patch.object(runtime, '_run_ccgp', return_value={'ok': True}) as run:
            first = runtime.run_stage('ccgp', now=self.ma, cycle_id=self.mid)
            again = runtime.run_stage('ccgp', now=self.ma, cycle_id=self.mid)
            self.lease(self.nid, self.na)
            noon = runtime.run_stage('ccgp', now=self.na, cycle_id=self.nid)
        self.assertEqual(first[1]['action'], 'COMPLETED')
        self.assertEqual(again[1]['action'], 'ALREADY_COMPLETED_TODAY')
        self.assertEqual(noon[1]['action'], 'COMPLETED')
        self.assertEqual(run.call_count, 2)
        self.assertEqual(self.cache.get(META_KEY)['cycle_id'], self.nid)

    def test_same_stage_live_duplicate_does_not_run(self):
        self.lease(self.mid, self.ma)
        self.cache.set(META_KEY, {'local_date': '2026-10-03', 'cycle_id': self.mid, 'stages': {'ccgp': {'status': 'RUNNING', 'started_at': MORNING.isoformat()}}})
        with patch.object(runtime, 'RuntimeCache', return_value=self.cache), patch.object(runtime, '_now_utc', return_value=MORNING + timedelta(seconds=10)), patch.object(runtime, '_run_ccgp') as run:
            result = runtime.run_stage('ccgp', now=self.ma, cycle_id=self.mid)
        self.assertEqual(result[0], 409)
        run.assert_not_called()

    def test_running_lease_uses_wall_clock(self):
        self.lease(self.mid, self.ma)
        wall = self.ma + timedelta(hours=1)
        with patch.object(runtime, 'RuntimeCache', return_value=self.cache), patch.object(runtime, '_now_utc', return_value=wall), patch.object(runtime, '_run_ccgp', return_value={}):
            runtime.run_stage('ccgp', now=self.ma, cycle_id=self.mid)
        self.assertEqual(self.cache.get(META_KEY)['stages']['ccgp']['started_at'], wall.isoformat())

    def test_old_same_day_message_is_superseded_without_active_lease(self):
        state = {'local_date': '2026-10-03', 'cycle_id': self.nid, 'stages': {'publish': {'status': 'COMPLETED'}}}
        self.assertEqual(deep_message_lease_disposition(None, state, cycle_id=self.mid, cycle_local_date='2026-10-03', current_local_date='2026-10-03'), 'SUPERSEDED')

    def test_old_stage_cannot_write_canonical_after_lease_changes(self):
        self.lease(self.nid, self.na)
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            with self.assertRaisesRegex(runtime.CollectorPrecondition, 'SUPERSEDED'):
                runtime._cache_set(self.cache, runtime.CCGP_RECORDS_KEY, [{'old': True}], tag='offline')
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)
        self.assertIsNone(self.cache.get(runtime.CCGP_RECORDS_KEY))

    def test_old_stage_completion_cannot_overwrite_noon_status(self):
        self.cache.set(META_KEY, {'local_date': '2026-10-03', 'cycle_id': self.nid, 'stages': {}})
        with self.assertRaises(runtime.CollectorPrecondition):
            runtime._mark_completed(self.cache, {'local_date': '2026-10-03', 'cycle_id': self.mid}, 'ccgp', {})
        self.assertEqual(self.cache.get(META_KEY)['cycle_id'], self.nid)

    def test_all_cache_evicted_cannot_bootstrap_old_seed(self):
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            bootstrap = unittest.mock.Mock(return_value=[{'old': True}])
            with self.assertRaisesRegex(runtime.CollectorPrecondition, 'HISTORY_UNAVAILABLE'):
                runtime._cached_list(self.cache, runtime.CCGP_RECORDS_KEY, bootstrap)
            bootstrap.assert_not_called()
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)

    def test_canonical_present_empty_is_valid_and_no_bootstrap(self):
        self.cache.set(runtime.CCGP_RECORDS_KEY, [])
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            self.assertEqual(runtime._cached_list(self.cache, runtime.CCGP_RECORDS_KEY, lambda: self.fail('seed used')), ([], False))
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)

    def test_stale_running_recoverable_but_live_and_malformed_block(self):
        for age, live in ((359, True), (360, False), (86400 * 30, False), (-1, True)):
            state = {'stages': {'ccgp': {'status': 'RUNNING', 'started_at': (NOON - timedelta(seconds=age)).isoformat()}}}
            self.assertEqual(running_stage_is_live(state, NOON), live)
        self.assertTrue(running_stage_is_live({'stages': {'ccgp': {'status': 'RUNNING'}}}, NOON))

    def test_long_pause_start_replaces_stale_running_without_seed(self):
        old = MORNING - timedelta(days=30)
        self.cache.set(META_KEY, {'cycle_id': 'old', 'cycle_as_of': old.isoformat(), 'stages': {'ccgp': {'status': 'RUNNING', 'started_at': old.isoformat()}}})
        self.cache.set(ACTIVE_CYCLE_KEY, {'cycle_id': 'old', 'cycle_as_of': old.isoformat()})
        with patch.object(start, 'RuntimeCache', return_value=self.cache), patch.object(start, 'send', new_callable=AsyncMock), patch.object(start, 'datetime') as clock:
            clock.now.return_value = MORNING
            clock.fromisoformat.side_effect = datetime.fromisoformat
            result = asyncio.run(start._enqueue_start('OFFLINE', 'morning'))
        self.assertEqual(result[2], self.mid)
        self.assertIsNone(self.cache.get(runtime.CCGP_RECORDS_KEY))

    def test_old_backlog_and_all_incremental_modes_are_acknowledged_without_work(self):
        payloads = [
            {'schema_version': '0.1', 'stage': 'ccgp', 'cycle_id': 'prod:2026-10-03', 'cycle_as_of': MORNING.isoformat()},
            *[{'schema_version': '0.1', 'schedule_version': SCHEDULE_VERSION, 'mode': mode} for mode in ('incremental', 'incremental_tick')],
            {'schema_version': '0.1', 'schedule_version': SCHEDULE_VERSION, 'stage': 'ccgp', 'cycle_id': self.mid, 'cycle_as_of': NOON.isoformat()},
        ]
        with patch.object(runtime, 'run_stage') as run, patch.object(queue, 'send', new_callable=AsyncMock) as send:
            for payload in payloads:
                asyncio.run(queue.process_collector_payload(payload))
        run.assert_not_called()
        send.assert_not_awaited()

    def test_complete_and_degraded_publish_never_start_incremental_chain(self):
        payload = {'schema_version': '0.1', 'schedule_version': SCHEDULE_VERSION, 'stage': 'publish', 'cycle_id': self.mid, 'cycle_as_of': self.ma.isoformat()}
        for status, result in ((200, {'action': 'COMPLETED'}), (409, {'action': 'BLOCKED', 'terminal': True})):
            with patch.object(queue, '_active_cycle_matches', return_value=True), patch.object(runtime, 'run_stage', return_value=(status, result)), patch.object(queue, '_start_intraday_chain_after_deep', new_callable=AsyncMock) as chain, patch.object(queue, '_release_active_cycle_if_owned') as release, patch.object(queue.incremental_runtime, 'clear_incremental_pending') as clear:
                asyncio.run(queue.process_collector_payload(payload))
            chain.assert_not_awaited()
            release.assert_called_once_with(self.mid)
            self.assertEqual(clear.call_count, int(status == 200))

    def test_push_dispatcher_serial_cap_and_lease_exceed_function_duration(self):
        config = json.loads((WEB / 'vercel.json').read_text())
        function = config['functions']['api/collector-queue.py']
        trigger = function['experimentalTriggers'][0]
        self.assertEqual(trigger['maxConcurrency'], 1)
        self.assertEqual(trigger['maxDeliveries'], 3)
        self.assertGreater(trigger['retryAfterSeconds'], function['maxDuration'])
        source = (WEB / 'api/collector-queue.py').read_text()
        self.assertIn('lease_duration=360', source)
        self.assertIn('retry_after=360', source)

    def test_accepted_duplicate_key_is_success_and_other_send_errors_propagate(self):
        duplicate = type('DuplicateIdempotencyKeyError', (Exception,), {})
        with patch.object(start, 'RuntimeCache', return_value=self.cache), patch.object(start, 'send', new_callable=AsyncMock) as send, patch.object(start, 'datetime') as clock:
            clock.now.return_value = MORNING
            clock.fromisoformat.side_effect = datetime.fromisoformat
            send.side_effect = duplicate()
            result = asyncio.run(start._enqueue_start('OFFLINE', 'morning'))
            self.assertEqual(result[0], 'ALREADY_QUEUED')
            send.side_effect = RuntimeError('OFFLINE_SEND_ERROR')
            with self.assertRaisesRegex(RuntimeError, 'OFFLINE_SEND_ERROR'):
                asyncio.run(start._enqueue_start('OFFLINE', 'morning'))
        with patch.object(queue, 'send', new_callable=AsyncMock) as send:
            send.side_effect = duplicate()
            result = asyncio.run(queue._enqueue_stage(stage='event1', cycle_as_of=self.ma, cycle_id=self.mid))
            self.assertEqual(result, 'ALREADY_QUEUED')

    def test_old_day_even_matching_active_lease_does_not_run(self):
        payload = {'schema_version': '0.1', 'schedule_version': SCHEDULE_VERSION, 'stage': 'ccgp', 'cycle_id': self.mid, 'cycle_as_of': self.ma.isoformat()}
        with patch.object(queue, 'datetime') as clock, patch.object(queue, '_active_cycle_matches', return_value=True), patch.object(runtime, 'run_stage') as run:
            clock.now.return_value = MORNING + timedelta(days=1)
            clock.fromisoformat.side_effect = datetime.fromisoformat
            asyncio.run(queue.process_collector_payload(payload))
        run.assert_not_called()

    def _publish_cache_and_state(self):
        self.lease(self.mid, self.ma)
        for key in (runtime.CCGP_RECORDS_KEY, runtime.CCGP_EVENTS_KEY,
                    runtime.TJMUGH_RECORDS_KEY, runtime.TJNOTHOP_RECORDS_KEY,
                    runtime.TEDA_RECORDS_KEY, runtime.TJFCH_RECORDS_KEY):
            self.cache.set(key, [])
        for code in runtime.REGIONAL_STAGE_MARKET_CODES.values():
            self.cache.set(runtime._regional_records_key(code), [])
        for key in runtime.PRESERVED_SOURCE_RECORDS_KEYS.values():
            self.cache.set(key, [])
        return {'cycle_as_of': self.ma.isoformat(), 'stages': {
            stage: {'status': 'COMPLETED', 'terminal': True, 'result': {'fallback_required': False}}
            for stage in runtime.STAGE_ORDER if stage != 'publish'
        }}

    def _baseline(self, ids):
        return {'snapshot_as_of': '2026-10-02T14:19:15.713282+08:00',
                'opportunity_pool': [{'opportunity_id': oid} for oid in ids],
                'opportunity_pool_count': len(ids), 'cards': []}

    def test_missing_published_baseline_prevents_durable_and_cache_publish(self):
        state = self._publish_cache_and_state()
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            with patch.object(runtime, '_persist_verified_snapshot_durably') as publish, patch.object(runtime, 'build_public_snapshot') as build:
                with self.assertRaisesRegex(runtime.CollectorPrecondition, 'BASELINE_UNAVAILABLE'):
                    runtime._run_publish(self.cache, state)
                publish.assert_not_called()
                build.assert_not_called()
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)

    def test_missing_historical_id_beyond_top_cards_blocks_without_overwrite(self):
        state = self._publish_cache_and_state()
        baseline = self._baseline(['known', 'outside-configured-shards'])
        baseline['cards'] = baseline['opportunity_pool'][:1]
        self.cache.set(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY, baseline)
        self.cache.set(runtime.LATEST_RUNTIME_SNAPSHOT_KEY, baseline)
        self.cache.set(runtime.CCGP_RECORDS_KEY, [{'opportunity_id': 'known'}])
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            with patch.object(runtime, '_persist_verified_snapshot_durably') as publish, patch.object(runtime, 'build_public_snapshot') as build:
                with self.assertRaisesRegex(runtime.CollectorPrecondition, 'PUBLISHED_HISTORY_MISSING'):
                    runtime._run_publish(self.cache, state)
                publish.assert_not_called()
                build.assert_not_called()
            self.assertEqual(self.cache.get(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY), baseline)
            self.assertEqual(self.cache.get(runtime.LATEST_RUNTIME_SNAPSHOT_KEY), baseline)
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)

    def test_baseline_cannot_fallback_to_top_cards_or_filter_bad_pool_entries(self):
        invalid = [
            {'snapshot_as_of': self.ma.isoformat(), 'cards': [], 'opportunity_pool_count': 0},
            {**self._baseline([]), 'opportunity_pool': [None], 'opportunity_pool_count': 1},
            {**self._baseline(['']), 'opportunity_pool_count': 1},
            self._baseline(['duplicate', 'duplicate']),
            {**self._baseline(['known']), 'opportunity_pool_count': True},
            {**self._baseline(['known']), 'opportunity_pool_count': 441},
            {**self._baseline(['known']), 'opportunity_pool': 'not-a-list'},
        ]
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            for baseline in invalid:
                self.cache.set(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY, baseline)
                with self.assertRaisesRegex(runtime.CollectorPrecondition, 'BASELINE_INVALID'):
                    runtime._require_published_canonical_history(self.cache, [{'opportunity_id': 'known'}], as_of=self.ma)
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)

    def test_published_baseline_clock_must_be_known_aware_and_not_newer(self):
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            for clock in (None, 'not-time', '2026-10-02T14:19:15', self.na.isoformat()):
                self.cache.set(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY, {**self._baseline([]), 'snapshot_as_of': clock})
                with self.assertRaisesRegex(runtime.CollectorPrecondition, 'BASELINE_INVALID'):
                    runtime._require_published_canonical_history(self.cache, [], as_of=self.ma)
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)

    def test_canonical_retains_expired_history_even_if_new_pool_excludes_it(self):
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            self.cache.set(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY, self._baseline(['now-expired']))
            records = [{'opportunity_id': 'now-expired'}, {'opportunity_id': 'new-fact'}]
            runtime._require_published_canonical_history(self.cache, records, as_of=self.ma)
            self.assertEqual(records, [{'opportunity_id': 'now-expired'}, {'opportunity_id': 'new-fact'}])
            self.cache.set(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY, self._baseline([]))
            runtime._require_published_canonical_history(self.cache, [], as_of=self.ma)
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)

    def _real_history(self):
        files = ['ccgp', 'tjmugh', 'tjnothop', 'tjzxfc', 'tjzyefy',
                 'tjzyefy_intent', 'teda', 'tjfch']
        local = {name: json.loads((runtime.DATA_ROOT / f'tianjin_live_{name}_records.json').read_text())
                 for name in files}
        regional = json.loads((runtime.DATA_ROOT / 'regional_live_ccgp_records.json').read_text())
        return local, regional

    def test_preserved_history_requires_real_separate_valid_shards_without_bootstrap(self):
        local, _ = self._real_history()
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            for source, key in runtime.PRESERVED_SOURCE_RECORDS_KEYS.items():
                with self.assertRaisesRegex(runtime.CollectorPrecondition, 'HISTORY_UNAVAILABLE'):
                    runtime._preserved_source_history(self.cache)
                self.cache.set(key, local[source.replace('-', '_')])
            self.assertEqual(len(runtime._preserved_source_history(self.cache)), 8)
            key = runtime.PRESERVED_SOURCE_RECORDS_KEYS['tjzyefy']
            for invalid in ([None], local['tjzyefy_intent'], {}):
                self.cache.set(key, invalid)
                with self.assertRaisesRegex(runtime.CollectorPrecondition, 'HISTORY_(INVALID|UNAVAILABLE)'):
                    runtime._preserved_source_history(self.cache)
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)

    def test_scheduled_projection_matches_real_static_cards_without_changing_canonical(self):
        local, regional = self._real_history()
        records = [row for rows in local.values() for row in rows]
        before = json.dumps([records, regional], sort_keys=True)
        baseline = json.loads((WEB / 'public/data/today-actions.public.json').read_text())
        clock = datetime.fromisoformat(baseline['snapshot_as_of'])
        events = json.loads((runtime.DATA_ROOT / 'tianjin_notice_events.json').read_text())
        rebuilt = runtime._build_scheduled_public_snapshot(records, regional, clock, events)
        self.assertEqual(rebuilt['opportunity_pool'], baseline['opportunity_pool'])
        self.assertEqual(json.dumps([records, regional], sort_keys=True), before)
        self.assertTrue(all(row['facts']['market_code'] for row in rebuilt['opportunity_pool']))

    def test_scheduled_projection_rejects_cross_shard_duplicate_and_wrong_market(self):
        local, regional = self._real_history()
        row = local['tjzyefy_intent'][0]
        with self.assertRaisesRegex(runtime.CollectorPrecondition, 'ID_CONFLICT'):
            runtime._build_scheduled_public_snapshot([row], [row], self.ma, [])
        with self.assertRaisesRegex(runtime.CollectorPrecondition, 'MARKET_MISMATCH'):
            runtime._build_scheduled_public_snapshot([regional[0]], [], self.ma, [])
        broken = json.loads(json.dumps(regional[:1]))
        broken[0]['facts'].pop('market_code')
        with self.assertRaisesRegex(runtime.CollectorPrecondition, 'MARKET_MISMATCH'):
            runtime._build_scheduled_public_snapshot([], broken, self.ma, [])

    def test_known_tianjin_history_null_market_metadata_is_normalized_only_in_copy(self):
        local, _ = self._real_history()
        for missing in (None, '', '   '):
            row = json.loads(json.dumps(local['tjzyefy_intent'][0]))
            for field in ('market_code', 'market_name', 'market_admin_code'):
                row['facts'][field] = missing
            rebuilt = runtime._build_scheduled_public_snapshot([row], [], self.ma, [])
            facts = rebuilt['opportunity_pool'][0]['facts']
            self.assertEqual((facts['market_code'], facts['market_name'], facts['market_admin_code']), ('TJ', '天津', '120000'))
            self.assertIs(row['facts']['market_code'], missing)
        row['facts']['market_name'] = '北京'
        with self.assertRaisesRegex(ValueError, 'MARKET_NAME_MISMATCH'):
            runtime._build_scheduled_public_snapshot([row], [], self.ma, [])

    def test_real_history_publish_retains_intents_but_does_not_claim_refreshed_coverage(self):
        state = self._publish_cache_and_state()
        local, regional = self._real_history()
        for name, key in [('ccgp', runtime.CCGP_RECORDS_KEY), ('tjmugh', runtime.TJMUGH_RECORDS_KEY),
                          ('tjnothop', runtime.TJNOTHOP_RECORDS_KEY), ('teda', runtime.TEDA_RECORDS_KEY),
                          ('tjfch', runtime.TJFCH_RECORDS_KEY)]:
            self.cache.set(key, local[name])
        for source, key in runtime.PRESERVED_SOURCE_RECORDS_KEYS.items():
            self.cache.set(key, local[source.replace('-', '_')])
        for code in runtime.REGIONAL_STAGE_MARKET_CODES.values():
            self.cache.set(runtime._regional_records_key(code), [row for row in regional if row['facts']['market_code'] == code])
        baseline = json.loads((WEB / 'public/data/today-actions.public.json').read_text())
        self.cache.set(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY, baseline)
        token = runtime._SCHEDULED_CYCLE.set(self.mid)
        try:
            with patch.object(runtime, '_persist_verified_snapshot_durably', return_value={'snapshot_as_of': self.ma.isoformat()}):
                result = runtime._run_publish(self.cache, state)
            self.assertEqual(result['canonical_record_count'], 911)
            published = self.cache.get(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY)
            ids = {row['opportunity_id'] for row in published['opportunity_pool']}
            self.assertTrue({row['opportunity_id'] for row in local['tjzyefy_intent']}.issubset(ids))
            self.assertIs(published['collection_coverage']['complete'], False)
            self.assertIsNone(published['collection_coverage']['last_complete_as_of'])
            self.assertEqual(published['collection_coverage']['history_only_source_ids'], list(runtime.PRESERVED_SOURCE_RECORDS_KEYS))
            self.assertEqual(published, self.cache.get(runtime.LATEST_RUNTIME_SNAPSHOT_KEY))
        finally:
            runtime._SCHEDULED_CYCLE.reset(token)
