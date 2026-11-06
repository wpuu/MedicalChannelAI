from __future__ import annotations

import asyncio
import copy
import importlib
import importlib.util
import socket
import sys
import types
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return copy.deepcopy(self.values.get(key))

    def set(self, key: str, value, options=None) -> None:
        self.values[key] = copy.deepcopy(value)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class CollectorOrchestrationBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache = MemoryCache()
        self.sent: list[dict] = []
        self.accepted: set[str] = set()
        functions = types.ModuleType("vercel.functions")
        functions.RuntimeCache = lambda *args, **kwargs: self.cache
        queue = types.ModuleType("vercel.queue")

        async def send(topic, payload, **options):
            self.sent.append({"topic": topic, "payload": payload, **options})
            self.accepted.add(options["idempotency_key"])
            return options["idempotency_key"]

        queue.send = send
        self.modules = patch.dict(sys.modules, {
            "vercel": types.ModuleType("vercel"),
            "vercel.functions": functions,
            "vercel.queue": queue,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        for name in ("collector_runtime", "collector_queue", "collector_incremental_runtime", "collector_incremental_bootstrap"):
            sys.modules.pop(name, None)
        self.runtime = importlib.import_module("collector_runtime")
        self.worker = importlib.import_module("collector_queue")
        spec = importlib.util.spec_from_file_location("collector_run_behavior", WEB_ROOT / "api" / "collector-run.py")
        self.trigger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.trigger)
        self.now = datetime(2026, 11, 5, 0, 20, tzinfo=timezone.utc)
        # asyncio needs its local socketpair; block connections/DNS, not creation.
        for owner, name in ((socket.socket, 'connect'), (socket, 'create_connection'),
                            (socket, 'getaddrinfo'), (urllib.request, 'build_opener')):
            blocker = patch.object(owner, name, side_effect=AssertionError('NETWORK_OR_REAL_CLIENT_FORBIDDEN'))
            blocker.start()
            self.addCleanup(blocker.stop)

    def cycle_payload(self, stage: str) -> dict:
        self.cache.set(self.worker.ACTIVE_CYCLE_KEY, {"cycle_id": "current"})
        return {"schema_version": "0.1", "stage": stage, "cycle_as_of": self.now.isoformat(), "cycle_id": "current"}

    def incremental_payload(self, source="tjzyefy"):
        return {"schema_version": "0.1", "mode": "incremental", "source_id": source,
                "observed_at": self.now.isoformat(),
                "scan_bucket_id": self.worker.incremental_runtime.scan_bucket_id(source, now=self.now)}

    def test_tjzyefy_budget_keeps_entry_origin_through_lease_and_ignores_payload_deadline(self):
        payload = self.incremental_payload()
        payload["deadline"] = 99999999
        tick, seen = [0.0], []
        fixed_now = self.now
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return fixed_now
        def acquire(*args, **kwargs):
            tick[0] = 175
            return "synthetic-scan"
        def run(source, **kwargs):
            b = kwargs["budget"]
            seen.append((b.started, b.request_timeout(30, "READ"), b.snapshot()))
            return 503, {"error": "OFFLINE_TIME_STOP"}
        with patch.object(self.worker, "datetime", Clock), patch.object(self.worker, "_acquire_incremental_lease", side_effect=acquire), patch.object(
            self.worker, "_release_incremental_lease") as release, patch.object(
            self.worker.incremental_runtime, "run_incremental_source", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "INCREMENTAL_QUEUE_SCAN_FAILED"):
                asyncio.run(self.worker.process_collector_payload(payload, monotonic=lambda: tick[0], sleep=lambda d: None))
        self.assertEqual(seen[0][:2], (0, 4))
        self.assertEqual(seen[0][2]["total_seconds"], 270)
        self.assertEqual(seen[0][2]["work_seconds"], 180)
        release.assert_called_once_with(self.cache, "synthetic-scan")
        self.assertFalse(self.sent)

    def test_tjzyefy_guards_and_owner_denial_never_enter_runner(self):
        fixed_now = self.now
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return fixed_now
        for mode in ("foreign", "bucket", "day", "owner"):
            with self.subTest(mode=mode):
                payload = self.incremental_payload()
                if mode == "bucket": payload["scan_bucket_id"] = "wrong"
                if mode == "day": payload["observed_at"] = (self.now - timedelta(days=1)).isoformat()
                with patch.object(self.worker, "datetime", Clock), patch.object(self.worker, "accepts_payload", return_value=mode != "foreign"), patch.object(
                    self.worker, "_acquire_incremental_lease", side_effect=RuntimeError("INCREMENTAL_SCAN_ALREADY_RUNNING")) as acquire, patch.object(
                    self.worker.incremental_runtime, "run_incremental_source") as run:
                    if mode == "owner":
                        with self.assertRaisesRegex(RuntimeError, "INCREMENTAL_SCAN_ALREADY_RUNNING"):
                            asyncio.run(self.worker.process_collector_payload(payload))
                    else:
                        asyncio.run(self.worker.process_collector_payload(payload))
                        acquire.assert_not_called()
                run.assert_not_called()

    def test_other_incremental_sources_keep_original_dispatch_without_budget(self):
        payload = self.incremental_payload("tjzyefy_intent")
        with patch.object(self.worker, "_process_incremental_payload") as process:
            asyncio.run(self.worker.process_collector_payload(payload))
        process.assert_called_once_with(payload)

    def test_tjzyefy_lease_release_failure_preserves_known_scan_result(self):
        payload = self.incremental_payload()
        fixed_now = self.now
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return fixed_now
        with patch.object(self.worker, "datetime", Clock), patch.object(self.worker, "_acquire_incremental_lease", return_value="scan"), patch.object(
            self.worker, "_release_incremental_lease", side_effect=OSError("SYNTHETIC_RELEASE")), patch.object(
            self.worker.incremental_runtime, "run_incremental_source", return_value=(200, {"action": "COMPLETED", "snapshot_refreshed": True})):
            with self.assertRaises(self.runtime.CollectorStageBlocked) as caught:
                asyncio.run(self.worker.process_collector_payload(payload))
        self.assertTrue(caught.exception.diagnostics["lease_mutation_possible"])
        self.assertTrue(caught.exception.diagnostics["scan_result"]["snapshot_refreshed"])

    def test_tjzyefy_lease_acquire_io_error_is_unknown_and_never_runs_source(self):
        payload = self.incremental_payload()
        fixed_now = self.now
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return fixed_now
        with patch.object(self.worker, "datetime", Clock), patch.object(self.worker, "_acquire_incremental_lease", side_effect=OSError("SYNTHETIC_ACQUIRE")), patch.object(
            self.worker.incremental_runtime, "run_incremental_source") as run:
            with self.assertRaises(self.runtime.CollectorStageBlocked) as caught:
                asyncio.run(self.worker.process_collector_payload(payload))
        self.assertTrue(caught.exception.diagnostics["lease_mutation_possible"])
        run.assert_not_called()

    def test_cron_seeds_intraday_before_deep_can_fail(self) -> None:
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 5, 0, 20, tzinfo=timezone.utc)

        with patch.object(self.trigger, "datetime", Clock):
            asyncio.run(self.trigger._enqueue_start("VERCEL_CRON"))
        self.assertEqual(self.sent[0]["payload"]["mode"], "incremental_tick")
        self.assertEqual(self.sent[1]["payload"]["stage"], "ccgp")
        self.assertIsNotNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))

    def test_deep_enqueue_failure_releases_only_its_owner_and_keeps_tick(self) -> None:
        async def failed_deep(*args, **kwargs):
            raise RuntimeError("QUEUE_UNAVAILABLE")

        fixed_now = self.now

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        with patch.object(self.trigger, "send", failed_deep), patch.object(self.trigger, "datetime", Clock):
            with self.assertRaisesRegex(RuntimeError, "QUEUE_UNAVAILABLE"):
                asyncio.run(self.trigger._enqueue_start("VERCEL_CRON"))
        self.assertIsNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))
        self.assertTrue(any(item["payload"].get("mode") == "incremental_tick" for item in self.sent))

    def test_ensuring_same_tick_is_idempotent(self) -> None:
        asyncio.run(self.worker.ensure_intraday_chain(now=self.now))
        asyncio.run(self.worker.ensure_intraday_chain(now=self.now))
        self.assertEqual(len(self.accepted), 1)

    def test_source_retry_exhaustion_marks_degraded_and_runs_next_source(self) -> None:
        stage = "tjmugh"
        self.cache.set(self.worker.META_KEY, {
            "local_date": "2026-11-05", "cycle_as_of": self.now.isoformat(),
            "stages": {stage: {"status": "FAILED", "attempt_count": self.runtime.MAX_STAGE_ATTEMPTS_PER_DAY}},
        })
        old = [{"opportunity_id": "last_verified"}]
        self.cache.set(self.runtime.TJMUGH_RECORDS_KEY, old)
        payload = self.cycle_payload(stage)
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "run_stage", return_value=(409, {"error": f"COLLECTOR_STAGE_RETRY_LIMIT:{stage}"}),
        ):
            asyncio.run(self.worker.process_collector_payload(payload))
        state = self.cache.get(self.worker.META_KEY)
        self.assertEqual(state["stages"][stage]["status"], "DEGRADED")
        self.assertEqual(self.cache.get(self.runtime.TJMUGH_RECORDS_KEY), old)
        self.assertEqual(self.sent[-1]["payload"]["stage"], "tjnothop")
        self.assertEqual(self.sent[-1]["payload"]["cycle_as_of"], self.now.isoformat())
        self.assertIsNotNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))
        following = self.sent[-1]["payload"]
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "_run_tjnothop", return_value={"new_verified_record_count": 0},
        ):
            asyncio.run(self.worker.process_collector_payload(following))
        self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["tjnothop"]["status"], "COMPLETED")

    def seed_retry(self, stage, attempts):
        self.cache.set(self.worker.META_KEY, {
            "local_date": self.now.date().isoformat(), "cycle_as_of": self.now.isoformat(),
            "stages": {**{name: {"status": "COMPLETED"} for name in self.worker.STAGE_ORDER[:self.worker.STAGE_ORDER.index(stage)]},
                       stage: {"status": "FAILED", "attempt_count": attempts}},
        })
        self.cache.set(self.runtime.TJMUGH_RECORDS_KEY, [{"opportunity_id": "last_verified"}])
        return self.cycle_payload(stage)

    def test_first_transient_failure_keeps_real_retry_and_canonical(self):
        payload = self.seed_retry("tjmugh", 0)
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "_run_tjmugh", side_effect=TimeoutError("temporary")):
            with self.assertRaisesRegex(RuntimeError, "COLLECTOR_QUEUE_STAGE_FAILED"):
                asyncio.run(self.worker.process_collector_payload(payload))
        row = self.cache.get(self.worker.META_KEY)["stages"]["tjmugh"]
        self.assertEqual((row["status"], row["attempt_count"]), ("FAILED", 1))
        self.assertEqual(self.sent, [])
        self.assertEqual(self.cache.get(self.runtime.TJMUGH_RECORDS_KEY), [{"opportunity_id": "last_verified"}])

    def test_regional_budget_uses_queue_entry_origin_after_preflight(self):
        for stage in ('regional_he', 'regional_he_fallback'):
            with self.subTest(stage=stage):
                payload = self.seed_retry(stage, 0)
                tick = [0.0]
                seen = []
                def active(*args, **kwargs):
                    tick[0] = 205
                    return True
                def run(stage, **kwargs):
                    budget = kwargs['budget']
                    seen.append((budget.started, budget.request_timeout(90, 'READ'), budget.snapshot()))
                    return 503, {'retryable':True,'retry_exhausted':False,'error':'OFFLINE_TRANSIENT'}
                with patch.object(self.worker,'_active_cycle_matches',side_effect=active), patch.object(
                    self.worker,'_heartbeat_deep_cycle',return_value=True), patch.object(self.runtime,'run_stage',side_effect=run):
                    with self.assertRaisesRegex(RuntimeError,'COLLECTOR_QUEUE_STAGE_FAILED'):
                        asyncio.run(self.worker.process_collector_payload(payload,monotonic=lambda:tick[0],sleep=lambda d:None))
                self.assertEqual(seen[0][:2],(0,4))
                self.assertEqual([seen[0][2][k] for k in ('total_seconds','work_seconds','finalize_reserve_seconds')],[270,210,60])

    def test_regional_budget_failure_retries_then_degrades_without_third_scan(self):
        stage = 'regional_he'
        payload = self.seed_retry(stage, 0)
        key = self.runtime._regional_records_key('HE')
        self.cache.set(key, [])
        tick = [0.0]
        def active(*args, **kwargs):
            tick[0] = 210
            return True
        def work(cache, state, stage, *, budget):
            budget.check('REGIONAL_SCOPED')
        with patch.object(self.worker,'_active_cycle_matches',side_effect=active), patch.object(
            self.worker,'_heartbeat_deep_cycle',return_value=True), patch.object(self.runtime,'_run_regional_market',side_effect=work) as scan:
            with self.assertRaisesRegex(RuntimeError,'COLLECTOR_QUEUE_STAGE_FAILED'):
                asyncio.run(self.worker.process_collector_payload(payload,monotonic=lambda:tick[0],sleep=lambda d:None))
            first = self.cache.get(self.worker.META_KEY)['stages'][stage]
            self.assertEqual((first['status'],first['attempt_count']),('FAILED',1))
            self.assertEqual(self.sent,[])
            tick[0] = 0
            asyncio.run(self.worker.process_collector_payload(payload,monotonic=lambda:tick[0],sleep=lambda d:None))
            final = self.cache.get(self.worker.META_KEY)['stages'][stage]
            self.assertEqual((final['status'],final['attempt_count']),('DEGRADED',2))
            self.assertEqual(self.sent[-1]['payload']['stage'],'regional_he_fallback')
            tick[0] = 0
            asyncio.run(self.worker.process_collector_payload(payload,monotonic=lambda:tick[0],sleep=lambda d:None))
            self.assertEqual(scan.call_count,2)
            self.assertEqual(self.cache.get(self.worker.META_KEY)['stages'][stage],final)
            tick[0] = 0
            asyncio.run(self.worker.process_collector_payload(self.sent[-1]['payload'],monotonic=lambda:tick[0],sleep=lambda d:None))
            self.assertEqual(scan.call_count,2)
            self.assertEqual(self.sent[-1]['payload']['stage'],'regional_ln')
        self.assertEqual(self.cache.get(key),[])

    def test_nonregional_stages_keep_original_run_stage_arguments(self):
        for stage in ('tjmugh','event1','publish'):
            with self.subTest(stage=stage):
                payload=self.seed_retry(stage,0)
                with patch.object(self.worker,'_active_cycle_matches',return_value=True), patch.object(
                    self.worker,'_heartbeat_deep_cycle',return_value=True), patch.object(self.runtime,'run_stage',
                    return_value=(200,{'action':'ALREADY_COMPLETED_TODAY'})) as run, patch.object(
                    self.worker,'ensure_intraday_chain',new=AsyncMock()), patch.object(
                    self.worker.incremental_runtime,'reconcile_incremental_pending_from_canonical',return_value={}):
                    asyncio.run(self.worker.process_collector_payload(payload))
                self.assertEqual(set(run.call_args.kwargs),{'now'})

    def test_foreign_payload_budget_path_has_no_cache_or_stage_effect(self):
        payload=self.cycle_payload('regional_he')
        with patch.object(self.worker,'accepts_payload',return_value=False), patch.object(
            self.worker,'RuntimeCache',side_effect=AssertionError('CACHE_FORBIDDEN')), patch.object(self.runtime,'run_stage') as run:
            asyncio.run(self.worker.process_collector_payload(payload))
        run.assert_not_called()

    def test_regional_owner_rejection_never_runs_budgeted_work(self):
        payload=self.cycle_payload('regional_he')
        with patch.object(self.worker,'_active_cycle_matches',return_value=False), patch.object(
            self.worker,'_heartbeat_deep_cycle') as heartbeat, patch.object(self.runtime,'run_stage') as run:
            asyncio.run(self.worker.process_collector_payload(payload))
        run.assert_not_called()
        heartbeat.assert_not_called()

    def test_incremental_dispatch_does_not_get_regional_budget(self):
        payload={'schema_version':'0.1','mode':'incremental_source','source_id':'tjzyefy'}
        with patch.object(self.worker,'_is_incremental_payload',return_value=True), patch.object(
            self.worker,'_process_incremental_payload') as process, patch.object(self.runtime,'run_stage') as run:
            asyncio.run(self.worker.process_collector_payload(payload))
        self.assertEqual(process.call_args.args, (payload,))
        self.assertEqual(process.call_args.kwargs["budget"].work_seconds, 180)
        run.assert_not_called()

    def test_last_actual_failure_degrades_and_advances_without_another_delivery(self):
        payload = self.seed_retry("tjmugh", 1)
        diagnostics = {"failure_count": 1, "reason_counts": {"NETWORK_TIMEOUT": 1}, "samples": []}
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "_run_tjmugh", side_effect=self.runtime.CollectorStageBlocked("SOURCE_FAILED", diagnostics=diagnostics)), patch.object(
            self.runtime, "_now_utc", return_value=self.now):
            asyncio.run(self.worker.process_collector_payload(payload))
        row = self.cache.get(self.worker.META_KEY)["stages"]["tjmugh"]
        self.assertEqual((row["status"], row["attempt_count"]), ("DEGRADED", 2))
        self.assertEqual(row["failed_at"], self.now.isoformat())
        self.assertEqual(row["diagnostics"], diagnostics)
        self.assertEqual(row["error_message"], "SOURCE_FAILED")
        self.assertEqual(self.sent[-1]["payload"]["stage"], "tjnothop")
        self.assertEqual(self.sent[-1]["delay"], self.worker.NEXT_STAGE_DELAY_SECONDS)
        self.assertIsNotNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))

    def test_enqueue_failure_replay_resumes_terminal_stage_without_refetch(self):
        payload = self.seed_retry("tjmugh", 1)
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "_run_tjmugh", side_effect=TimeoutError("temporary")) as scan, patch.object(
            self.worker, "send", new_callable=AsyncMock, side_effect=[RuntimeError("send failed"), "next-id"]) as send:
            with self.assertRaisesRegex(RuntimeError, "send failed"):
                asyncio.run(self.worker.process_collector_payload(payload))
            before = self.cache.get(self.worker.META_KEY)["stages"]["tjmugh"]
            asyncio.run(self.worker.process_collector_payload(payload))
            scan.assert_called_once()
            self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["tjmugh"], before)
            self.assertEqual(send.await_args_list[0], send.await_args_list[1])

    def test_nonretryable_terminal_redelivery_does_not_spend_a_second_attempt(self):
        payload = self.seed_retry("teda", 0)
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "_run_teda", side_effect=self.runtime.CollectorStageBlocked("TEDA_HTTP_403", retryable=False)) as scan:
            asyncio.run(self.worker.process_collector_payload(payload))
            first = self.cache.get(self.worker.META_KEY)["stages"]["teda"]
            asyncio.run(self.worker.process_collector_payload(payload))
            scan.assert_called_once()
        self.assertEqual(first["attempt_count"], 1)
        self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["teda"], first)

    def test_last_publish_failure_releases_owner_and_remains_failed_immediately(self):
        payload = self.seed_retry("publish", 1)
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "_run_publish", side_effect=RuntimeError("DATABASE_UNAVAILABLE")):
            asyncio.run(self.worker.process_collector_payload(payload))
        row = self.cache.get(self.worker.META_KEY)["stages"]["publish"]
        self.assertEqual((row["status"], row["attempt_count"]), ("FAILED", 2))
        self.assertIsNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))
        self.assertEqual(self.sent, [])
        self.assertIsNone(self.cache.get(self.runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY))

    def test_explicit_legacy_recovery_exceptions_still_allow_their_extra_attempt(self):
        for stage, function, error in [
            ("tjfch", "_run_tjfch", "TJFCH_NOTICE_TYPE_UNSUPPORTED"),
            ("publish", "_run_publish", "COLLECTOR_CANONICAL_STATE_INCOMPLETE:regional_bj"),
        ]:
            with self.subTest(stage=stage):
                self.seed_retry(stage, 1)
                with patch.object(self.runtime, function, side_effect=RuntimeError(error)):
                    status, result = self.runtime.run_stage(stage, now=self.now)
                self.assertEqual(status, 503)
                self.assertFalse(result["retry_exhausted"])
                with patch.object(self.runtime, function, return_value={"failure_count": 0}):
                    status, result = self.runtime.run_stage(stage, now=self.now)
                self.assertEqual(status, 200)
                self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"][stage]["attempt_count"], 3)

    def test_superseded_owner_after_failure_cannot_degrade_or_enqueue(self):
        payload = self.seed_retry("tjmugh", 1)
        def lose_owner(*args):
            self.cache.set(self.worker.ACTIVE_CYCLE_KEY, {"cycle_id": "new-owner"})
            raise TimeoutError("temporary")
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "_run_tjmugh", side_effect=lose_owner):
            asyncio.run(self.worker.process_collector_payload(payload))
        self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["tjmugh"]["status"], "FAILED")
        self.assertEqual(self.cache.get(self.worker.ACTIVE_CYCLE_KEY)["cycle_id"], "new-owner")
        self.assertEqual(self.sent, [])

    def test_degraded_regional_primary_skips_fallback_without_fetch_or_retry(self):
        self.cache.set(self.worker.META_KEY, {
            "local_date": "2026-11-05", "cycle_as_of": self.now.isoformat(),
            "stages": {"regional_ln": {"status": "DEGRADED", "attempt_count": 2}},
        })
        payload = self.cycle_payload("regional_ln_fallback")
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "_run_regional_market", side_effect=AssertionError("must not fetch dependency")), patch.object(
            self.runtime, "run_stage", side_effect=AssertionError("must not schedule futile attempt")):
            asyncio.run(self.worker.process_collector_payload(payload))
        row = self.cache.get(self.worker.META_KEY)["stages"]["regional_ln_fallback"]
        self.assertEqual(row["status"], "DEGRADED")
        self.assertEqual(row["degraded_reason"], "COLLECTOR_DEPENDENCY_DEGRADED")
        self.assertEqual(row["attempt_count"], 1)
        self.assertEqual(self.sent[-1]["payload"]["stage"], "regional_jl")

    def test_nonterminal_regional_primary_does_not_get_terminally_skipped(self):
        for primary_status in ("FAILED", "RUNNING"):
            self.cache.set(self.worker.META_KEY, {"stages": {"regional_ln": {"status": primary_status}}})
            payload = self.cycle_payload("regional_ln_fallback")
            with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
                self.runtime, "run_stage", return_value=(503, {"error": "UPSTREAM_NOT_READY"})) as run:
                with self.assertRaisesRegex(RuntimeError, "UPSTREAM_NOT_READY"):
                    asyncio.run(self.worker.process_collector_payload(payload))
            run.assert_called_once()

    def test_explicit_access_denial_degrades_once_and_advances(self):
        self.cache.set(self.worker.META_KEY, {"stages": {"teda": {"status": "FAILED", "attempt_count": 1}}})
        payload = self.cycle_payload("teda")
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "run_stage", return_value=(503, {"retryable": False, "error": "TEDA_HTTP_403"})):
            asyncio.run(self.worker.process_collector_payload(payload))
        self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["teda"]["status"], "DEGRADED")
        self.assertEqual(self.sent[-1]["payload"]["stage"], "tjfch")

    def test_completed_deep_keeps_uncovered_pending_barrier(self) -> None:
        incremental = self.worker.incremental_runtime
        unresolved = "https://www.tjmugh.com.cn/unresolved-detail"
        incremental._save_pending_barrier(self.cache, "tjmugh", {unresolved})
        self.cache.set(self.runtime.TJMUGH_RECORDS_KEY, [])
        payload = self.cycle_payload("publish")
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "run_stage", return_value=(200, {"action": "COMPLETED"}),
        ), patch.object(self.worker, "ensure_intraday_chain", new_callable=AsyncMock) as ensure:
            asyncio.run(self.worker.process_collector_payload(payload))
        self.assertEqual(incremental._load_pending_barrier(self.cache, "tjmugh"), {unresolved})
        self.assertIsNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))
        ensure.assert_awaited_once()

    def test_failed_ccgp_dependency_skips_event_network_and_reaches_healthy_source(self) -> None:
        self.cache.set(self.worker.META_KEY, {
            "local_date": "2026-11-05", "cycle_as_of": self.now.isoformat(),
            "stages": {"ccgp": {"status": "DEGRADED", "attempt_count": 2}},
        })
        payload = self.cycle_payload("event1")
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "_run_event_batch", side_effect=AssertionError("dependent official fetch must not run"),
        ):
            for index in range(1, 7):
                self.assertEqual(payload["stage"], f"event{index}")
                asyncio.run(self.worker.process_collector_payload(payload))
                payload = self.sent[-1]["payload"]
        self.assertEqual(payload["stage"], "tjmugh")
        stages = self.cache.get(self.worker.META_KEY)["stages"]
        self.assertTrue(all(stages[f"event{index}"]["status"] == "DEGRADED" for index in range(1, 7)))

    def test_superseded_cycle_never_executes_a_stage(self) -> None:
        payload = self.cycle_payload("tjmugh")
        self.cache.set(self.worker.ACTIVE_CYCLE_KEY, {"cycle_id": "new-owner"})
        with patch.object(self.runtime, "run_stage") as run:
            asyncio.run(self.worker.process_collector_payload(payload))
        run.assert_not_called()
        self.assertEqual(self.sent, [])

    def test_failed_publish_releases_owner_without_claiming_success(self) -> None:
        payload = self.cycle_payload("publish")
        self.cache.set(self.worker.META_KEY, {"stages": {"publish": {"status": "FAILED"}}})
        with patch.object(self.worker, "_active_cycle_matches", return_value=True), patch.object(
            self.runtime, "run_stage", return_value=(409, {"error": "COLLECTOR_STAGE_RETRY_LIMIT:publish"}),
        ):
            asyncio.run(self.worker.process_collector_payload(payload))
        self.assertIsNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))
        self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["publish"]["status"], "FAILED")
        self.assertEqual(self.sent, [])

    def running_state(self, *, wall_age: timedelta, frozen_age: timedelta = timedelta(hours=5)) -> dict:
        return {
            "local_date": "2026-11-05", "cycle_as_of": (self.now - frozen_age).isoformat(),
            "updated_at": (self.now - wall_age).isoformat(),
            "stages": {"ccgp": {
                "status": "RUNNING", "attempt_count": 1,
                "started_at": (self.now - frozen_age).isoformat(),
                "wall_started_at": (self.now - wall_age).isoformat(),
            }},
        }

    def test_recent_wall_execution_is_not_expired_by_frozen_cycle_clock(self) -> None:
        self.cache.set(self.worker.META_KEY, self.running_state(wall_age=timedelta(minutes=2)))
        with self.assertRaises(self.trigger.CollectorStartConflict):
            self.trigger._activate_cycle(self.cache, cycle_id="new", now=self.now, local_date="2026-11-05", source="CRON")
        self.assertIsNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))

    def test_recent_heartbeat_protects_long_deep_cycle_despite_old_collection_clock(self) -> None:
        self.cache.set(self.worker.META_KEY, self.running_state(wall_age=timedelta(hours=2)))
        self.cache.set(self.worker.ACTIVE_CYCLE_KEY, {
            "cycle_id": "live-owner", "local_date": "2026-11-05",
            "activated_at": (self.now - timedelta(hours=5)).isoformat(),
            "wall_heartbeat_at": (self.now - timedelta(minutes=2)).isoformat(),
        })
        with self.assertRaises(self.trigger.CollectorStartConflict):
            self.trigger._activate_cycle(self.cache, cycle_id="new", now=self.now, local_date="2026-11-05", source="CRON")
        self.assertEqual(self.cache.get(self.worker.ACTIVE_CYCLE_KEY)["cycle_id"], "live-owner")

    def test_recent_stage_wall_update_keeps_legacy_long_cycle_owner_live(self) -> None:
        self.cache.set(self.worker.META_KEY, self.running_state(wall_age=timedelta(minutes=2)))
        self.cache.set(self.worker.ACTIVE_CYCLE_KEY, {
            "cycle_id": "legacy-live", "local_date": "2026-11-05",
            "cycle_as_of": (self.now - timedelta(hours=5)).isoformat(),
        })
        with self.assertRaises(self.trigger.CollectorStartConflict):
            self.trigger._activate_cycle(self.cache, cycle_id="new", now=self.now, local_date="2026-11-05", source="CRON")
        self.assertEqual(self.cache.get(self.worker.ACTIVE_CYCLE_KEY)["cycle_id"], "legacy-live")

    def test_each_deep_stage_renews_wall_heartbeat_without_changing_frozen_clock(self) -> None:
        payload = self.cycle_payload("tjmugh")
        original = self.now - timedelta(hours=5)
        payload["cycle_as_of"] = original.isoformat()
        self.cache.set(self.worker.ACTIVE_CYCLE_KEY, {
            "cycle_id": "current", "local_date": "2026-11-05",
            "activated_at": original.isoformat(),
            "cycle_as_of": original.isoformat(),
            "wall_heartbeat_at": (self.now - timedelta(minutes=2)).isoformat(),
        })
        fixed_now = self.now

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        with patch.object(self.worker, "datetime", Clock), patch.object(
            self.runtime, "run_stage", return_value=(200, {"action": "COMPLETED"}),
        ):
            asyncio.run(self.worker.process_collector_payload(payload))
        active = self.cache.get(self.worker.ACTIVE_CYCLE_KEY)
        self.assertEqual(active["wall_heartbeat_at"], self.now.isoformat())
        self.assertEqual(active["cycle_as_of"], original.isoformat())
        self.assertEqual(self.sent[-1]["payload"]["cycle_as_of"], original.isoformat())

    def test_expired_publish_owner_is_failed_instead_of_degraded_or_completed(self) -> None:
        state = self.running_state(wall_age=timedelta(hours=2))
        state["stages"]["publish"] = state["stages"].pop("ccgp")
        self.cache.set(self.worker.META_KEY, state)
        self.cache.set(self.worker.ACTIVE_CYCLE_KEY, {
            "cycle_id": "expired-publish", "local_date": "2026-11-05",
            "wall_heartbeat_at": (self.now - timedelta(hours=2)).isoformat(),
        })
        self.assertTrue(self.worker.recover_expired_deep_cycle(self.cache, now=self.now))
        self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["publish"]["status"], "FAILED")
        self.assertIsNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))

    def test_hard_timeout_with_owner_key_still_present_recovers_and_fences_old_delivery(self) -> None:
        self.cache.set(self.worker.META_KEY, self.running_state(wall_age=timedelta(hours=2)))
        old_id = "prod:2026-11-05"
        self.cache.set(self.worker.ACTIVE_CYCLE_KEY, {
            "cycle_id": old_id, "local_date": "2026-11-05",
            "activated_at": (self.now - timedelta(hours=5)).isoformat(),
            "wall_heartbeat_at": (self.now - timedelta(hours=2)).isoformat(),
        })
        identity = self.trigger._activate_cycle(
            self.cache, cycle_id=old_id, now=self.now, local_date="2026-11-05", source="CRON",
        )
        self.assertNotEqual(identity, old_id)
        self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["ccgp"]["status"], "DEGRADED")
        fixed_now = self.now

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        with patch.object(self.worker, "datetime", Clock), patch.object(self.runtime, "run_stage") as run:
            asyncio.run(self.worker.process_collector_payload({
                "schema_version": "0.1", "stage": "ccgp", "cycle_id": old_id,
                "cycle_as_of": self.now.isoformat(),
            }))
        run.assert_not_called()
        self.assertEqual(self.cache.get(self.worker.ACTIVE_CYCLE_KEY)["cycle_id"], identity)

    def test_independent_tick_reclaims_dead_owner_and_queues_healthy_source(self) -> None:
        delivered = self.now.replace(hour=3, minute=30)
        self.cache.set(self.worker.META_KEY, self.running_state(wall_age=timedelta(hours=2)))
        self.cache.set(self.worker.ACTIVE_CYCLE_KEY, {
            "cycle_id": "prod:2026-11-05", "local_date": "2026-11-05",
            "activated_at": (self.now - timedelta(hours=5)).isoformat(),
            "wall_heartbeat_at": (self.now - timedelta(hours=2)).isoformat(),
        })
        tick = self.worker.first_tick_after_deep(delivered)

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return delivered

        with patch.object(self.worker, "datetime", Clock), patch.object(
            self.worker, "choose_due_incremental_source", return_value=types.SimpleNamespace(source_id="tjmugh"),
        ):
            asyncio.run(self.worker._process_incremental_tick_payload({
                "business_date": tick.business_date, "scheduled_for": tick.scheduled_for,
                "tick_id": tick.tick_id, "sequence": tick.sequence,
            }))
        self.assertIsNone(self.cache.get(self.worker.ACTIVE_CYCLE_KEY))
        self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["ccgp"]["status"], "DEGRADED")
        self.assertTrue(any(item["payload"].get("source_id") == "tjmugh" for item in self.sent))
        replacement = self.trigger._activate_cycle(
            self.cache, cycle_id="prod:2026-11-05", now=delivered,
            local_date="2026-11-05", source="CRON",
        )
        self.assertIn(":orphan-recovery:", replacement)

    def test_expired_ownerless_running_is_degraded_and_new_identity_fences_old_messages(self) -> None:
        self.cache.set(self.worker.META_KEY, self.running_state(wall_age=timedelta(hours=2)))
        identity = self.trigger._activate_cycle(
            self.cache, cycle_id="prod:2026-11-05", now=self.now, local_date="2026-11-05", source="CRON",
        )
        self.assertIn(":orphan-recovery:", identity)
        self.assertEqual(self.cache.get(self.worker.META_KEY)["stages"]["ccgp"]["status"], "DEGRADED")
        self.assertFalse(self.worker._active_cycle_matches("prod:2026-11-05", cycle_as_of=self.now))

    def test_ownerless_running_without_wall_evidence_fails_closed(self) -> None:
        state = self.running_state(wall_age=timedelta(hours=2))
        del state["updated_at"]
        del state["stages"]["ccgp"]["wall_started_at"]
        self.cache.set(self.worker.META_KEY, state)
        with self.assertRaises(self.trigger.CollectorStartConflict):
            self.trigger._activate_cycle(self.cache, cycle_id="new", now=self.now, local_date="2026-11-05", source="CRON")

    def test_legacy_wall_update_allows_cross_day_orphan_recovery(self) -> None:
        state = self.running_state(wall_age=timedelta(days=1))
        state["local_date"] = "2026-11-04"
        del state["stages"]["ccgp"]["wall_started_at"]
        self.cache.set(self.worker.META_KEY, state)
        identity = self.trigger._activate_cycle(
            self.cache, cycle_id="prod:2026-11-05", now=self.now, local_date="2026-11-05", source="CRON",
        )
        self.assertEqual(self.cache.get(self.worker.ACTIVE_CYCLE_KEY)["cycle_id"], identity)


if __name__ == "__main__":
    unittest.main()
