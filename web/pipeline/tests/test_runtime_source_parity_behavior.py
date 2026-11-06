from __future__ import annotations

import copy
import importlib
import io
import json
import socket
import sys
import types
import unittest
import urllib.request
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return copy.deepcopy(self.values.get(key))

    def set(self, key, value, options=None):
        self.values[key] = copy.deepcopy(value)

    def delete(self, key):
        self.values.pop(key, None)


class RuntimeSourceParityBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.cache = MemoryCache()
        functions = types.ModuleType("vercel.functions")
        functions.RuntimeCache = lambda *args, **kwargs: self.cache
        stub = patch.dict(sys.modules, {"vercel": types.ModuleType("vercel"), "vercel.functions": functions})
        stub.start()
        self.addCleanup(stub.stop)
        for name in ("collector_runtime", "collector_incremental_runtime", "collector_incremental_bootstrap"):
            sys.modules.pop(name, None)
        self.runtime = importlib.import_module("collector_runtime")
        self.incremental = importlib.import_module("collector_incremental_runtime")
        self.scheduler = importlib.import_module("collector_incremental_scheduler")
        self.now = datetime(2026, 10, 1, 4, tzinfo=timezone.utc)
        self.state = {"cycle_as_of": self.now.isoformat(), "local_date": "2026-10-01", "stages": {}}
        sleep = patch.object(self.runtime.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        for owner, name in ((socket, 'socket'), (socket, 'create_connection'), (urllib.request, 'build_opener')):
            blocker = patch.object(owner, name, side_effect=AssertionError('NETWORK_OR_REAL_CLIENT_FORBIDDEN'))
            blocker.start()
            self.addCleanup(blocker.stop)

    def fixture(self, source):
        # Minimal synthetic HTML bodies, never captured live responses. Titles,
        # URLs and publication identities reuse the audited task/repo fixtures.
        if source == "tjzyefy":
            title = "院内调研公告（2026年23号）-肢体康复训练等医疗设备采购项目"
            url = "https://www.tjzyefy.com/system/2026/09/28/030199113.shtml"
            body = "天津中医药大学第二附属医院。我院拟对肢体康复训练进行院内调研。报名时间：2026年9月28日-2026年10月9日16:00。"
            published = "2026-09-28"
        elif source == "tjzyefy_intent":
            title = "采购意向公告（2026年42号）-肺功能仪等医疗设备采购项目"
            url = "https://www.tjzyefy.com/system/2026/08/04/030195986.shtml"
            body = "天津中医药大学第二附属医院。我院将于近期对天津中医药大学第二附属医院肺功能仪等医疗设备采购项目进行采购，欢迎各位有资质的供应商咨询。预计采购时间2026年8-9月。"
            published = "2026-08-04"
        else:
            title = "天津市中心妇产科医院 载玻片打号机采购项目市场调研邀请公告"
            url = "https://www.tjzxfc.cn/system/2026/07/08/030313811.shtml"
            body = "天津市中心妇产科医院。为进一步规范我院病理科标本标识管理，根据科室设备采购计划，我院拟开展病理科载玻片打号机采购项目院内论证工作，现面向社会公开邀请供应商参与本次市场调研。资料提交截止时间：2026年7月15日17:00。"
            published = "2026-07-08"
        index = f'<a href="{url}">{title}</a>'
        detail = f'<h1>{title}</h1><div>时间：{published} 10:05 发布人：设备科</div><p>{body}</p>'
        return index, detail, url

    def parse_fixture(self, source):
        index, detail, url = self.fixture(source)
        fetch_name = "fetch_tjzxfc_page_with_retry" if source == "tjzxfc" else "fetch_tjzyefy_page_with_retry"
        discovery_as_of = {"tjzyefy": self.now, "tjzyefy_intent": datetime(2026, 8, 5, tzinfo=timezone.utc),
                           "tjzxfc": datetime(2026, 7, 10, tzinfo=timezone.utc)}[source]
        with patch.object(self.runtime, fetch_name, side_effect=[index, detail]):
            candidates = self.incremental._DISCOVERY[source](discovery_as_of)
            self.assertEqual(len(candidates), 1)
            record = self.incremental._VERIFICATION[source](candidates[0], self.now.isoformat(), self.now)
        self.assertEqual(record["source"]["url"], url)
        return candidates[0], record

    def seed_all_canonical(self):
        r = self.runtime
        for key in (r.CCGP_RECORDS_KEY, r.CCGP_EVENTS_KEY, r.TJMUGH_RECORDS_KEY, r.TJNOTHOP_RECORDS_KEY,
                    r.TEDA_RECORDS_KEY, r.TJFCH_RECORDS_KEY, r.TJZYEFY_RECORDS_KEY,
                    r.TJZYEFY_INTENT_RECORDS_KEY, r.TJZXFC_RECORDS_KEY):
            self.cache.set(key, [])
        for market in r.REGIONAL_STAGE_MARKET_CODES.values():
            self.cache.set(r._regional_records_key(market), [])

    def publish(self):
        with patch.object(self.runtime, "_persist_verified_snapshot_durably", return_value={"snapshot_as_of": self.now.isoformat()}):
            result = self.runtime._run_publish(self.cache, self.state)
        return result, self.cache.get(self.runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY)

    def test_real_three_adapters_publish_positive_and_intent_with_distinct_identity(self):
        self.seed_all_canonical()
        expected = {}
        keys = []
        for source in ("tjzyefy", "tjzyefy_intent", "tjzxfc"):
            candidate, record = self.parse_fixture(source)
            _, key = self.incremental._existing_records(self.cache, source)
            keys.append(key)
            # Duplicate same-identity records still pass through canonical merge.
            self.cache.set(key, [record, record])
            expected[record["opportunity_id"]] = source
            if source == "tjzyefy":
                self.assertEqual(record["opportunity_id"], "tjzyefy_20260928_030199113")
                self.assertEqual(record["facts"]["registration_deadline"], "2026-10-09T16:00:00+08:00")
                self.assertEqual(record["facts"]["lifecycle_state"], "MARKET_RESEARCH")
            if source == "tjzyefy_intent":
                self.assertEqual(record["facts"]["lifecycle_state"], "PROCUREMENT_INTENT")
                self.assertIsNone(record["facts"]["registration_deadline"])
        self.assertEqual(len(set(keys)), 3)
        result, snapshot = self.publish()
        self.assertEqual(result["canonical_record_count"], 3)
        visible = {row["opportunity_id"]: row["source_id"] for row in snapshot["opportunity_pool"]}
        self.assertEqual(visible, {key: value for key, value in expected.items() if value != "tjzxfc"})
        # Historical hospital fixture has already closed by October. Its July
        # publish proves parity while preserving the real deadline boundary.
        with patch.object(self.runtime, "_persist_verified_snapshot_durably", return_value={}):
            self.runtime._run_publish(self.cache, {**self.state, "cycle_as_of": "2026-07-10T00:00:00+00:00"})
        historical = self.cache.get(self.runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY)
        self.assertIn("tjzxfc", {row["source_id"] for row in historical["opportunity_pool"]})
        self.assertEqual(len(snapshot["source_health"]["sources"]), 14)
        self.assertTrue(all(row["last_successful_scan_at"] is None for row in snapshot["source_health"]["sources"].values()))

    def test_tjzyefy_september30_data_security_is_not_a_fact_or_failure(self):
        html = '<a href="/system/2026/09/30/030199248.shtml">天津中医药大学第二附属医院数据安全服务项目调研公告</a>'
        with patch.object(self.runtime, "fetch_tjzyefy_page_with_retry", return_value=html):
            self.assertEqual(self.incremental._discover_tjzyefy(self.now), [])
            status, result = self.incremental.run_incremental_source("tjzyefy", now=self.now, cache=self.cache)
        self.assertEqual(status, 200)
        self.assertEqual(result["verification_failure_count"], 0)
        self.assertEqual(result["verified_record_count"], 0)

    def test_three_invalid_index_responses_preserve_canonical_pending_and_success_clock(self):
        for source in ("tjzyefy", "tjzyefy_intent", "tjzxfc"):
            with self.subTest(source=source):
                _, record = self.parse_fixture(source)
                _, key = self.incremental._existing_records(self.cache, source)
                self.cache.set(key, [record])
                prior = self.now - timedelta(hours=2)
                self.runtime.record_source_scan(self.cache, source, successful=True, attempted_at=prior)
                unresolved = record["source"]["url"]
                self.incremental._save_pending_barrier(self.cache, source, {unresolved})
                fetch = "fetch_tjzxfc_page_with_retry" if source == "tjzxfc" else "fetch_tjzyefy_page_with_retry"
                with patch.object(self.runtime, fetch, return_value='<title>访问验证</title><body>请开启JavaScript</body>'), patch.object(
                    self.incremental, "_publish_snapshot_if_ready") as publish:
                    status, result = self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
                self.assertEqual(status, 503)
                self.assertIn("INDEX_RESPONSE_INVALID", result["error"])
                self.assertEqual(self.cache.get(key), [record])
                self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), {unresolved})
                self.assertIsNone(self.cache.get(self.incremental._bucket_cache_key(source)))
                health = self.runtime.snapshot_source_health(self.cache)["sources"][source]
                self.assertEqual(health["last_successful_scan_at"], prior.isoformat())
                self.assertEqual(health["failure_reason"], "INDEX_SCAN_FAILED")
                publish.assert_not_called()

    def test_legitimate_zero_relevance_scans_can_complete_for_all_three_sources(self):
        html = '<a href="/system/2026/08/04/030195986.shtml">办公桌采购公告</a>'
        for source in ("tjzyefy", "tjzyefy_intent", "tjzxfc"):
            with self.subTest(source=source):
                fetch = "fetch_tjzxfc_page_with_retry" if source == "tjzxfc" else "fetch_tjzyefy_page_with_retry"
                with patch.object(self.runtime, fetch, return_value=html), patch.object(
                    self.incremental, "_publish_snapshot_if_ready", return_value=(False, None)):
                    status, result = self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
                self.assertEqual(status, 200)
                self.assertEqual(result["discovered_candidate_count"], 0)
                self.assertEqual(result["verification_failure_count"], 0)
                self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], self.now.isoformat())

    def test_deep_three_source_index_failures_cannot_become_completed_fresh_scans(self):
        for source in ("tjzyefy", "tjzyefy_intent", "tjzxfc"):
            with self.subTest(source=source):
                _, record = self.parse_fixture(source)
                _, key = self.incremental._existing_records(self.cache, source)
                self.cache.set(key, [record])
                prior = self.now - timedelta(hours=2)
                self.runtime.record_source_scan(self.cache, source, successful=True, attempted_at=prior)
                state = {**self.state, "stages": {source: {"status": "RUNNING", "attempt_count": 1}}}
                self.cache.set(self.runtime.META_KEY, state)
                fetch = "fetch_tjzxfc_page_with_retry" if source == "tjzxfc" else "fetch_tjzyefy_page_with_retry"
                with patch.object(self.runtime, "_prepare_stage", return_value=(state, None)), patch.object(
                    self.runtime, fetch, return_value='<div id="app"></div><script src="/app.js"></script>'), patch.object(
                    self.runtime, "_now_utc", return_value=self.now):
                    status, result = self.runtime.run_stage(source, now=self.now)
                self.assertEqual(status, 503)
                self.assertEqual(self.cache.get(self.runtime.META_KEY)["stages"][source]["status"], "FAILED")
                self.assertEqual(self.cache.get(key), [record])
                self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], prior.isoformat())

    def test_tjzxfc_nonmedical_is_explicit_nonfact_and_official_guards_remain(self):
        title = "天津市中心妇产科医院报告厅提升改造项目市场调研邀请公告"
        url = "https://www.tjzxfc.cn/system/2026/08/17/030331860.shtml"
        detail = f"<h1>{title}</h1><div>时间：2026-08-17</div><p>天津市中心妇产科医院报告厅提升改造项目市场调研，截止时间2026年8月24日17:00。</p>"
        with patch.object(self.runtime, "fetch_tjzxfc_page_with_retry", side_effect=[f'<a href="{url}">{title}</a>', detail]):
            candidate = self.incremental._discover_tjzxfc(datetime(2026, 8, 18, tzinfo=timezone.utc))[0]
            self.assertIsNone(self.incremental._verify_tjzxfc(candidate, self.now.isoformat(), self.now))
        candidate, record = self.parse_fixture("tjzxfc")
        with patch.object(self.runtime, "fetch_tjzxfc_page_with_retry", return_value=self.fixture("tjzxfc")[1].replace("2026-07-08", "2026-07-07")):
            with self.assertRaises(self.runtime.TjzxfcParseError):
                self.incremental._verify_tjzxfc(candidate, self.now.isoformat(), self.now)
        foreign = types.SimpleNamespace(title=candidate.title, published_at=candidate.published_at,
                                         detail_url="https://evil.example/system/2026/09/28/030199115.shtml")
        with patch.object(self.runtime, "fetch_tjzxfc_page_with_retry", return_value=self.fixture("tjzxfc")[1]):
            with self.assertRaises(self.runtime.TjzxfcParseError):
                self.incremental._verify_tjzxfc(foreign, self.now.isoformat(), self.now)

    def test_missing_any_new_canonical_fails_before_publish_without_seeding(self):
        for key in (self.runtime.TJZYEFY_RECORDS_KEY, self.runtime.TJZYEFY_INTENT_RECORDS_KEY, self.runtime.TJZXFC_RECORDS_KEY):
            self.seed_all_canonical()
            self.cache.delete(key)
            with patch.object(self.runtime, "_persist_verified_snapshot_durably") as durable:
                with self.assertRaisesRegex(self.runtime.CollectorPrecondition, "COLLECTOR_CANONICAL_STATE_INCOMPLETE"):
                    self.runtime._run_publish(self.cache, self.state)
            self.assertIsNone(self.cache.get(key))
            durable.assert_not_called()

    def test_new_sources_partial_failure_preserves_canonical_and_pending_barrier(self):
        for source in ("tjzyefy", "tjzyefy_intent", "tjzxfc"):
            with self.subTest(source=source):
                candidate, record = self.parse_fixture(source)
                _, key = self.incremental._existing_records(self.cache, source)
                self.cache.set(key, [])
                bad = types.SimpleNamespace(title=candidate.title, published_at=candidate.published_at,
                                            detail_url=candidate.detail_url.replace(".shtml", "1.shtml"))
                with patch.dict(self.incremental._DISCOVERY, {source: lambda now: [candidate, bad]}), patch.dict(
                    self.incremental._VERIFICATION, {source: lambda item, *args: record if item.detail_url == candidate.detail_url else (_ for _ in ()).throw(ValueError("DETAIL_CHANGED"))}
                ), patch.object(self.incremental, "_publish_snapshot_if_ready") as publish:
                    status, result = self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
                self.assertEqual(status, 503)
                self.assertEqual(self.cache.get(key), [])
                self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), {bad.detail_url})
                self.assertEqual(len(self.incremental._load_pending_records(self.cache, source)), 1)
                self.assertIsNone(self.cache.get(self.incremental._bucket_cache_key(source)))
                publish.assert_not_called()
                with patch.dict(self.incremental._DISCOVERY, {source: lambda now: [candidate]}), patch.dict(self.incremental._VERIFICATION, {source: lambda *args: record}):
                    with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "SOURCE_PENDING_VERIFICATION_BARRIER"):
                        self.runtime._run_early_signal_source(self.cache, self.state, source)
                self.assertEqual(self.cache.get(key), [])

    def test_retry_can_resolve_nonfact_barrier_and_commit_verified_sibling(self):
        source = "tjzxfc"
        candidate, record = self.parse_fixture(source)
        _, key = self.incremental._existing_records(self.cache, source)
        self.cache.set(key, [])
        nonfact = types.SimpleNamespace(title="报告厅改造市场调研公告", published_at="2026-09-28",
                                        detail_url="https://www.tjzxfc.cn/system/2026/09/28/030199999.shtml")
        self.incremental._save_pending_barrier(self.cache, source, {nonfact.detail_url})
        with patch.dict(self.incremental._DISCOVERY, {source: lambda now: [candidate, nonfact]}), patch.dict(
            self.incremental._VERIFICATION, {source: lambda item, *args: record if item.detail_url == candidate.detail_url else None}
        ), patch.object(self.incremental, "_publish_snapshot_if_ready", return_value=(False, None)):
            status, result = self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
        self.assertEqual(status, 200)
        self.assertEqual(result["verified_nonfact_count"], 1)
        self.assertEqual(len(self.cache.get(key)), 1)
        self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), set())

    def test_tjfch_sibling_pending_does_not_block_healthy_incremental_feed(self):
        candidate, record = self.parse_fixture("tjzyefy")
        for source, sibling in (("tjfch", "tjfch_test"), ("tjfch_test", "tjfch")):
            with self.subTest(source=source):
                self.cache = MemoryCache()
                self.cache.set(self.runtime.TJFCH_RECORDS_KEY, [])
                unresolved = "https://www.tj-fch.com/unresolved-sibling"
                self.incremental._save_pending_barrier(self.cache, sibling, {unresolved})
                with patch.dict(self.incremental._DISCOVERY, {source: lambda now: [candidate]}), patch.dict(
                    self.incremental._VERIFICATION, {source: lambda *args: record}
                ), patch.object(self.incremental, "_publish_snapshot_if_ready", return_value=(False, None)):
                    status, result = self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
                self.assertEqual(status, 200)
                self.assertEqual(len(self.cache.get(self.runtime.TJFCH_RECORDS_KEY)), 1)
                self.assertEqual(self.incremental._load_pending_barrier(self.cache, sibling), {unresolved})

    def test_deep_verified_nonfact_resolves_only_its_proven_barrier_after_commit(self):
        candidate, record = self.parse_fixture("tjzxfc")
        self.cache.set(self.runtime.TJZXFC_RECORDS_KEY, [])
        self.incremental._save_pending_barrier(self.cache, "tjzxfc", {candidate.detail_url})
        with patch.dict(self.incremental._DISCOVERY, {"tjzxfc": lambda now: [candidate]}), patch.dict(
            self.incremental._VERIFICATION, {"tjzxfc": lambda *args: None}
        ):
            result = self.runtime._run_early_signal_source(self.cache, self.state, "tjzxfc")
        self.assertEqual(result["unsupported_count"], 1)
        self.assertEqual(self.cache.get(self.runtime.TJZXFC_RECORDS_KEY), [])
        self.assertEqual(self.incremental._load_pending_barrier(self.cache, "tjzxfc"), set())

    def test_legacy_hospital_partial_failures_never_change_source_canonical(self):
        candidate, record = self.parse_fixture("tjzyefy")
        for source in ("tjmugh", "tjnothop"):
            with self.subTest(source=source), ExitStack() as patches:
                key = getattr(self.runtime, source.upper() + "_RECORDS_KEY")
                self.cache.set(key, [])
                bad = types.SimpleNamespace(title=candidate.title, published_at=candidate.published_at,
                                            detail_url=candidate.detail_url.replace(".shtml", "1.shtml"))
                patches.enter_context(patch.object(self.runtime, f"fetch_{source}_page", return_value="minimal synthetic HTML"))
                patches.enter_context(patch.object(self.runtime, f"parse_{source}_index_html", return_value=[candidate, bad]))
                patches.enter_context(patch.object(self.runtime, f"select_{source}_candidates", return_value=[candidate, bad]))
                patches.enter_context(patch.object(self.runtime, f"{source}_opportunity_id", return_value="fixture-id"))
                patches.enter_context(patch.object(self.runtime, f"parse_{source}_market_research", side_effect=[record, ValueError("DETAIL_CHANGED")]))
                with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "CANDIDATE_VERIFICATION_INCOMPLETE"):
                    getattr(self.runtime, f"_run_{source}")(self.cache, self.state)
                self.assertEqual(self.cache.get(key), [])

    def regional_budget_case(self, mode='success', *, stage='regional_he'):
        r = self.runtime
        corpus = WEB_ROOT / 'pipeline/tests/fixtures/ccgp_template_audit_20261106'
        case = next(c for c in json.loads((corpus / 'manifest.json').read_text())['cases'] if c['label'] == 'ccgp_he_2a9ca892bf9d0b6a')
        html = (corpus / case['file']).read_bytes().decode(case['encoding'])
        plan = r.load_regional_plan(r.DATA_ROOT / 'multi_region_query_plan.json')
        plan.update(keywords=['first', 'second'], notice_types=['公开招标'], delay_seconds=4)
        candidate = types.SimpleNamespace(title='医院医疗设备', region='河北', notice_type='公开招标',
            published_at='2026-09-08', buyer_name='医院', detail_url=case['url'])
        old = next(row for row in json.loads((r.DATA_ROOT / 'regional_live_ccgp_records.json').read_text())
                   if row['source']['url'] != case['url'] and row['facts'].get('market_code') == 'HE')
        key = r._regional_records_key('HE')
        self.cache.set(key, [old])
        prior = (self.now - timedelta(days=1)).isoformat()
        self.cache.set(r.SOURCE_HEALTH_KEY, {'schema_version':'0.1','sources':{'regional_he':{'last_successful_scan_at':prior}}})
        pending_key = 'medicalchannelai:collector-incremental-pending-barrier:tjzyefy:v2'
        self.cache.set(pending_key, ['unresolved'])
        ledger_key = 'medicalchannelai:collector-incremental-ledger:tjzyefy:v2'
        self.cache.set(ledger_key, {'entries':{'retained':{'verification_status':'UNVERIFIED'}}})
        before_ledger = self.cache.get(ledger_key)
        stages = {name:{'status':'COMPLETED'} for name in r.STAGE_ORDER[:r.STAGE_ORDER.index(stage)]}
        if stage.endswith('_fallback'):
            stages['regional_he']['result'] = {'fallback_required':True}
        self.cache.set(r.META_KEY, {**self.state, 'stages':stages})
        tick = [0.0]
        sleeps = []
        def sleep(delay):
            sleeps.append(delay)
            tick[0] = 210 if mode == 'sleep_overrun' else tick[0] + delay
        budget = r.CliBudget(lambda:tick[0], sleep, total_seconds=270, work_seconds=210, started_at=0)
        if mode in ('expired', 'margin'):
            tick[0] = 210 if mode == 'expired' else 209
        def discover(session, **kwargs):
            if mode == 'ordinary_error' and kwargs['keyword'] == 'second':
                raise TimeoutError('OFFLINE_TRANSIENT')
            if mode in ('search_late','failure_state_error'): tick[0] = 210
            if mode == 'sleep_admission': tick[0] = 206
            if mode == 'timeout_near' and kwargs['keyword'] == 'second': tick[0] = 200
            if mode == 'empty' or kwargs['page_index'] > 1:
                return []
            return [('公开招标', candidate)]
        def fetch(url, **kwargs):
            if mode == 'detail_late': tick[0] = 210
            return html
        adapter = r.VERIFIED_NOTICE_ADAPTERS['公开招标']
        def parse(*args, **kwargs):
            result = adapter(*args, **kwargs)
            if mode == 'parse_late': tick[0] = 210
            return result
        original_set = self.cache.set
        def cache_set(cache_key, value, options=None):
            if cache_key == r.META_KEY and mode == 'failure_state_error' and value['stages'][stage]['status'] == 'FAILED':
                raise OSError('OFFLINE_FAILURE_STATE_ERROR')
            if cache_key == key and mode == 'write_error_before':
                raise OSError('OFFLINE_WRITE_ERROR')
            if cache_key == r.SOURCE_HEALTH_KEY and mode == 'health_error':
                raise OSError('OFFLINE_HEALTH_ERROR')
            original_set(cache_key, value, options)
            if cache_key == key and mode == 'write_then_error':
                raise OSError('OFFLINE_WRITE_RESULT_UNKNOWN')
            if (cache_key == key and mode == 'commit_late') or (cache_key == r.SOURCE_HEALTH_KEY and mode == 'health_late'):
                tick[0] = 270
        original_check = budget.check
        def check(phase, **kwargs):
            if mode == 'precommit_late' and phase == 'REGIONAL_PRE_COMMIT': tick[0] = 270
            return original_check(phase, **kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch.object(r,'load_regional_plan',return_value=plan))
            session = stack.enter_context(patch.object(r,'RegionalCcgpSearchSession'))
            search = stack.enter_context(patch.object(r,'fetch_regional_candidates_page',side_effect=discover))
            detail = stack.enter_context(patch.object(r,'fetch_ccgp_detail_html',side_effect=fetch))
            parser = stack.enter_context(patch.dict(r.VERIFIED_NOTICE_ADAPTERS,{'公开招标':parse}))
            stack.enter_context(patch.object(self.cache,'set',side_effect=cache_set))
            stack.enter_context(patch.object(budget,'check',side_effect=check))
            stack.enter_context(patch.object(r,'_now_utc',return_value=self.now))
            error = None
            try:
                status, result = r.run_stage(stage, now=self.now, budget=budget)
            except r.CollectorStageBlocked as exc:
                status, result, error = None, {'diagnostics':exc.diagnostics}, str(exc)
            return {'status':status,'result':result,'error':error,'canonical':self.cache.get(key),'old':[old],
                    'stage':self.cache.get(r.META_KEY)['stages'][stage],
                    'health':self.cache.get(r.SOURCE_HEALTH_KEY)['sources']['regional_he'], 'prior':prior,
                    'pending':self.cache.get(pending_key),'ledger_unchanged':self.cache.get(ledger_key)==before_ledger,
                    'search_calls':search.call_count,'detail_calls':detail.call_count,'session_calls':session.call_count,
                    'timeouts':[c.kwargs.get('timeout_seconds') for c in detail.call_args_list], 'sleeps':sleeps}

    def test_runtime_budget_expired_or_margin_rejects_before_session(self):
        for mode in ('expired','margin'):
            with self.subTest(mode=mode):
                result = self.regional_budget_case(mode)
                self.assertEqual(result['status'],503)
                self.assertEqual((result['session_calls'],result['search_calls'],result['detail_calls']),(0,0,0))
                self.assertEqual(result['canonical'],result['old'])
                self.assertTrue(result['result']['retryable'])

    def test_runtime_budget_stops_late_work_and_preserves_pending_health(self):
        for mode in ('search_late','sleep_admission','sleep_overrun','detail_late','parse_late','precommit_late'):
            with self.subTest(mode=mode):
                result = self.regional_budget_case(mode)
                self.assertEqual(result['status'],503)
                self.assertEqual(result['result']['error'],'REGIONAL_WORK_BUDGET_EXCEEDED')
                self.assertEqual(result['canonical'],result['old'])
                self.assertEqual(result['pending'],['unresolved'])
                self.assertTrue(result['ledger_unchanged'])
                self.assertEqual(result['health']['last_successful_scan_at'],result['prior'])
                self.assertEqual(result['stage']['status'],'FAILED')
                self.assertFalse(result['result']['canonical_mutation_possible'])

    def test_runtime_primary_fallback_and_complete_empty_keep_semantics(self):
        for stage in ('regional_he','regional_he_fallback'):
            for mode in ('success','empty'):
                with self.subTest(stage=stage,mode=mode):
                    result=self.regional_budget_case(mode,stage=stage)
                    self.assertEqual(result['status'],200)
                    self.assertEqual(result['stage']['status'],'COMPLETED')
                    self.assertEqual(result['result']['result']['fallback_required'],stage=='regional_he' and mode=='empty')
                    self.assertTrue(all(0<t<=30 for t in result['timeouts']))
                    self.assertTrue(result['ledger_unchanged'])

    def test_runtime_fallback_budget_expiry_keeps_previous_canonical(self):
        result=self.regional_budget_case('search_late',stage='regional_he_fallback')
        self.assertEqual(result['status'],503)
        self.assertEqual((result['search_calls'],result['detail_calls']),(1,0))
        self.assertEqual(result['canonical'],result['old'])

    def test_runtime_ordinary_timeout_does_not_stop_other_queries(self):
        result=self.regional_budget_case('ordinary_error')
        self.assertEqual(result['search_calls'],2)
        self.assertEqual(result['status'],503)
        self.assertIsNone(result['result']['budget']['exhausted_phase'])
        self.assertEqual(result['canonical'],result['old'])

    def test_runtime_committed_lateness_is_not_relabelled_as_precommit_failure(self):
        for mode in ('commit_late','health_late'):
            with self.subTest(mode=mode):
                result=self.regional_budget_case(mode)
                self.assertEqual(result['status'],200)
                self.assertTrue(result['result']['budget_finalization_overrun'])
                self.assertEqual(result['stage']['status'],'COMPLETED')
                self.assertNotEqual(result['canonical'],result['old'])

    def test_runtime_write_failure_does_not_claim_zero_canonical_mutation(self):
        for mode,changed in (('write_error_before',False),('write_then_error',True)):
            with self.subTest(mode=mode):
                result=self.regional_budget_case(mode)
                self.assertEqual(result['status'],503)
                self.assertTrue(result['result']['canonical_mutation_possible'])
                self.assertEqual(result['canonical']!=result['old'],changed)

    def test_runtime_health_failure_after_canonical_has_unknown_receipt(self):
        result=self.regional_budget_case('health_error')
        self.assertEqual(result['error'],'REGIONAL_FINALIZATION_RESULT_UNKNOWN')
        self.assertTrue(result['result']['diagnostics']['canonical_mutation_possible'])
        self.assertEqual(result['stage']['status'],'COMPLETED')
        self.assertEqual(result['health']['last_successful_scan_at'],result['prior'])

    def test_runtime_failure_state_write_error_has_uncertain_state_receipt(self):
        result=self.regional_budget_case('failure_state_error')
        self.assertEqual(result['error'],'REGIONAL_FAILURE_STATE_RESULT_UNKNOWN')
        self.assertTrue(result['result']['diagnostics']['stage_or_health_mutation_possible'])
        self.assertFalse(result['result']['diagnostics']['canonical_mutation_possible'])
        self.assertEqual(result['canonical'],result['old'])
        self.assertEqual(result['stage']['status'],'RUNNING')

    def test_runtime_detail_timeout_is_clamped_to_remaining_margin(self):
        result=self.regional_budget_case('timeout_near')
        self.assertEqual(result['status'],200)
        self.assertEqual(result['timeouts'],[1])

    def test_regional_partial_discovery_or_detail_failure_never_changes_canonical(self):
        candidate, record = self.parse_fixture("tjzyefy")
        plan = self.runtime.load_regional_plan(self.runtime.DATA_ROOT / "multi_region_query_plan.json")
        plan.update(keywords=["医院"], notice_types=["公开招标"], delay_seconds=0)
        regional = [types.SimpleNamespace(title="医院医疗设备", published_at="2026-09-28", region="北京", buyer_name="北京医院",
                                          detail_url=f"https://www.ccgp.gov.cn/cggg/202609/t20260928_{index}.htm") for index in (1, 2)]
        key = self.runtime._regional_records_key("BJ")
        self.cache.set(key, [])
        with patch.object(self.runtime, "load_regional_plan", return_value=plan), patch.object(
            self.runtime, "RegionalCcgpSearchSession"), patch.object(self.runtime, "fetch_regional_candidates_page", return_value=[("公开招标", row) for row in regional]), patch.object(
            self.runtime, "regional_candidate_skip_reason", return_value=None), patch.object(self.runtime, "fetch_ccgp_detail_html", return_value="HTML"), patch.dict(
            self.runtime.VERIFIED_NOTICE_ADAPTERS, {"公开招标": unittest.mock.Mock(side_effect=[record, ValueError("DETAIL_CHANGED")])}
        ), patch.object(self.runtime, "annotate_regional_market", side_effect=lambda row, market: row):
            with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "REGIONAL_CANDIDATE_VERIFICATION_INCOMPLETE") as caught:
                self.runtime._run_regional_market(self.cache, self.state, "regional_bj")
        self.assertEqual(caught.exception.diagnostics["phase_counts"], {"verified_detail": 1})
        self.assertEqual(caught.exception.diagnostics["failure_count"], 1)
        self.assertEqual(self.cache.get(key), [])

    def test_safe_regional_failure_diagnostics_are_bounded_and_persisted(self):
        from collector_diagnostics import failure_row, failure_summary
        rows = [failure_row("verified_detail", ValueError("secret-credential"), f"https://private.example/{i}?key=secret") for i in range(9)]
        diagnostic = failure_summary(rows)
        self.assertEqual(diagnostic["failure_count"], 9)
        self.assertEqual(len(diagnostic["samples"]), 5)
        self.assertEqual(diagnostic["reason_counts"], {"DETAIL_VALIDATION_FAILED": 9})
        self.assertNotIn("secret", json.dumps(diagnostic))
        self.assertNotIn("private.example", json.dumps(diagnostic))
        self.assertEqual(failure_row("scoped_discovery", RuntimeError("CCGP_RATE_LIMITED:secret"), "q")["reason"], "RATE_LIMITED")
        self.assertEqual(failure_row("verified_detail", RuntimeError("CCGP_DETAIL_HTTP_403:secret"), "q")["reason"], "CCGP_DETAIL_HTTP_403")
        stage = "regional_ln"
        self.cache.set(self.runtime.META_KEY, {**self.state, "stages": {
            "regional_he_fallback": {"status": "COMPLETED"},
        }})
        error = self.runtime.CollectorStageBlocked("REGIONAL_CANDIDATE_VERIFICATION_INCOMPLETE:LN", diagnostics=diagnostic)
        with patch.object(self.runtime, "_run_regional_market", side_effect=error):
            status, result = self.runtime.run_stage(stage, now=self.now)
        self.assertEqual(status, 503)
        stored = self.cache.get(self.runtime.META_KEY)["stages"][stage]
        self.assertEqual(stored["diagnostics"], diagnostic)
        self.assertNotIn("secret", json.dumps(stored))

    def test_regional_throttle_stops_further_queries_and_keeps_canonical(self):
        old = [{"opportunity_id": "retained"}]
        self.cache.set(self.runtime._regional_records_key("LN"), old)
        with patch.object(self.runtime, "RegionalCcgpSearchSession"), patch.object(
            self.runtime, "fetch_regional_candidates_page", side_effect=RuntimeError("CCGP_RATE_LIMITED")) as fetch:
            with self.assertRaises(self.runtime.CollectorStageBlocked) as caught:
                self.runtime._run_regional_market(self.cache, self.state, "regional_ln")
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(caught.exception.diagnostics["reason_counts"], {"RATE_LIMITED": 1})
        self.assertEqual(self.cache.get(self.runtime._regional_records_key("LN")), old)

    def test_teda_access_denial_is_distinct_from_transient_server_failure(self):
        from urllib.error import HTTPError
        for code in (403, 503):
            with patch.object(self.runtime, "discover_teda_candidates", side_effect=HTTPError("https://www.tedahospital.com.cn/", code, "secret", None, None)):
                with self.assertRaises(self.runtime.CollectorStageBlocked) as caught:
                    self.runtime._run_teda(self.cache, self.state)
            self.assertEqual(caught.exception.retryable, code == 503)
            self.assertEqual(caught.exception.diagnostics["reason_counts"], {f"TEDA_HTTP_{code}": 1})
            self.assertNotIn("secret", str(caught.exception))

    def test_deep_reconciliation_clears_only_recent_matching_url(self):
        candidate, record = self.parse_fixture("tjzyefy")
        self.cache.set(self.runtime.TJZYEFY_RECORDS_KEY, [record])
        missing = "https://www.tjzyefy.com/system/2026/09/29/030199999.shtml"
        self.incremental._save_pending_barrier(self.cache, "tjzyefy", {candidate.detail_url, missing})
        result = self.incremental.reconcile_incremental_pending_from_canonical(self.cache, verified_after=self.now)
        self.assertEqual(result["resolved_barrier_count"], 1)
        self.assertEqual(self.incremental._load_pending_barrier(self.cache, "tjzyefy"), {missing})
        self.incremental._save_pending_barrier(self.cache, "tjzyefy", {candidate.detail_url})
        result = self.incremental.reconcile_incremental_pending_from_canonical(self.cache, verified_after=self.now + timedelta(seconds=1))
        self.assertEqual(result["resolved_barrier_count"], 0)
        self.assertEqual(self.incremental._load_pending_barrier(self.cache, "tjzyefy"), {candidate.detail_url})

    def test_eight_sources_each_scan_at_least_twice_in_unchanged_business_window(self):
        counts = Counter()
        # 11:30-19:00 Asia/Shanghai, one source per existing 15 minute tick.
        start = datetime(2026, 10, 1, 3, 30, tzinfo=timezone.utc)
        for step in range(31):
            now = start + timedelta(minutes=15 * step)
            decision = self.scheduler.choose_due_incremental_source(self.cache, now=now)
            if decision.source_id:
                source = decision.source_id
                counts[source] += 1
                self.scheduler.mark_incremental_source_attempt(self.cache, source, now=now)
                self.incremental._mark_bucket_completed(self.cache, source_id=source,
                    bucket_id=importlib.import_module("collector_incremental").scan_bucket_id(source, now=now),
                    completed_at=now, result={"selected_detail_count": 0, "verification_failure_count": 0, "pending_barrier_count": 0})
        self.assertEqual(set(counts), set(self.incremental.SUPPORTED_INCREMENTAL_SOURCES))
        self.assertGreaterEqual(min(counts.values()), 2, counts)

    def test_empty_pool_ack_zero_is_valid_but_missing_or_boolean_is_rejected(self):
        snapshot = {"snapshot_as_of": self.now.isoformat(), "cards": [], "opportunity_pool": []}
        class Response(io.BytesIO):
            status = 200
        with patch.dict(self.runtime.os.environ, {"VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "x" * 24}):
            for count in (0, None, False, "0"):
                response = Response(json.dumps({"ok": True, "snapshot_as_of": self.now.isoformat(), "opportunity_pool_count": count}).encode())
                with patch.object(self.runtime, "urlopen", return_value=response):
                    if type(count) is int:
                        self.assertEqual(self.runtime._persist_verified_snapshot_durably(snapshot)["opportunity_pool_count"], 0)
                    else:
                        with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "POOL_MISMATCH"):
                            self.runtime._persist_verified_snapshot_durably(snapshot)

    def test_durable_commit_survives_published_cache_failure(self):
        self.seed_all_canonical()
        original_set = self.cache.set
        def broken_set(key, value, options=None):
            if key == self.runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY:
                raise RuntimeError("CACHE_UNAVAILABLE")
            original_set(key, value, options)
        with patch.object(self.cache, "set", side_effect=broken_set):
            result, _ = self.publish()
        self.assertTrue(result["durable_snapshot_persisted"])
        self.assertEqual(result["cache_status"], "RETRY_REQUIRED")

    def run_stub_stage(self, stage, result=None, error=None):
        self.cache.set(self.runtime.META_KEY, self.state)
        if stage == "ccgp":
            function = "_run_ccgp"
        elif stage.startswith("event"):
            function = "_run_event_batch"
        elif stage == "tjfch":
            function = "_run_tjfch"
        else:
            function = "_run_regional_market"
        self.state["stages"][stage] = {"status": "RUNNING", "attempt_count": 1}
        self.cache.set(self.runtime.META_KEY, self.state)
        with patch.object(self.runtime, "_prepare_stage", return_value=(self.state, None)), patch.object(
                self.runtime, function, return_value=result or {}, side_effect=error), patch.object(self.runtime, "_now_utc", return_value=self.now):
            response = self.runtime.run_stage(stage, now=self.now)
        self.state = self.cache.get(self.runtime.META_KEY)
        return response

    def test_ccgp_event_failure_cannot_be_masked_by_later_batch_success(self):
        self.run_stub_stage("ccgp")
        self.assertIsNone(self.runtime.snapshot_source_health(self.cache)["sources"]["ccgp"]["last_successful_scan_at"])
        for stage in ("event1", "event2", "event3", "event4", "event5"):
            self.run_stub_stage(stage, error=ValueError("EVENT_FAILED") if stage == "event2" else None)
        self.run_stub_stage("event6")
        health = self.runtime.snapshot_source_health(self.cache)["sources"]["ccgp"]
        self.assertEqual(health["failure_reason"], "SOURCE_SCAN_FAILED")
        self.assertIsNone(health["last_successful_scan_at"])

    def test_ccgp_success_clock_requires_all_seven_stages(self):
        for stage in ("ccgp", "event1", "event2", "event3", "event4", "event5", "event6"):
            self.run_stub_stage(stage)
        self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"]["ccgp"]["last_successful_scan_at"], self.now.isoformat())

    def test_regional_skip_keeps_primary_failure_and_tjfch_failure_marks_both_feeds(self):
        self.runtime.record_source_scan(self.cache, "regional_bj", successful=False, attempted_at=self.now, failure_reason="INDEX_SCAN_FAILED")
        self.run_stub_stage("regional_bj_fallback", {"fallback_skipped": True})
        self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"]["regional_bj"]["failure_reason"], "INDEX_SCAN_FAILED")
        self.run_stub_stage("tjfch", error=ValueError("TEST_FEED_FAILED"))
        for source in ("tjfch", "tjfch_test"):
            self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["failure_reason"], "SOURCE_SCAN_FAILED")

    def test_event6_commits_one_bundle_only_after_prior_batches_completed(self):
        self.cache.set(self.runtime.CCGP_RECORDS_KEY, [])
        self.cache.set(self.runtime.CCGP_EVENTS_KEY, [])
        self.cache.set(self.runtime.CCGP_WATCH_KEY, [])
        staged = {"cycle_as_of": self.now.isoformat(), "records": [], "events": []}
        self.cache.set(self.runtime.CCGP_CYCLE_STAGING_KEY, staged)
        self.state["stages"] = {stage: {"status": "COMPLETED", "result": {"start_date": "2026:09:01", "end_date": "2026:10:01"}}
                                 for stage in ("ccgp", "event1", "event2", "event3", "event4", "event5")}
        self.state["stages"]["event2"]["status"] = "DEGRADED"
        with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "CCGP_SOURCE_TRANSACTION_INCOMPLETE"):
            self.runtime._run_event_batch(self.cache, self.state, "event6")
        self.assertIsNone(self.cache.get(self.runtime.CCGP_COMMITTED_STATE_KEY))
        self.state["stages"]["event2"]["status"] = "COMPLETED"
        self.runtime._run_event_batch(self.cache, self.state, "event6")
        self.assertEqual(self.cache.get(self.runtime.CCGP_COMMITTED_STATE_KEY), staged)

    def seed_nonempty_event_batch(self):
        self.state["stages"] = {"ccgp": {"status": "COMPLETED", "result": {
            "start_date": "2026:09:29", "end_date": "2026:10:01"}}}
        self.cache.set(self.runtime.META_KEY, self.state)
        self.cache.set(self.runtime.CCGP_WATCH_KEY, ["private-project-number"])
        self.cache.set(self.runtime.CCGP_CYCLE_STAGING_KEY, {
            "cycle_as_of": self.now.isoformat(), "records": [], "events": []})
        committed = {"cycle_as_of": "previous", "records": [], "events": []}
        self.cache.set(self.runtime.CCGP_COMMITTED_STATE_KEY, committed)
        return committed

    def prepare_retry_case(self, stage, previous, *, publish=None, fallback=False):
        stages={name:{"status":"COMPLETED"} for name in self.runtime.STAGE_ORDER[:self.runtime.STAGE_ORDER.index(stage)]}
        stages[stage]=previous
        if publish is not None:stages["publish"]=publish
        if fallback:stages[f"{stage}_fallback"]={"status":"DEGRADED"}
        self.cache.set(self.runtime.META_KEY,{**self.state,"stages":stages})
        with patch.object(self.runtime,"_now_utc",return_value=self.now):
            return self.runtime._prepare_stage(self.cache,stage,self.now)

    def test_stale_running_regional_migration_replay_requires_the_known_failure(self):
        for age,error,allowed in [(16,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:regional_bj",True),
                                  (1,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:regional_bj",False),
                                  (16,"OTHER_FAILURE",False)]:
            with self.subTest(age=age,error=error):
                previous={"status":"RUNNING","attempt_count":2,"wall_started_at":(self.now-timedelta(minutes=age)).isoformat()}
                if allowed:
                    state,prior=self.prepare_retry_case("regional_bj",previous,publish={"status":"FAILED","error_message":error},fallback=True)
                    self.assertIsNone(prior)
                    self.assertEqual(state["stages"]["regional_bj"]["attempt_count"],3)
                else:
                    with self.assertRaisesRegex(self.runtime.CollectorPrecondition,"COLLECTOR_STAGE_RETRY_LIMIT"):
                        self.prepare_retry_case("regional_bj",previous,publish={"status":"FAILED","error_message":error},fallback=True)

    def test_regional_timeout_split_recovery_has_real_negative_cases(self):
        for stage,status,attempts,error,fallback,allowed in [
            ("regional_bj","RUNNING",2,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:BJ",False,True),
            ("regional_bj","RUNNING",3,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:BJ",False,True),
            ("regional_bj","FAILED",2,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:BJ",False,False),
            ("regional_bj","RUNNING",4,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:BJ",False,False),
            ("regional_bj","RUNNING",2,"OTHER",False,False),
            ("regional_bj","RUNNING",2,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:BJ",True,False),
            ("tjmugh","RUNNING",2,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:BJ",False,False),
        ]:
            with self.subTest(stage=stage,status=status,attempts=attempts,error=error,fallback=fallback):
                previous={"status":status,"attempt_count":attempts,"wall_started_at":self.now.isoformat()}
                if allowed:
                    state,prior=self.prepare_retry_case(stage,previous,publish={"status":"FAILED","error_message":error},fallback=fallback)
                    self.assertIsNone(prior)
                    self.assertEqual(state["stages"][stage]["attempt_count"],attempts+1)
                else:
                    with self.assertRaisesRegex(self.runtime.CollectorPrecondition,"COLLECTOR_STAGE_RETRY_LIMIT"):
                        self.prepare_retry_case(stage,previous,publish={"status":"FAILED","error_message":error},fallback=fallback)

    def test_completed_regional_replay_occurs_only_when_its_shard_is_missing(self):
        key=self.runtime._regional_records_key("BJ")
        previous={"status":"COMPLETED","attempt_count":2}
        self.cache.delete(key)
        state,prior=self.prepare_retry_case("regional_bj",previous)
        self.assertIsNone(prior)
        self.assertEqual(state["stages"]["regional_bj"]["attempt_count"],3)
        self.cache.set(key,[])
        state,prior=self.prepare_retry_case("regional_bj",previous)
        self.assertEqual(prior,previous)
        self.assertEqual(state["stages"]["regional_bj"]["attempt_count"],2)

    def test_publish_migration_retry_is_bounded_and_missing_canonical_is_named(self):
        for attempts,error,allowed in [(2,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:BJ",True),
                                       (3,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:BJ",False),(2,"DATABASE_UNAVAILABLE",False)]:
            with self.subTest(attempts=attempts,error=error):
                previous={"status":"FAILED","attempt_count":attempts,"error_message":error}
                if allowed:
                    state,prior=self.prepare_retry_case("publish",previous)
                    self.assertIsNone(prior)
                    self.assertEqual(state["stages"]["publish"]["attempt_count"],3)
                else:
                    with self.assertRaisesRegex(self.runtime.CollectorPrecondition,"COLLECTOR_STAGE_RETRY_LIMIT"):
                        self.prepare_retry_case("publish",previous)
        with self.assertRaisesRegex(self.runtime.CollectorPrecondition,"COLLECTOR_CANONICAL_STATE_INCOMPLETE:.*ccgp"):
            self.runtime._run_publish(self.cache,self.state)

    def test_tjfch_policy_recovery_retry_is_narrowly_scoped_in_behavior(self):
        for stage,attempts,error,allowed in [("tjfch",2,"TJFCH_NOTICE_TYPE_UNSUPPORTED",True),
            ("tjfch",3,"TJFCH_NOTICE_TYPE_UNSUPPORTED",False),("tjfch",2,"OTHER_FAILURE",False),
            ("teda",2,"TJFCH_NOTICE_TYPE_UNSUPPORTED",False)]:
            with self.subTest(stage=stage,attempts=attempts,error=error):
                previous={"status":"FAILED","attempt_count":attempts,"error_message":error}
                if allowed:
                    state,prior=self.prepare_retry_case(stage,previous)
                    self.assertIsNone(prior)
                    self.assertEqual(state["stages"][stage]["attempt_count"],3)
                else:
                    with self.assertRaisesRegex(self.runtime.CollectorPrecondition,"COLLECTOR_STAGE_RETRY_LIMIT"):
                        self.prepare_retry_case(stage,previous)

    def test_nonempty_event_failure_persists_only_safe_diagnostics_and_keeps_committed_bundle(self):
        committed = self.seed_nonempty_event_batch()
        def failed(project, **options):
            options["failures"].append({"stage": "event_detail", "project_number": project,
                "url": "https://official.example/private?token=secret", "error": "CcgpEventParseError",
                "message": "CCGP_EVENT_PROJECT_NUMBER_NOT_FOUND:secret"})
            return []
        with patch.object(self.runtime, "scan_events", side_effect=failed):
            status, result = self.runtime.run_stage("event1", now=self.now)
        self.assertEqual(status, 503)
        self.assertFalse(result["retry_exhausted"])
        row=self.cache.get(self.runtime.META_KEY)["stages"]["event1"]
        self.assertEqual(row["diagnostics"]["reason_counts"], {"CCGP_EVENT_PROJECT_NUMBER_NOT_FOUND": 1})
        self.assertEqual(row["diagnostics"]["phase_counts"], {"event_detail":1})
        for private in ["private-project-number", "official.example", "secret", "token="]:
            self.assertNotIn(private,json.dumps(row))
        self.assertEqual(self.cache.get(self.runtime.CCGP_COMMITTED_STATE_KEY),committed)
        self.assertIsNone(self.runtime.snapshot_source_health(self.cache)["sources"]["ccgp"]["last_successful_scan_at"])

    def test_both_searches_failed_have_diagnostics_without_raw_project_in_error(self):
        self.seed_nonempty_event_batch()
        def failed(project, **options):
            for notice in ["更正公告","终止公告"]:
                options["failures"].append({"stage":"event_search","project_number":project,
                    "notice_type":notice,"error":"RuntimeError","message":"CCGP_RATE_LIMITED:secret"})
            return []
        with patch.object(self.runtime,"scan_events",side_effect=failed):
            status,result=self.runtime.run_stage("event1",now=self.now)
        self.assertEqual(status,503)
        self.assertEqual(result["error"],"EVENT_WATCH_ALL_SEARCHES_FAILED")
        row=self.cache.get(self.runtime.META_KEY)["stages"]["event1"]
        self.assertEqual(row["diagnostics"]["reason_counts"],{"RATE_LIMITED":2})
        self.assertNotIn("private-project-number",json.dumps(row))

    def test_unexpected_event_scan_exception_is_safe_and_observable(self):
        committed=self.seed_nonempty_event_batch()
        with patch.object(self.runtime,"scan_events",side_effect=RuntimeError("token=secret private-project-number")):
            status,result=self.runtime.run_stage("event1",now=self.now)
        self.assertEqual(status,503)
        self.assertEqual(result["error"],"EVENT_WATCH_SCAN_FAILED")
        row=self.cache.get(self.runtime.META_KEY)["stages"]["event1"]
        self.assertEqual(row["diagnostics"]["phase_counts"],{"event_scan":1})
        self.assertNotIn("secret",json.dumps(row))
        self.assertEqual(self.cache.get(self.runtime.CCGP_COMMITTED_STATE_KEY),committed)

    def test_successful_nonempty_event_watch_still_commits_only_after_final_batch(self):
        committed=self.seed_nonempty_event_batch()
        event={"schema_version":"0.1","event_id":"termination-example","event_type":"TERMINATION",
            "project_number":"private-project-number","project_name":"verified-example","published_at":"2026-10-01",
            "source_url":"https://www.ccgp.gov.cn/example","observed_at":self.now.isoformat(),"summary":"project terminated",
            "changed_fact_paths":[],"fact_overrides":{},"unresolved_fact_paths":[],"requires_reconciliation":False,"terminal":True}
        with patch.object(self.runtime,"scan_events",return_value=[event]) as scan:
            for index in range(1,7):
                status,result=self.runtime.run_stage(f"event{index}",now=self.now)
                self.assertEqual(status,200)
                if index<6:self.assertEqual(self.cache.get(self.runtime.CCGP_COMMITTED_STATE_KEY),committed)
        self.assertEqual(scan.call_count,1)
        self.assertEqual(self.cache.get(self.runtime.CCGP_COMMITTED_STATE_KEY)["events"],[event])
        self.assertIsNotNone(self.runtime.snapshot_source_health(self.cache)["sources"]["ccgp"]["last_successful_scan_at"])


if __name__ == "__main__":
    unittest.main()
