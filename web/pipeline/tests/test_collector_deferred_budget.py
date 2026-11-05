from __future__ import annotations

import copy
import importlib
import json
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
