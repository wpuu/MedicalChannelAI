from __future__ import annotations

import copy
import importlib
import io
import json
import sys
import types
import unittest
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
            with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "REGIONAL_CANDIDATE_VERIFICATION_INCOMPLETE"):
                self.runtime._run_regional_market(self.cache, self.state, "regional_bj")
        self.assertEqual(self.cache.get(key), [])

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


if __name__ == "__main__":
    unittest.main()
