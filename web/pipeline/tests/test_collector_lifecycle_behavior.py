"""Behavioral tests for the Vercel collector lifecycle.

These run the REAL runtime modules (collector_runtime, collector_queue,
api/collector-run.py) against an in-memory stand-in for the Vercel SDK
(tests/_stubs/vercel). No network: every source-facing stage function is
replaced. The scenarios are the ones that previously locked the pipeline out:

* a platform kill (maxDuration) left a stage RUNNING forever and every later
  daily cron answered 409 COLLECTOR_CYCLE_ALREADY_RUNNING;
* same-day recovery reused hard-coded cycle ids, so the queue rejected the
  first message (DuplicateIdempotencyKeyError) after the lease was written;
* started_at was written from the cycle clock, so staleness math was wrong.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_ROOT = Path(__file__).resolve().parent
WEB_ROOT = TESTS_ROOT.parents[1]
STUBS = TESTS_ROOT / "_stubs"

for entry in (str(STUBS), str(WEB_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from vercel import functions as fake_cache  # noqa: E402
from vercel import queue as fake_queue  # noqa: E402

import collector_queue as cq  # noqa: E402  (applies the v2 namespace to the runtime)
import collector_runtime as rt  # noqa: E402
import collector_namespace as ns  # noqa: E402
from vercel.functions import RuntimeCache  # noqa: E402


def _load_collector_run():
    spec = importlib.util.spec_from_file_location("collector_run_under_test", WEB_ROOT / "api" / "collector-run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector_run = _load_collector_run()


class PlatformKill(BaseException):
    """Vercel terminates the process at maxDuration: no `except Exception` runs."""


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


async def _noop_async(*_args, **_kwargs):
    return None


class CollectorLifecycleBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_cache.reset_store()
        fake_queue.reset()
        # 2026-09-27 00:20 Asia/Shanghai == 2026-09-26 16:20 UTC (the daily cron slot).
        self.clock = FakeClock(datetime(2026, 9, 26, 16, 20, tzinfo=timezone.utc))
        self.kill_stage: str | None = None
        self.stage_calls: list[str] = []
        self._patches = [
            mock.patch.object(rt, "_now_utc", self.clock),
            mock.patch.object(collector_run, "datetime", _FrozenDatetime.bind(self.clock)),
            mock.patch.object(cq, "datetime", _FrozenDatetime.bind(self.clock)),
            mock.patch.object(rt, "_run_ccgp", self._stage("ccgp")),
            mock.patch.object(rt, "_run_event_batch", lambda cache, state, stage: self._record(stage)),
            mock.patch.object(rt, "_run_tjmugh", self._stage("tjmugh")),
            mock.patch.object(rt, "_run_tjnothop", self._stage("tjnothop")),
            mock.patch.object(rt, "_run_teda", self._stage("teda")),
            mock.patch.object(rt, "_run_tjfch", self._stage("tjfch")),
            mock.patch.object(rt, "_run_official_site_stage", lambda cache, state, source: self._record(source.stage)),
            mock.patch.object(rt, "_run_publish", self._stage("publish")),
            mock.patch.object(rt, "_run_regional_market", lambda cache, state, stage: self._record(stage, fallback_required=False)),
            mock.patch.object(cq, "_start_intraday_chain_after_deep", _noop_async),
            mock.patch.object(cq.incremental_runtime, "clear_incremental_pending", lambda cache: None),
            mock.patch.object(cq.asyncio, "sleep", self._sleep_advances_clock),
        ]
        for patch in self._patches:
            patch.start()
        # Canonical outputs must exist for COMPLETED stages to be trusted.
        cache = RuntimeCache()
        for key in (
            rt.CCGP_RECORDS_KEY, rt.CCGP_EVENTS_KEY, rt.CCGP_WATCH_KEY, rt.TJMUGH_RECORDS_KEY,
            rt.TJNOTHOP_RECORDS_KEY, rt.TEDA_RECORDS_KEY, rt.TJFCH_RECORDS_KEY,
            *(source.records_key() for source in rt.OFFICIAL_SITE_SOURCES.values()),
        ):
            cache.set(key, [])
        for market in rt.REGIONAL_STAGE_MARKET_CODES.values():
            cache.set(rt._regional_records_key(market), [])

    def tearDown(self) -> None:
        for patch in reversed(self._patches):
            patch.stop()

    # ------------------------------------------------------------------ helpers
    async def _sleep_advances_clock(self, seconds: float) -> None:
        self.clock.advance(seconds)

    def _stage(self, name: str):
        return lambda cache, state: self._record(name)

    def _record(self, name: str, **extra):
        self.stage_calls.append(name)
        if name == self.kill_stage:
            raise PlatformKill(name)
        return {"ok": True, **extra}

    def trigger(self) -> tuple[str, object]:
        try:
            return "202", asyncio.run(collector_run._enqueue_start("VERCEL_CRON"))
        except collector_run.CollectorStartConflict as exc:
            return "409", str(exc)
        except Exception as exc:  # what the HTTP handler turns into 503
            return "503", f"{type(exc).__name__}:{exc}"

    def drain_queue(self, *, max_attempts: int = 3, stop_on_kill: bool = False) -> list[str]:
        """Deliver queued messages like Vercel would: ordered, at-least-once, 3 attempts.

        A killed worker is redelivered only after the queue lease (maxDuration)
        expired; a raised exception is retried after retryAfterSeconds (150 s).
        """
        dropped: list[str] = []
        guard = 0
        while fake_queue.SENT and guard < 500:
            guard += 1
            message = fake_queue.SENT.pop(0)
            not_before = message.get("_not_before")
            if not_before is not None and self.clock.now < not_before:
                self.clock.now = not_before
            try:
                asyncio.run(cq.process_collector_payload(message["payload"]))
            except PlatformKill:
                attempts = message.setdefault("_attempts", 1)
                message["_not_before"] = self.clock.now + timedelta(seconds=ns.QUEUE_FUNCTION_MAX_DURATION_SECONDS + 1)
                if attempts < max_attempts:
                    message["_attempts"] = attempts + 1
                    fake_queue.SENT.insert(0, message)
                else:
                    dropped.append(str(message["payload"].get("stage")))
                if stop_on_kill:
                    return dropped
            except Exception as exc:
                attempts = message.setdefault("_attempts", 1)
                message["_not_before"] = self.clock.now + timedelta(seconds=150)
                if attempts < max_attempts:
                    message["_attempts"] = attempts + 1
                    fake_queue.SENT.insert(0, message)
                else:
                    dropped.append(f"{message['payload'].get('stage')}:{str(exc)[:80]}")
        return dropped

    def state(self) -> dict:
        return RuntimeCache().get(ns.META_KEY) or {}

    def active_cycle(self):
        return ns.active_cycle_id(RuntimeCache().get(ns.ACTIVE_CYCLE_KEY))

    # -------------------------------------------------------------- scenarios
    def test_full_daily_cycle_completes_publishes_and_releases_the_lease(self) -> None:
        status, info = self.trigger()
        self.assertEqual(status, "202", info)
        self.assertEqual(info[2], "prod:2026-09-27")
        dropped = self.drain_queue()
        self.assertEqual(dropped, [])
        state = self.state()
        self.assertEqual(state["stages"]["publish"]["status"], "COMPLETED")
        self.assertEqual(len([s for s in rt.STAGE_ORDER if state["stages"][s]["status"] == "COMPLETED"]), len(rt.STAGE_ORDER))
        self.assertIsNone(self.active_cycle(), "publish COMPLETED must release ACTIVE_CYCLE_KEY")
        # Only one recovery-free cycle id was ever used.
        self.assertTrue(all(key.startswith("medicalchannelai-refresh-v2:prod:2026-09-27:") for key in fake_queue.USED_IDEMPOTENCY_KEYS))

    def test_started_at_and_lease_use_the_wall_clock_not_the_cycle_clock(self) -> None:
        cycle_as_of = self.clock.now
        self.clock.advance(3 * 60 * 60)  # a recovery replaying an old cycle clock, three hours later
        status, result = rt.run_stage("ccgp", now=cycle_as_of)
        self.assertEqual(status, 200, result)
        stage = self.state()["stages"]["ccgp"]
        self.assertEqual(datetime.fromisoformat(stage["started_at"]), self.clock.now)
        self.assertEqual(
            datetime.fromisoformat(stage["lease_expires_at"]),
            self.clock.now + timedelta(seconds=ns.STAGE_LEASE_SECONDS),
        )
        # The cycle clock still drives local_date / snapshot_as_of.
        self.assertEqual(self.state()["local_date"], "2026-09-27")

    def test_platform_kill_no_longer_locks_out_the_next_day(self) -> None:
        self.kill_stage = "regional_he"
        status, _ = self.trigger()
        self.assertEqual(status, "202")
        self.drain_queue(stop_on_kill=True)
        state = self.state()
        self.assertEqual(state["stages"]["regional_he"]["status"], "RUNNING")
        self.assertNotIn("publish", state["stages"])

        # While the lease is live a second start is (correctly) refused ...
        status, info = self.trigger()
        self.assertEqual((status, info), ("409", "COLLECTOR_CYCLE_ALREADY_RUNNING"))

        # ... the queue redelivers, the stage is killed again and the cycle ends
        # with an honest FAILED/COLLECTOR_STAGE_TIMEOUT instead of a RUNNING ghost ...
        dropped = self.drain_queue()
        self.assertEqual(dropped, [])
        stage = self.state()["stages"]["regional_he"]
        self.assertEqual((stage["status"], stage["error_code"]), ("FAILED", "COLLECTOR_STAGE_TIMEOUT"))
        self.assertEqual(stage["attempt_count"], rt.MAX_STAGE_ATTEMPTS_PER_DAY)
        self.assertIsNone(self.active_cycle(), "retry limit must release the active cycle")

        # ... and the next day's cron is accepted and runs to completion.
        self.kill_stage = None
        self.clock.advance(24 * 60 * 60)
        status, info = self.trigger()
        self.assertEqual(status, "202", info)
        self.assertEqual(info[2], "prod:2026-09-28")
        self.assertEqual(self.drain_queue(), [])
        self.assertEqual(self.state()["local_date"], "2026-09-28")
        self.assertEqual(self.state()["stages"]["publish"]["status"], "COMPLETED")

    def test_same_day_recovery_mints_new_cycle_ids_and_resets_attempts(self) -> None:
        self.kill_stage = "regional_he"
        self.assertEqual(self.trigger()[0], "202")
        # Stop right after the first kill: the stage is a RUNNING ghost with an
        # unexpired lease, exactly the state that used to be unrecoverable.
        self.drain_queue(stop_on_kill=True)
        fake_queue.SENT.clear()
        self.assertEqual(self.state()["stages"]["regional_he"]["status"], "RUNNING")
        self.assertEqual(self.trigger(), ("409", "COLLECTOR_CYCLE_ALREADY_RUNNING"))

        # Source recovered; the operator re-triggers once the lease has expired.
        self.kill_stage = None
        self.clock.advance(ns.STAGE_LEASE_SECONDS + 1)
        status, info = self.trigger()
        self.assertEqual(status, "202", info)
        self.assertEqual(info[2], "prod:2026-09-27:recovery-1")
        state = self.state()
        self.assertEqual(state["recovery_attempts"], 1)
        self.assertEqual(state["stages"]["regional_he"]["attempt_count"], 0)
        self.assertEqual(state["stages"]["regional_he"]["status"], "FAILED")
        self.assertEqual(state["stages"]["regional_he"]["error_code"], "COLLECTOR_STAGE_TIMEOUT")
        self.assertEqual(len(state["stages"]["regional_he"]["previous_attempts"]), 1)
        # Completed stages are not re-run by the recovery cycle.
        calls_before = list(self.stage_calls)
        self.assertEqual(self.drain_queue(), [])
        new_calls = self.stage_calls[len(calls_before):]
        self.assertNotIn("ccgp", new_calls)
        self.assertNotIn("regional_bj", new_calls)
        self.assertEqual(new_calls[0], "regional_he")
        self.assertEqual(self.state()["stages"]["publish"]["status"], "COMPLETED")
        self.assertIsNone(self.active_cycle())

        # Once today's publish completed, further same-day triggers are refused.
        self.assertEqual(self.trigger(), ("409", "COLLECTOR_CYCLE_ALREADY_COMPLETED_TODAY"))

    def test_same_day_recoveries_are_bounded(self) -> None:
        self.kill_stage = "regional_he"
        self.assertEqual(self.trigger()[0], "202")
        self.drain_queue()
        seen_ids = []
        for expected in range(1, ns.MAX_RECOVERY_CYCLES_PER_DAY + 1):
            self.clock.advance(ns.STAGE_LEASE_SECONDS + 1)
            status, info = self.trigger()
            self.assertEqual(status, "202", info)
            seen_ids.append(info[2])
            self.assertEqual(info[2], f"prod:2026-09-27:recovery-{expected}")
            # Each recovery gets a fresh attempt budget for the broken stage.
            self.assertEqual(self.state()["stages"]["regional_he"]["attempt_count"], 0)
            self.drain_queue()
            self.assertEqual(self.state()["stages"]["regional_he"]["attempt_count"], rt.MAX_STAGE_ATTEMPTS_PER_DAY)
        self.clock.advance(ns.STAGE_LEASE_SECONDS + 1)
        self.assertEqual(self.trigger(), ("409", "COLLECTOR_RECOVERY_LIMIT"))
        self.assertEqual(len(set(seen_ids)), ns.MAX_RECOVERY_CYCLES_PER_DAY)
        # Every cycle id produced distinct queue idempotency keys.
        ccgp_keys = {key for key in fake_queue.USED_IDEMPOTENCY_KEYS if key.endswith(":ccgp")}
        self.assertEqual(len(ccgp_keys), ns.MAX_RECOVERY_CYCLES_PER_DAY + 1)

    def test_failed_queue_send_releases_the_active_cycle_lease(self) -> None:
        async def failing_send(*_args, **_kwargs):
            raise RuntimeError("QUEUE_UNAVAILABLE")

        with mock.patch.object(collector_run, "send", failing_send):
            status, info = self.trigger()
        self.assertEqual(status, "503", info)
        self.assertIsNone(self.active_cycle(), "a lease without a queue message must not linger")
        status, info = self.trigger()
        self.assertEqual(status, "202", info)

    def test_duplicate_idempotency_key_is_reported_not_leaked_as_a_lease(self) -> None:
        # Simulate: the first send for this cycle id already succeeded elsewhere.
        fake_queue.USED_IDEMPOTENCY_KEYS.add("medicalchannelai-refresh-v2:prod:2026-09-27:ccgp")
        status, info = self.trigger()
        self.assertEqual((status, info), ("409", "COLLECTOR_CYCLE_ALREADY_QUEUED"))

    def test_duplicate_delivery_while_lease_is_live_does_not_run_the_stage_twice(self) -> None:
        cycle_as_of = self.clock.now
        cache = RuntimeCache()
        state, previous = rt._prepare_stage(cache, "ccgp", cycle_as_of, self.clock.now)
        self.assertIsNone(previous)
        self.clock.advance(10)
        status, result = rt.run_stage("ccgp", now=cycle_as_of)
        self.assertEqual(status, 409)
        self.assertTrue(result["error"].startswith("COLLECTOR_STAGE_LEASE_HELD:ccgp:"), result)
        self.assertEqual(
            datetime.fromisoformat(result["lease_expires_at"]),
            self.clock.now - timedelta(seconds=10) + timedelta(seconds=ns.STAGE_LEASE_SECONDS),
        )
        self.assertEqual(self.stage_calls, [])
        # After the lease expired the dead attempt is recorded and the stage retried.
        self.clock.advance(ns.STAGE_LEASE_SECONDS)
        status, result = rt.run_stage("ccgp", now=cycle_as_of)
        self.assertEqual(status, 200, result)
        stage = self.state()["stages"]["ccgp"]
        self.assertEqual(stage["attempt_count"], 2)
        self.assertEqual(self.stage_calls, ["ccgp"])

    def test_completed_stage_is_replayed_when_its_canonical_output_vanished(self) -> None:
        self.assertEqual(self.trigger()[0], "202")
        self.assertEqual(self.drain_queue(), [])
        cache = RuntimeCache()
        cache.delete(rt._regional_records_key("HE"))
        cycle_as_of = datetime.fromisoformat(self.state()["cycle_as_of"])
        state, previous = rt._prepare_stage(cache, "regional_he", cycle_as_of, self.clock.now)
        self.assertIsNone(previous, "a COMPLETED marker without its output must not be trusted")
        stage = state["stages"]["regional_he"]
        self.assertEqual(stage["status"], "RUNNING")
        self.assertEqual(stage["attempt_count"], 1)
        self.assertTrue(stage["replay_reason"].startswith("COLLECTOR_STAGE_OUTPUT_MISSING:"))
        # Stages whose output is intact are still short-circuited.
        _, previous = rt._prepare_stage(cache, "regional_bj", cycle_as_of, self.clock.now)
        self.assertIsNotNone(previous)

    def test_redelivered_message_of_a_completed_stage_is_acknowledged_quietly(self) -> None:
        self.assertEqual(self.trigger()[0], "202")
        # Deliver messages one by one until tjmugh has run (mid-cycle).
        tjmugh_payload = None
        while fake_queue.SENT:
            message = fake_queue.SENT.pop(0)
            asyncio.run(cq.process_collector_payload(message["payload"]))
            if message["payload"]["stage"] == "tjmugh":
                tjmugh_payload = message["payload"]
                break
        self.assertIsNotNone(tjmugh_payload)
        self.assertEqual([m["payload"]["stage"] for m in fake_queue.SENT], ["tjnothop"])
        calls_before = len(self.stage_calls)
        # At-least-once delivery: the same tjmugh message arrives again. It must
        # neither re-run the stage nor blow up on the already-used idempotency
        # key of the next stage, and it must not enqueue tjnothop twice.
        asyncio.run(cq.process_collector_payload(tjmugh_payload))
        self.assertEqual(len(self.stage_calls), calls_before)
        self.assertEqual([m["payload"]["stage"] for m in fake_queue.SENT], ["tjnothop"])
        self.assertEqual(self.drain_queue(), [])
        self.assertEqual(self.state()["stages"]["publish"]["status"], "COMPLETED")

    def test_stale_worker_cannot_overwrite_a_stage_reclaimed_after_its_lease_expired(self) -> None:
        self.assertEqual(self.trigger()[0], "202")
        cache = RuntimeCache()
        cycle_as_of = datetime.fromisoformat(fake_queue.SENT[0]["payload"]["cycle_as_of"])
        # Worker A claims ccgp and then stalls past its lease.
        state_a, previous = rt._prepare_stage(cache, "ccgp", cycle_as_of, self.clock.now)
        self.assertIsNone(previous)
        self.clock.advance(ns.STAGE_LEASE_SECONDS + 1)
        # Worker B re-claims the stage (A's lease is recorded as a timeout).
        state_b, previous = rt._prepare_stage(cache, "ccgp", cycle_as_of, self.clock.now)
        self.assertIsNone(previous)
        stage_b = state_b["stages"]["ccgp"]
        self.assertEqual(stage_b["attempt_count"], 2)
        # A finally finishes: its write must be fenced off, B's record survives.
        with self.assertRaises(rt.CollectorPrecondition) as ctx:
            rt._mark_completed(cache, state_a, "ccgp", {"stale": True})
        self.assertEqual(str(ctx.exception), "COLLECTOR_STAGE_LEASE_LOST:ccgp")
        with self.assertRaises(rt.CollectorPrecondition):
            rt._mark_failed(cache, state_a, "ccgp", RuntimeError("stale failure"))
        current = self.state()["stages"]["ccgp"]
        self.assertEqual((current["status"], current["started_at"]), ("RUNNING", stage_b["started_at"]))
        self.assertIsNone(current["result"])

    def test_next_day_cron_does_not_replay_yesterdays_stages(self) -> None:
        self.assertEqual(self.trigger()[0], "202")
        self.assertEqual(self.drain_queue(), [])
        self.clock.advance(24 * 60 * 60)
        calls_before = len(self.stage_calls)
        status, info = self.trigger()
        self.assertEqual(status, "202", info)
        self.assertEqual(self.drain_queue(), [])
        self.assertEqual(self.stage_calls[calls_before], "ccgp")
        self.assertEqual(len(self.stage_calls) - calls_before, len(rt.STAGE_ORDER))


class _FrozenDatetime(datetime):
    """datetime replacement whose now() follows the test clock."""

    _clock: FakeClock | None = None

    @classmethod
    def bind(cls, clock: FakeClock):
        bound = type("BoundDatetime", (cls,), {"_clock": clock})
        return bound

    @classmethod
    def now(cls, tz=None):
        current = cls._clock() if cls._clock else datetime.now(timezone.utc)
        return current.astimezone(tz) if tz else current


class StageBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_cache.reset_store()

    def tearDown(self) -> None:
        rt._begin_stage_budget(None)

    def test_budget_exhaustion_commits_verified_records_and_defers_the_rest(self) -> None:
        candidates = [
            SimpleNamespace(title=f"c{i}", detail_url=f"https://www.tjmugh.com.cn/notice/{i}.html")
            for i in range(4)
        ]
        fetched: list[str] = []

        def slow_fetch(url, *, timeout_seconds=None):
            self.assertEqual(timeout_seconds, rt.SOURCE_REQUEST_TIMEOUT_SECONDS)
            fetched.append(url)
            if url != rt.TJMUGH_INDEX_URL:
                time.sleep(0.03)
            return "<html></html>"

        cache = RuntimeCache()
        cache.set(rt.TJMUGH_RECORDS_KEY, [])
        state = {"cycle_as_of": "2026-09-27T00:20:00+08:00", "stages": {}}
        with (
            mock.patch.object(rt, "fetch_tjmugh_page", slow_fetch),
            mock.patch.object(rt, "parse_tjmugh_index_html", lambda html: candidates),
            mock.patch.object(rt, "select_tjmugh_candidates", lambda discovered, **kwargs: list(discovered)),
            mock.patch.object(rt, "parse_tjmugh_market_research", lambda html, **kwargs: {"opportunity_id": kwargs["opportunity_id"]}),
            mock.patch.object(rt, "tjmugh_opportunity_id", lambda url: url.rsplit("/", 1)[-1]),
            mock.patch.object(rt, "merge_canonical_records", lambda existing, new: [*existing, *new]),
            mock.patch.object(rt, "_sleep", lambda seconds: None),
        ):
            rt._begin_stage_budget(0.05)
            result = rt._run_tjmugh(cache, state)

        self.assertEqual(result["selected_candidate_count"], 4)
        self.assertGreaterEqual(result["new_verified_record_count"], 1)
        self.assertGreaterEqual(result["deferred_candidate_count"], 1)
        self.assertEqual(result["new_verified_record_count"] + result["deferred_candidate_count"], 4)
        self.assertEqual(len(cache.get(rt.TJMUGH_RECORDS_KEY)), result["new_verified_record_count"])

    def test_budget_exhausted_before_any_detail_fails_the_stage_explicitly(self) -> None:
        candidates = [SimpleNamespace(title="c0", detail_url="https://www.tjmugh.com.cn/notice/0.html")]
        cache = RuntimeCache()
        cache.set(rt.TJMUGH_RECORDS_KEY, [])
        state = {"cycle_as_of": "2026-09-27T00:20:00+08:00", "stages": {}}
        with (
            mock.patch.object(rt, "fetch_tjmugh_page", lambda url, *, timeout_seconds=None: "<html></html>"),
            mock.patch.object(rt, "parse_tjmugh_index_html", lambda html: candidates),
            mock.patch.object(rt, "select_tjmugh_candidates", lambda discovered, **kwargs: list(discovered)),
        ):
            rt._begin_stage_budget(0)
            with self.assertRaisesRegex(rt.CollectorStageBlocked, "COLLECTOR_STAGE_BUDGET_EXHAUSTED:tjmugh:detail"):
                rt._run_tjmugh(cache, state)

    def test_sleep_never_exceeds_the_remaining_budget(self) -> None:
        rt._begin_stage_budget(0.02)
        started = time.monotonic()
        rt._sleep(5.0)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_budget_constants_leave_headroom_under_the_function_limit(self) -> None:
        vercel_json = json.loads((WEB_ROOT / "vercel.json").read_text(encoding="utf-8"))
        max_duration = vercel_json["functions"]["api/collector-queue.py"]["maxDuration"]
        self.assertEqual(max_duration, ns.QUEUE_FUNCTION_MAX_DURATION_SECONDS)
        self.assertEqual(ns.STAGE_LEASE_SECONDS, max_duration + ns.STAGE_LEASE_GRACE_SECONDS)
        self.assertLessEqual(rt.STAGE_BUDGET_SECONDS + rt.DURABLE_PUBLISH_TIMEOUT_SECONDS + rt.PUBLISH_BASELINE_TIMEOUT_SECONDS, max_duration - 15)
        self.assertLess(rt.SOURCE_REQUEST_TIMEOUT_SECONDS * 3, rt.STAGE_BUDGET_SECONDS)


class PublishGateAndTargetTests(unittest.TestCase):
    def _snapshot(self, pool_size: int) -> dict:
        return {
            "snapshot_as_of": "2026-09-27T00:20:00+08:00",
            "cards": [],
            "opportunity_pool": [
                {"opportunity_id": f"o{i}", "evidence_source_urls": [f"https://host{i % 3}.example/{i}"]}
                for i in range(pool_size)
            ],
        }

    def test_regression_gate_blocks_a_sharply_smaller_pool(self) -> None:
        with (
            mock.patch.object(rt, "_served_pool_baseline", lambda: (400, "status:DATABASE")),
            mock.patch.dict(os.environ, {"COLLECTOR_PUBLISH_MIN_POOL_RATIO": ""}),
        ):
            with self.assertRaisesRegex(rt.CollectorStageBlocked, r"PUBLISH_REGRESSION_POOL_SHRUNK:100<280"):
                rt._publish_regression_gate(self._snapshot(100))
            report = rt._publish_regression_gate(self._snapshot(300))
        self.assertEqual(report["decision"], "PASS")
        self.assertEqual(report["baseline_pool_count"], 400)
        self.assertEqual(sum(report["contributing_source_hosts"].values()), 300)

    def test_regression_gate_can_be_bypassed_explicitly_and_tolerates_no_baseline(self) -> None:
        with mock.patch.dict(os.environ, {"COLLECTOR_PUBLISH_MIN_POOL_RATIO": "0"}):
            self.assertEqual(rt._publish_regression_gate(self._snapshot(1))["decision"], "BYPASSED")
        with (
            mock.patch.object(rt, "_served_pool_baseline", lambda: (None, "none")),
            mock.patch.dict(os.environ, {"COLLECTOR_PUBLISH_MIN_POOL_RATIO": ""}),
        ):
            self.assertEqual(rt._publish_regression_gate(self._snapshot(1))["decision"], "NO_BASELINE")

    def test_baseline_falls_back_to_the_bundled_snapshot_when_status_is_unreachable(self) -> None:
        def unreachable(*_args, **_kwargs):
            raise OSError("offline")

        with (
            mock.patch.object(rt, "urlopen", unreachable),
            mock.patch.dict(os.environ, {"VERCEL_ENV": "production"}),
        ):
            count, source = rt._served_pool_baseline()
        bundled = json.loads((WEB_ROOT / "public" / "data" / "today-actions.public.json").read_text(encoding="utf-8"))
        self.assertEqual((count, source), (len(bundled["opportunity_pool"]), "bundled"))

    def test_publish_target_follows_the_deployment_environment(self) -> None:
        with mock.patch.dict(os.environ, {"VERCEL_ENV": "production", "VERCEL_PROJECT_PRODUCTION_URL": "medicalchannelai.vercel.app", "VERCEL_URL": "medicalchannelai-abc.vercel.app"}, clear=False):
            url, headers = rt._durable_publish_url()
        self.assertEqual((url, headers), ("https://medicalchannelai.vercel.app/api/public-snapshot", {}))

        preview_env = {
            "VERCEL_ENV": "preview",
            "VERCEL_PROJECT_PRODUCTION_URL": "medicalchannelai.vercel.app",
            "VERCEL_URL": "medicalchannelai-git-fix-abc.vercel.app",
            "VERCEL_AUTOMATION_BYPASS_SECRET": "bypass-secret",
            "COLLECTOR_ALLOW_NON_PRODUCTION_PUBLISH": "",
        }
        with mock.patch.dict(os.environ, preview_env, clear=False):
            url, headers = rt._durable_publish_url()
        self.assertEqual(url, "https://medicalchannelai-git-fix-abc.vercel.app/api/public-snapshot")
        self.assertEqual(headers, {"x-vercel-protection-bypass": "bypass-secret"})

        with mock.patch.dict(os.environ, {"VERCEL_ENV": "development", "VERCEL_URL": "", "COLLECTOR_ALLOW_NON_PRODUCTION_PUBLISH": ""}, clear=False):
            with self.assertRaisesRegex(rt.CollectorStageBlocked, "DURABLE_SNAPSHOT_PUBLISH_TARGET_UNRESOLVED"):
                rt._durable_publish_url()

        with mock.patch.dict(os.environ, {"VERCEL_ENV": "development", "VERCEL_URL": "", "COLLECTOR_ALLOW_NON_PRODUCTION_PUBLISH": "1", "VERCEL_PROJECT_PRODUCTION_URL": ""}, clear=False):
            url, _ = rt._durable_publish_url()
        self.assertEqual(url, f"https://{rt.PRODUCTION_PUBLISH_HOST}/api/public-snapshot")


if __name__ == "__main__":
    unittest.main()
