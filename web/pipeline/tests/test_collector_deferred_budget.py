from __future__ import annotations

import copy
import importlib
import json
import socket
import urllib.request
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))


class MemoryCache:
    def __init__(self):
        self.values = {}
        self.writes = []

    def get(self, key):
        return copy.deepcopy(self.values.get(key))

    def set(self, key, value, options=None):
        self.values[key] = copy.deepcopy(value)
        self.writes.append((key, copy.deepcopy(value)))

    def delete(self, key):
        self.values.pop(key, None)


class CollectorDeferredBudgetTests(unittest.TestCase):
    def setUp(self):
        self.cache = MemoryCache()
        functions = types.ModuleType("vercel.functions")
        functions.RuntimeCache = lambda *args, **kwargs: self.cache
        modules = patch.dict(sys.modules, {"vercel": types.ModuleType("vercel"), "vercel.functions": functions})
        modules.start()
        self.addCleanup(modules.stop)
        for name in ("collector_runtime", "collector_incremental_runtime", "collector_incremental_bootstrap"):
            sys.modules.pop(name, None)
        self.runtime = importlib.import_module("collector_runtime")
        self.incremental = importlib.import_module("collector_incremental_runtime")
        self.planner = importlib.import_module("collector_incremental")
        self.now = datetime(2026, 10, 1, 4, tzinfo=timezone.utc)
        self.template = json.loads((WEB_ROOT / "pipeline/data/tianjin_verified_seed.json").read_text())[0]
        sleeping = patch.object(self.runtime.time, "sleep")
        sleeping.start()
        self.addCleanup(sleeping.stop)
        for owner, name in ((socket.socket, "connect"), (socket, "create_connection"),
                            (socket, "getaddrinfo"), (urllib.request, "build_opener")):
            blocker = patch.object(owner, name, side_effect=AssertionError("NETWORK_OR_REAL_SDK_FORBIDDEN"))
            blocker.start()
            self.addCleanup(blocker.stop)

    def fixture(self, source, count):
        # Synthetic canonical records exercise the real planner and commit path.
        # Parser grounding/host checks have separate official-adapter fixtures.
        host = "www.tjzxfc.cn" if source == "tjzxfc" else "www.tjzyefy.com"
        rows = {}
        candidates = []
        for index in range(1, count + 1):
            row = copy.deepcopy(self.template)
            identity = f"synthetic_{source}_{index:03d}"
            url = f"https://{host}/system/2026/10/01/{index:09d}.shtml"
            row["opportunity_id"] = identity
            row["source"].update(source_id=f"{source}:{identity}", source_type="OFFICIAL_INSTITUTION_NOTICE",
                                 url=url, observed_at=(self.now - timedelta(days=2)).isoformat())
            row["facts"].update(project_number=None, project_name=f"合成医疗设备项目{index:03d}", published_at="2026-10-01")
            for evidence in row["evidence"]:
                evidence["source_url"] = url
            rows[url] = row
            candidates.append(types.SimpleNamespace(title=row["facts"]["project_name"], published_at="2026-10-01", detail_url=url))
        return candidates, rows

    def seed_source(self, source):
        self.cache = MemoryCache()
        _, key = self.incremental._existing_records(self.cache, source)
        baseline = copy.deepcopy(self.template)
        self.cache.set(key, [baseline])
        prior = self.now - timedelta(hours=2)
        self.runtime.record_source_scan(self.cache, source, successful=True, attempted_at=prior)
        self.cache.writes.clear()
        return key, [baseline], prior

    def verifier(self, rows):
        def verify(candidate, observed_at, now):
            row = copy.deepcopy(rows[candidate.detail_url])
            row["source"]["observed_at"] = observed_at
            return row
        return verify


    def incremental_budget_case(self, mode="success", *, count=2):
        source = "tjzyefy"
        key, baseline, prior = self.seed_source(source)
        candidates, rows = self.fixture(source, count)
        if mode in {"empty", "old_pending_empty"}:
            candidates = []
        if mode == "periodic_defer":
            ledger = self.planner.plan_detail_verification(source, candidates, None, now=self.now).next_ledger
            for candidate in candidates:
                ledger = self.planner.record_verification_success(ledger, self.planner.candidate_observation(source, candidate),
                                                                  verified_at=self.now - timedelta(hours=25))
            self.incremental._save_ledger(self.cache, source, ledger)
        if mode == "old_pending_empty":
            self.incremental._save_pending_barrier(self.cache, source, {"old-unresolved"})
        tick = [180.0 if mode == "expired" else 0.0]
        events, called, fired = [], [], set()
        pending_key = self.incremental._pending_cache_key(source)
        barrier_key = self.incremental._pending_barrier_cache_key(source)
        ledger_key = self.incremental._ledger_cache_key(source)
        bucket_key = self.incremental._bucket_cache_key(source)
        other_key = self.incremental._pending_barrier_cache_key("tjzyefy_intent")
        self.cache.set(other_key, ["unresolved-other-source"])
        def sleep(delay):
            tick[0] += delay
            if mode == "sleep_late":
                tick[0] = 180
        budget = self.runtime.CliBudget(lambda: tick[0], sleep, total_seconds=270, work_seconds=180, started_at=0)
        original_check = budget.check
        def checked(phase, **kwargs):
            if mode == "pre_canonical_late" and phase == "PRE_CANONICAL":
                tick[0] = 270
            if mode.startswith("admit_") and phase == mode[6:]:
                tick[0] = 33
            return original_check(phase, **kwargs)
        budget.check = checked
        def discover(now, **kwargs):
            called.append("index")
            if mode == "index_late":
                tick[0] = 180
            elif mode in {"sleep_admission", "periodic_defer"}:
                tick[0] = 177
            return candidates
        verify_row = self.verifier(rows)
        def verify(candidate, observed_at, now, **kwargs):
            called.append(candidate.detail_url)
            if mode in {"detail_late", "nonfact_late"}:
                tick[0] = 180
            if mode == "hard_stop" and len(called) == 3:
                raise KeyboardInterrupt("synthetic hard stop")
            if mode in {"ordinary_error", "failure_ledger_error"} and len(called) == 2:
                raise RuntimeError("SYNTHETIC_DETAIL_ERROR")
            return None if mode in {"nonfact", "nonfact_late"} else verify_row(candidate, observed_at, now)
        original_set, original_delete, original_get = self.cache.set, self.cache.delete, self.cache.get
        def changed(kind, cache_key, value=None):
            events.append((kind, cache_key))
            if mode == "staging_recovery_error" and "staging" in fired and cache_key == barrier_key and kind == "set" and len(value) == count:
                raise OSError("SYNTHETIC_RECOVERY_WRITE")
            target = None
            if cache_key == pending_key and kind == "set" and mode.startswith("staging_"):
                target = "staging"
            if cache_key == barrier_key and kind == "set" and len(value) == count - 1 and mode.startswith("barrier_"):
                target = "barrier"
            if cache_key == ledger_key and kind == "set" and any(r.get("verification_status") == "VERIFIED" for r in value["entries"].values()) and mode.startswith("ledger_"):
                target = "ledger"
            if cache_key == key and kind == "set":
                target = "canonical"
            if cache_key == self.runtime.SOURCE_HEALTH_KEY and kind == "set" and (value["sources"].get(source) or {}).get("last_successful_scan_at") == self.now.isoformat():
                target = "health"
            if cache_key == bucket_key and kind == "set":
                target = "bucket"
            if mode == "failure_ledger_error" and cache_key == ledger_key and kind == "set" and any(r.get("verification_status") == "FAILED" for r in value["entries"].values()):
                raise OSError("SYNTHETIC_FAILURE_LEDGER")
            if target and target not in fired:
                fired.add(target)
                if mode == target + "_error_before":
                    raise OSError("SYNTHETIC_WRITE_BEFORE")
                if mode == "staging_recovery_error" and target == "staging":
                    tick[0] += 30
                if mode == target + "_late":
                    tick[0] = 270 if target in {"canonical", "bucket", "health"} else tick[0] + 30
                if mode == "publish_admission" and target == "canonical":
                    tick[0] = 240
            return target
        def setter(cache_key, value, options=None):
            target = changed("set", cache_key, value)
            original_set(cache_key, value, options)
            if mode == "staging_error_then_deadline" and target == "staging":
                tick[0] = 270
                raise OSError("SYNTHETIC_ORIGINAL_WRITE_ERROR")
            if mode == str(target) + "_error_after":
                # One reported error after the in-memory write; recovery uses non-VERIFIED state.
                if "raised" not in fired:
                    fired.add("raised")
                    raise OSError("SYNTHETIC_WRITE_AFTER")
        def deleter(cache_key):
            changed("delete", cache_key)
            original_delete(cache_key)
        def getter(cache_key):
            if mode == "finalize_late" and cache_key == key and len(called) > count and "finalize" not in fired:
                fired.add("finalize")
                tick[0] = 210
            return original_get(cache_key)
        def publish(cache, now, **kwargs):
            called.append("publish")
            if mode == "publish_error":
                raise OSError("SYNTHETIC_PUBLISH_UNKNOWN")
            if mode == "publish_late":
                tick[0] = 270
            return True, {"snapshot_as_of": self.now.isoformat()}
        status, result, error = None, {}, None
        with patch.dict(self.incremental._DISCOVERY, {source: discover}), patch.dict(
            self.incremental._VERIFICATION, {source: verify}), patch.object(
            self.incremental, "_publish_snapshot_if_ready", side_effect=publish), patch.object(
            self.cache, "set", side_effect=setter), patch.object(self.cache, "delete", side_effect=deleter), patch.object(
            self.cache, "get", side_effect=getter):
            try:
                status, result = self.incremental.run_incremental_source(source, now=self.now, cache=self.cache, budget=budget)
            except BaseException as exc:
                error = type(exc).__name__
        return {"status": status, "result": result, "exception": error, "called": called, "events": events,
                "canonical": original_get(key), "baseline": baseline,
                "staged": self.incremental._load_pending_records(self.cache, source),
                "barrier": sorted(self.incremental._load_pending_barrier(self.cache, source)),
                "ledger": self.incremental._load_ledger(self.cache, source), "bucket": original_get(bucket_key),
                "health": self.runtime.snapshot_source_health(self.cache)["sources"][source], "prior": prior.isoformat(),
                "other_pending": original_get(other_key), "tick": tick[0]}

    def test_incremental_budget_rejects_before_or_after_discovery(self):
        for mode in ("expired", "index_late"):
            with self.subTest(mode=mode):
                c = self.incremental_budget_case(mode)
                self.assertEqual(c["status"], 503)
                self.assertEqual(c["called"], [] if mode == "expired" else ["index"])
                self.assertEqual(c["canonical"], c["baseline"])
                self.assertIsNone(c["bucket"])

    def test_incremental_budget_sleep_and_fact_nonfact_lateness_keep_pending(self):
        for mode in ("sleep_admission", "sleep_late", "detail_late", "nonfact_late"):
            with self.subTest(mode=mode):
                c = self.incremental_budget_case(mode)
                self.assertEqual(c["status"], 503)
                self.assertEqual(len(c["barrier"]), 2)
                self.assertFalse(c["staged"])
                self.assertFalse(any(r["verification_status"] == "VERIFIED" for r in c["ledger"]["entries"].values()))
                self.assertEqual(c["health"]["last_successful_scan_at"], c["prior"])
                self.assertNotIn("publish", c["called"])

    def test_incremental_budget_save_steps_late_recover_without_partial_canonical(self):
        for mode in ("staging_late", "barrier_late", "ledger_late", "admit_URL_STAGING", "admit_URL_BARRIER", "admit_URL_LEDGER"):
            with self.subTest(mode=mode):
                c = self.incremental_budget_case(mode)
                self.assertEqual(c["status"], 503)
                self.assertTrue(c["result"]["recovery_confirmed"])
                self.assertEqual(len(c["barrier"]), 2)
                self.assertEqual(c["canonical"], c["baseline"])
                self.assertIsNone(c["bucket"])
                self.assertEqual(len(c["called"]), 2)
                self.assertFalse(any(r["verification_status"] == "VERIFIED" for r in c["ledger"]["entries"].values()))
                self.assertEqual(c["other_pending"], ["unresolved-other-source"])

    def test_incremental_budget_save_io_errors_stop_and_report_unknown(self):
        for mode in ("staging_error_before", "staging_error_after", "barrier_error_after", "ledger_error_after", "failure_ledger_error"):
            with self.subTest(mode=mode):
                c = self.incremental_budget_case(mode)
                self.assertEqual(c["status"], 503)
                self.assertEqual(c["result"]["error"], "INCREMENTAL_STATE_RESULT_UNKNOWN")
                self.assertTrue(c["result"]["pending_or_ledger_mutation_possible"])
                self.assertEqual(c["canonical"], c["baseline"])
                self.assertIsNone(c["bucket"])
                self.assertEqual(len(c["called"]), 2)

    def test_incremental_budget_complete_empty_nonfact_and_count_deferred(self):
        for mode, count in (("success", 2), ("empty", 0), ("nonfact", 2), ("success", 13)):
            with self.subTest(mode=mode, count=count):
                c = self.incremental_budget_case(mode, count=count)
                self.assertEqual(c["status"], 200)
                self.assertIsNotNone(c["bucket"])
                self.assertEqual(c["result"]["budget"]["work_complete"], count != 13)
                if count == 13:
                    self.assertEqual(len(c["barrier"]), 1)
                    self.assertEqual(len(c["staged"]), 12)
                    self.assertFalse(c["result"]["snapshot_refreshed"])
                    self.assertEqual(c["canonical"], c["baseline"])
                else:
                    self.assertFalse(c["barrier"])
                    self.assertTrue(c["result"]["snapshot_refreshed"])

    def test_incremental_budget_finalization_and_precanonical_reject_preserve_staging(self):
        for mode in ("finalize_late", "pre_canonical_late"):
            with self.subTest(mode=mode):
                c = self.incremental_budget_case(mode)
                self.assertEqual(c["status"], 503)
                self.assertEqual(c["canonical"], c["baseline"])
                self.assertEqual(len(c["staged"]), 2)
                self.assertNotIn("publish", c["called"])

    def test_incremental_budget_canonical_unknown_distinguishes_before_and_after(self):
        for mode in ("canonical_error_before", "canonical_error_after"):
            with self.subTest(mode=mode):
                c = self.incremental_budget_case(mode)
                self.assertEqual(c["status"], 503)
                self.assertTrue(c["result"]["canonical_mutation_possible"])
                self.assertIsNone(c["result"]["canonical_write_completed"])
                self.assertEqual(c["canonical"] == c["baseline"], mode.endswith("before"))

    def test_incremental_budget_postcanonical_and_publish_admission_keep_known_commit(self):
        for mode in ("canonical_late", "health_late", "publish_admission"):
            with self.subTest(mode=mode):
                c = self.incremental_budget_case(mode)
                self.assertEqual(c["status"], 503)
                self.assertTrue(c["result"]["canonical_write_completed"])
                self.assertNotEqual(c["canonical"], c["baseline"])
                self.assertNotIn("publish", c["called"])
                self.assertEqual(c["health"]["last_successful_scan_at"], self.now.isoformat())
                self.assertIsNone(c["bucket"])

    def test_incremental_budget_publish_and_bucket_lateness_or_unknown(self):
        for mode in ("publish_late", "bucket_late", "publish_error", "bucket_error_after", "health_error_before"):
            with self.subTest(mode=mode):
                c = self.incremental_budget_case(mode)
                self.assertNotEqual(c["canonical"], c["baseline"])
                if mode in {"publish_late", "bucket_late"}:
                    self.assertEqual(c["status"], 200)
                    self.assertTrue(c["result"]["budget_finalization_overrun"])
                    self.assertEqual(c["result"]["publication_outcome"], "CONFIRMED")
                else:
                    self.assertEqual(c["status"], 503)
                    self.assertTrue(c["result"]["canonical_write_completed"])
                    if mode == "bucket_error_after":
                        self.assertTrue(c["result"]["snapshot_refreshed"])
                    elif mode == "publish_error":
                        self.assertEqual(c["result"]["publication_outcome"], "UNKNOWN")

    def test_incremental_budget_hard_stop_preserves_sibling_staging(self):
        c = self.incremental_budget_case("hard_stop")
        self.assertEqual(c["exception"], "KeyboardInterrupt")
        self.assertEqual(len(c["staged"]), 1)
        self.assertEqual(len(c["barrier"]), 1)
        self.assertEqual(c["canonical"], c["baseline"])

    def test_incremental_budget_ordinary_error_does_not_disable_other_details(self):
        c = self.incremental_budget_case("ordinary_error")
        self.assertEqual(c["status"], 503)
        self.assertEqual(len(c["called"]), 3)
        self.assertEqual(len(c["staged"]), 1)
        self.assertEqual(len(c["barrier"]), 1)

    def test_incremental_budget_periodic_recheck_remains_carryover_and_old_empty_barrier_survives(self):
        c = self.incremental_budget_case("periodic_defer")
        self.assertEqual(c["status"], 503)
        self.assertTrue(all(r["verification_status"] == "UNVERIFIED" for r in c["ledger"]["entries"].values()))
        plan = self.planner.plan_detail_verification("tjzyefy", [], c["ledger"], now=self.now + timedelta(minutes=1))
        self.assertEqual([r.reason for r in plan.selected], ["PENDING_CARRYOVER"] * 2)
        c = self.incremental_budget_case("old_pending_empty")
        self.assertEqual(c["status"], 200)
        self.assertFalse(c["result"]["snapshot_refreshed"])
        self.assertEqual(c["barrier"], ["old-unresolved"])
        self.assertFalse(c["result"]["budget"]["work_complete"])
        self.assertEqual(c["health"]["last_successful_scan_at"], c["prior"])

    def test_incremental_budget_frozen_detail_parser_rejects_late_fact_and_nonfact(self):
        html = (WEB_ROOT / "pipeline/tests/fixtures/tjzyefy_20261020_030201209_service_excerpt.html").read_text()
        candidate = types.SimpleNamespace(title="天津中医药大学第二附属医院制剂室内包材检验服务项目调研公告",
            published_at="2026-10-20", detail_url="https://www.tjzyefy.com/system/2026/10/20/030201209.shtml")
        real_parse = self.runtime.parse_tjzyefy_market_research
        for mode in ("timely", "late_fact", "late_nonfact"):
            with self.subTest(mode=mode):
                tick = [0.0]
                budget = self.runtime.CliBudget(lambda: tick[0], lambda d: None, total_seconds=270, work_seconds=180)
                def parse(*args, **kwargs):
                    if mode == "late_nonfact":
                        tick[0] = 180
                        raise self.runtime.TjzyefyParseError("TJZYEFY_NON_MEDICAL_RESEARCH")
                    record = real_parse(*args, **kwargs)
                    if mode == "late_fact": tick[0] = 180
                    return record
                with patch.object(self.runtime, "fetch_tjzyefy_page_with_retry", return_value=html) as fetch, patch.object(
                    self.runtime, "parse_tjzyefy_market_research", side_effect=parse):
                    if mode == "timely":
                        record = self.incremental._verify_tjzyefy(candidate, self.now.isoformat(), self.now, budget=budget)
                        self.assertEqual(record["facts"]["registration_deadline"], "2026-10-29T17:00:00+08:00")
                    else:
                        with self.assertRaises(self.runtime.CliBudgetExceeded):
                            self.incremental._verify_tjzyefy(candidate, self.now.isoformat(), self.now, budget=budget)
                self.assertIs(fetch.call_args.kwargs["budget"], budget)

    def test_incremental_budget_finally_expiry_does_not_mask_original_io_error(self):
        c = self.incremental_budget_case("staging_error_then_deadline")
        self.assertEqual(c["status"], 503)
        self.assertEqual(c["result"]["error"], "INCREMENTAL_STATE_RESULT_UNKNOWN")
        self.assertEqual(c["result"]["error_type"], "OSError")
        self.assertEqual(c["result"]["failure_ledger_error_type"], "CliBudgetExceeded")
        self.assertFalse(c["result"]["recovery_confirmed"])
        self.assertTrue(c["result"]["budget_finalization_overrun"])
        self.assertEqual(c["canonical"], c["baseline"])
        self.assertEqual(len(c["staged"]), 1)

    def test_incremental_budget_recovery_write_failure_never_claims_restoration(self):
        c = self.incremental_budget_case("staging_recovery_error")
        self.assertEqual(c["status"], 503)
        self.assertEqual(c["result"]["error"], "INCREMENTAL_TIME_BUDGET_EXCEEDED")
        self.assertFalse(c["result"]["recovery_confirmed"])
        self.assertEqual(c["result"]["recovery_error_type"], "OSError")
        self.assertTrue(c["result"]["pending_or_ledger_mutation_possible"])
        self.assertEqual(c["canonical"], c["baseline"])
        self.assertEqual(len(c["staged"]), 1)

    def test_incremental_publish_bridge_forwards_exact_parent_budget(self):
        tick = [195.0]
        budget = self.runtime.CliBudget(lambda: tick[0], lambda d: None, total_seconds=270, work_seconds=180, started_at=0)
        def publish(cache, state, **kwargs):
            self.assertIs(kwargs["budget"], budget)
            self.runtime._publish_work_check(budget, {}, "PUBLISH_TEST")
            return {"snapshot_as_of": self.now.isoformat(), "publish_receipt": {"publication_outcome": "CONFIRMED"}}
        with patch.object(self.runtime, "_run_publish", side_effect=publish):
            success, result = self.incremental._publish_snapshot_if_ready(self.cache, self.now, budget=budget)
        self.assertTrue(success)
        self.assertEqual(budget.started, 0)
        self.assertEqual(budget.work_seconds, 180)

    def test_incremental_publisher_failure_uses_precise_attempt_receipt(self):
        for outcome in ("NOT_ATTEMPTED", "UNKNOWN"):
            with self.subTest(outcome=outcome):
                key, baseline, prior = self.seed_source("tjzyefy")
                b = self.runtime.CliBudget(lambda: 0, lambda d: None, total_seconds=270, work_seconds=180)
                error = self.runtime.CliBudgetExceeded("PUBLISH_WORK") if outcome == "NOT_ATTEMPTED" else OSError("SYNTHETIC_PUT")
                error.diagnostics = {"publish_receipt": {"publication_outcome": outcome}}
                with patch.dict(self.incremental._DISCOVERY, {"tjzyefy": lambda *args, **kwargs: []}), patch.object(self.runtime, "_run_publish", side_effect=error):
                    status, result = self.incremental.run_incremental_source("tjzyefy", now=self.now, cache=self.cache, budget=b)
                self.assertEqual(status, 503)
                self.assertEqual(result["publication_outcome"], outcome)
                self.assertEqual(result["publish_receipt"]["publication_outcome"], outcome)
                self.assertEqual(self.cache.get(key), baseline)
                self.assertIsNone(self.cache.get(self.incremental._bucket_cache_key("tjzyefy")))

    def test_incremental_real_bridge_confirmed_then_bucket_failure_keeps_receipt(self):
        self.seed_source("tjzyefy")
        b = self.runtime.CliBudget(lambda: 0, lambda d: None, total_seconds=270, work_seconds=180)
        result = {"snapshot_as_of": self.now.isoformat(), "publish_receipt": {"publication_outcome": "CONFIRMED"}}
        with patch.dict(self.incremental._DISCOVERY, {"tjzyefy": lambda *args, **kwargs: []}), patch.object(
            self.runtime, "_run_publish", return_value=result), patch.object(self.incremental, "_mark_bucket_completed", side_effect=OSError("SYNTHETIC_BUCKET")):
            status, response = self.incremental.run_incremental_source("tjzyefy", now=self.now, cache=self.cache, budget=b)
        self.assertEqual(status, 503)
        self.assertTrue(response["snapshot_refreshed"])
        self.assertEqual(response["publish_receipt"]["publication_outcome"], "CONFIRMED")
        self.assertTrue(response["bucket_mutation_possible"])

    def test_other_incremental_source_does_not_receive_publisher_budget(self):
        self.seed_source("tjzyefy_intent")
        b = self.runtime.CliBudget(lambda: 210, lambda d: None, total_seconds=270, work_seconds=180, started_at=0)
        with patch.dict(self.incremental._DISCOVERY, {"tjzyefy_intent": lambda *args, **kwargs: []}), patch.object(
            self.runtime, "_run_publish", return_value={"snapshot_as_of": self.now.isoformat()}) as publish:
            status, result = self.incremental.run_incremental_source("tjzyefy_intent", now=self.now, cache=self.cache, budget=b)
        self.assertEqual(status, 200)
        self.assertNotIn("budget", publish.call_args.kwargs)
        self.assertNotIn("budget", result)

    def test_exactly_twelve_incremental_details_commit_normally_for_all_three_sources(self):
        for source in ("tjzyefy", "tjzyefy_intent", "tjzxfc"):
            with self.subTest(source=source):
                key, baseline, _ = self.seed_source(source)
                candidates, rows = self.fixture(source, 12)
                with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates}), patch.dict(
                    self.incremental._VERIFICATION, {source: self.verifier(rows)},
                ), patch.object(self.incremental, "_publish_snapshot_if_ready", return_value=(True, {"snapshot_as_of": self.now.isoformat()})) as publish:
                    status, result = self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
                self.assertEqual(status, 200)
                self.assertEqual(result["selected_detail_count"], 12)
                self.assertEqual(result["deferred_detail_count"], 0)
                self.assertTrue(result["snapshot_refreshed"])
                self.assertEqual(len(self.cache.get(key)), len(baseline) + 12)
                self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], self.now.isoformat())
                publish.assert_called_once()

    def test_thirteenth_detail_defers_entire_source_then_carryover_commits_once(self):
        for source in ("tjzyefy", "tjzyefy_intent", "tjzxfc"):
            with self.subTest(source=source):
                key, baseline, prior = self.seed_source(source)
                candidates, rows = self.fixture(source, 13)
                with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates}), patch.dict(
                    self.incremental._VERIFICATION, {source: self.verifier(rows)},
                ), patch.object(self.incremental, "_publish_snapshot_if_ready", return_value=(False, None)) as publish:
                    status, result = self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
                    self.assertEqual(status, 200)
                    self.assertEqual(result["selected_detail_count"], 12)
                    self.assertEqual(result["deferred_detail_count"], 1)
                    self.assertEqual(result["deferred_reason"], "DETAIL_BUDGET_DEFERRED")
                    self.assertFalse(result["snapshot_refreshed"])
                    self.assertEqual(self.cache.get(key), baseline)
                    self.assertEqual(len(self.incremental._load_pending_records(self.cache, source)), 12)
                    self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), {candidates[-1].detail_url})
                    self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], prior.isoformat())
                    publish.assert_not_called()
                    later = self.now + timedelta(minutes=self.planner.SOURCE_POLICIES[source]["scan_interval_minutes"] + 1)
                    # The budget-deferred URL disappears from the next index.
                    with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates[:12]}):
                        status, result = self.incremental.run_incremental_source(source, now=later, cache=self.cache)
                self.assertEqual(status, 200)
                self.assertEqual(result["selected_detail_count"], 1)
                self.assertEqual(result["deferred_detail_count"], 0)
                self.assertEqual(len(self.cache.get(key)), len(baseline) + 13)
                self.assertEqual(self.incremental._load_pending_records(self.cache, source), [])
                self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), set())
                self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], later.isoformat())
                self.assertEqual(len([write for write in self.cache.writes if write[0] == key]), 1)
                publish.assert_called_once()

    def test_budget_deferred_periodic_recheck_remains_carryover_eligible(self):
        source = "tjzyefy"
        key, _, prior = self.seed_source(source)
        candidates, rows = self.fixture(source, 13)
        self.cache.set(key, list(rows.values()))
        ledger = self.planner.empty_ledger()
        for candidate in candidates:
            ledger = self.planner.record_verification_success(
                ledger, self.planner.candidate_observation(source, candidate), verified_at=self.now - timedelta(days=2),
            )
        self.incremental._save_ledger(self.cache, source, ledger)
        with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates}), patch.dict(
            self.incremental._VERIFICATION, {source: self.verifier(rows)},
        ), patch.object(self.incremental, "_publish_snapshot_if_ready", return_value=(False, None)) as publish:
            self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
            entry = self.incremental._load_ledger(self.cache, source)["entries"][self.planner.ledger_key(
                self.planner.candidate_observation(source, candidates[-1]),
            )]
            self.assertEqual(entry["verification_status"], "UNVERIFIED")
            self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], prior.isoformat())
            publish.assert_not_called()
            with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates[:12]}):
                status, result = self.incremental.run_incremental_source(source, now=self.now + timedelta(hours=1, minutes=1), cache=self.cache)
        self.assertEqual(status, 200)
        self.assertEqual(result["selected_detail_count"], 1)
        self.assertEqual(len(self.cache.get(key)), 13)
        self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), set())
        publish.assert_called_once()

    def test_twenty_candidates_commit_only_after_all_eight_carryovers_are_verified(self):
        source = "tjzyefy"
        key, baseline, _ = self.seed_source(source)
        candidates, rows = self.fixture(source, 20)
        with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates}), patch.dict(
            self.incremental._VERIFICATION, {source: self.verifier(rows)},
        ), patch.object(self.incremental, "_publish_snapshot_if_ready", return_value=(False, None)) as publish:
            _, first = self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
            self.assertEqual(first["deferred_detail_count"], 8)
            self.assertEqual(self.cache.get(key), baseline)
            self.assertEqual(len(self.incremental._load_pending_records(self.cache, source)), 12)
            self.assertEqual(len(self.incremental._load_pending_barrier(self.cache, source)), 8)
            publish.assert_not_called()
            later = self.now + timedelta(hours=1, minutes=1)
            with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates[:12]}):
                status, result = self.incremental.run_incremental_source(source, now=later, cache=self.cache)
        self.assertEqual(status, 200)
        self.assertEqual(result["selected_detail_count"], 8)
        self.assertEqual(result["deferred_detail_count"], 0)
        self.assertEqual(len(self.cache.get(key)), len(baseline) + 20)
        self.assertEqual(len([write for write in self.cache.writes if write[0] == key]), 1)
        publish.assert_called_once()
        # A subsequent capped deep scan must not reopen already proven URLs.
        with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates}):
            with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "EARLY_SIGNAL_DETAIL_BUDGET_DEFERRED"):
                self.runtime._run_early_signal_source(self.cache, {"cycle_as_of": later.isoformat()}, source)
        self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), set())
        self.assertTrue(all(row["verification_status"] == "VERIFIED"
                            for row in self.incremental._load_ledger(self.cache, source)["entries"].values()))

    def test_hard_stop_preserves_fact_or_nonfact_proof_before_ledger_can_skip_it(self):
        for first_nonfact in (False, True):
            with self.subTest(first_nonfact=first_nonfact):
                source = "tjzxfc"
                key, baseline, prior = self.seed_source(source)
                candidates, rows = self.fixture(source, 2)
                verify_record = self.verifier(rows)

                def interrupt_on_second(candidate, observed_at, now):
                    if candidate.detail_url == candidates[0].detail_url:
                        return None if first_nonfact else verify_record(candidate, observed_at, now)
                    raise KeyboardInterrupt("simulated worker hard stop")

                with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates}), patch.dict(
                    self.incremental._VERIFICATION, {source: interrupt_on_second},
                ), patch.object(self.incremental, "_publish_snapshot_if_ready", return_value=(False, None)) as publish:
                    with self.assertRaises(KeyboardInterrupt):
                        self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
                    self.assertEqual(self.cache.get(key), baseline)
                    self.assertEqual(len(self.incremental._load_pending_records(self.cache, source)), 0 if first_nonfact else 1)
                    self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), {candidates[1].detail_url})
                    self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], prior.isoformat())
                    publish.assert_not_called()
                    retry_verifier = verify_record if first_nonfact else lambda *args: None
                    with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates[:1]}), patch.dict(
                        self.incremental._VERIFICATION, {source: retry_verifier},
                    ):
                        status, result = self.incremental.run_incremental_source(source, now=self.now + timedelta(minutes=1), cache=self.cache)
                self.assertEqual(status, 200)
                self.assertEqual(result["selected_detail_count"], 1)
                self.assertEqual(result["skipped_unchanged_count"], 1)
                self.assertEqual(len(self.cache.get(key)), len(baseline) + 1)
                self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), set())
                self.assertEqual(self.incremental._load_pending_records(self.cache, source), [])
                self.assertEqual(len([write for write in self.cache.writes if write[0] == key]), 1)
                publish.assert_called_once()

    def test_deferred_barrier_survives_a_later_empty_scan_beyond_carryover_age(self):
        source = "tjzyefy"
        key, baseline, prior = self.seed_source(source)
        candidates, rows = self.fixture(source, 13)
        with patch.dict(self.incremental._DISCOVERY, {source: lambda now: candidates}), patch.dict(
            self.incremental._VERIFICATION, {source: self.verifier(rows)},
        ), patch.object(self.incremental, "_publish_snapshot_if_ready") as publish:
            self.incremental.run_incremental_source(source, now=self.now, cache=self.cache)
            with patch.dict(self.incremental._DISCOVERY, {source: lambda now: []}):
                _, result = self.incremental.run_incremental_source(source, now=self.now + timedelta(hours=49), cache=self.cache)
        self.assertEqual(result["deferred_reason"], "PENDING_VERIFICATION_BARRIER")
        self.assertEqual(self.cache.get(key), baseline)
        self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), {candidates[-1].detail_url})
        self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], prior.isoformat())
        publish.assert_not_called()

    def test_deep_thirteen_blocks_without_network_or_partial_canonical_and_keeps_urls(self):
        for source in ("tjzyefy", "tjzyefy_intent", "tjzxfc"):
            with self.subTest(source=source):
                key, baseline, prior = self.seed_source(source)
                candidates, _ = self.fixture(source, 13)
                state = {"local_date": "2026-10-01", "cycle_as_of": self.now.isoformat(),
                         "stages": {source: {"status": "RUNNING", "attempt_count": 1}}}
                self.cache.set(self.runtime.META_KEY, state)
                with patch.object(self.runtime, "_prepare_stage", return_value=(state, None)), patch.dict(
                    self.incremental._DISCOVERY, {source: lambda now: candidates},
                ), patch.dict(self.incremental._VERIFICATION, {source: unittest.mock.Mock()}) as verification, patch.object(
                    self.runtime, "_now_utc", return_value=self.now,
                ):
                    status, result = self.runtime.run_stage(source, now=self.now)
                    self.incremental._VERIFICATION[source].assert_not_called()
                self.assertEqual(status, 503)
                self.assertEqual(result["error"], "EARLY_SIGNAL_DETAIL_BUDGET_DEFERRED")
                self.assertEqual(self.cache.get(key), baseline)
                self.assertEqual(self.incremental._load_pending_barrier(self.cache, source), {row.detail_url for row in candidates})
                self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], prior.isoformat())

    def test_deep_twelve_keeps_normal_commit_and_complete_clock(self):
        source = "tjzyefy"
        key, baseline, _ = self.seed_source(source)
        candidates, rows = self.fixture(source, 12)
        state = {"local_date": "2026-10-01", "cycle_as_of": self.now.isoformat(),
                 "stages": {source: {"status": "RUNNING", "attempt_count": 1}}}
        self.cache.set(self.runtime.META_KEY, state)
        with patch.object(self.runtime, "_prepare_stage", return_value=(state, None)), patch.dict(
            self.incremental._DISCOVERY, {source: lambda now: candidates},
        ), patch.dict(self.incremental._VERIFICATION, {source: self.verifier(rows)}), patch.object(
            self.runtime, "_now_utc", return_value=self.now,
        ):
            status, result = self.runtime.run_stage(source, now=self.now)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["selected_candidate_count"], 12)
        self.assertEqual(result["result"]["deferred_detail_count"], 0)
        self.assertEqual(len(self.cache.get(key)), len(baseline) + 12)
        self.assertEqual(self.runtime.snapshot_source_health(self.cache)["sources"][source]["last_successful_scan_at"], self.now.isoformat())


if __name__ == "__main__":
    unittest.main()
