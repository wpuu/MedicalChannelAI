from __future__ import annotations

import importlib
import asyncio
import json
import os
import sys
import types
import unittest
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import AsyncMock, patch


class MemoryCache:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.fail_readback_key = None
        self._corrupt_once = False

    def get(self, key):
        if self.fail_readback_key == key and self._corrupt_once:
            self._corrupt_once = False
            return {"readback": "corrupt"}
        return self.values.get(key)

    def set(self, key, value, options=None):
        self.values[key] = value
        if key == self.fail_readback_key and isinstance(value, dict) and value.get("snapshot_as_of") == "2026-10-03T00:00:00+00:00":
            self._corrupt_once = True

    def delete(self, key):
        self.values.pop(key, None)


def _load_runtime_modules():
    vercel = types.ModuleType("vercel")
    functions = types.ModuleType("vercel.functions")
    functions.RuntimeCache = MemoryCache
    queue_api = types.ModuleType("vercel.queue")
    async def fake_send(*_args, **_kwargs):
        return "offline-message"
    queue_api.send = fake_send
    vercel.functions = functions
    vercel.queue = queue_api
    sys.modules.setdefault("vercel", vercel)
    sys.modules.setdefault("vercel.functions", functions)
    sys.modules.setdefault("vercel.queue", queue_api)
    web_root = str(__import__("pathlib").Path(__file__).resolve().parents[2])
    if web_root not in sys.path:
        sys.path.insert(0, web_root)
    runtime = importlib.import_module("collector_runtime")
    incremental = importlib.import_module("collector_incremental_runtime")
    queue = importlib.import_module("collector_queue")
    return runtime, incremental, queue


runtime, incremental, queue = _load_runtime_modules()


class CollectorNativeReliabilityTests(unittest.TestCase):
    def _canonical_cache(self):
        return MemoryCache({
            runtime.CCGP_RECORDS_KEY: [],
            runtime.CCGP_EVENTS_KEY: [],
            runtime.TJMUGH_RECORDS_KEY: [],
            runtime.TJNOTHOP_RECORDS_KEY: [],
            runtime.TEDA_RECORDS_KEY: [],
            runtime.TJFCH_RECORDS_KEY: [],
            **{runtime._regional_records_key(code): [] for code in runtime.REGIONAL_STAGE_MARKET_CODES.values()},
        })

    def _completed_stage_state(self):
        stages = {
            stage: {"status": "COMPLETED", "terminal": True, "result": {"fallback_required": False}}
            for stage in runtime.STAGE_ORDER
            if stage != "publish"
        }
        return {"cycle_as_of": "2026-10-03T00:00:00+00:00", "stages": stages}

    def test_durable_publish_failure_preserves_both_last_good_cache_values(self):
        old = {"snapshot_as_of": "2026-10-02T00:00:00+00:00", "cards": [], "opportunity_pool": []}
        cache = self._canonical_cache()
        cache.values[runtime.LATEST_RUNTIME_SNAPSHOT_KEY] = old
        cache.values[runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY] = old
        with patch.object(runtime, "_persist_verified_snapshot_durably", side_effect=runtime.CollectorStageBlocked("DURABLE_TEST_HTTP_503")):
            with self.assertRaises(runtime.CollectorStageBlocked):
                runtime._run_publish(cache, self._completed_stage_state())
        self.assertEqual(cache.get(runtime.LATEST_RUNTIME_SNAPSHOT_KEY), old)
        self.assertEqual(cache.get(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY), old)

    def test_cache_readback_failure_rolls_back_candidate_after_durable_acceptance(self):
        old = {"snapshot_as_of": "2026-10-02T00:00:00+00:00", "cards": [], "opportunity_pool": []}
        cache = self._canonical_cache()
        cache.values[runtime.LATEST_RUNTIME_SNAPSHOT_KEY] = old
        cache.values[runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY] = old
        cache.fail_readback_key = runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY
        accepted = {"snapshot_as_of": "2026-10-03T00:00:00+00:00", "opportunity_pool_count": 0}
        with patch.object(runtime, "_persist_verified_snapshot_durably", return_value=accepted):
            with self.assertRaises(runtime.CollectorStageBlocked) as caught:
                runtime._run_publish(cache, self._completed_stage_state())
        self.assertTrue(caught.exception.durable_accepted)
        self.assertEqual(cache.get(runtime.LATEST_RUNTIME_SNAPSHOT_KEY), old)
        self.assertEqual(cache.get(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY), old)

    def test_zero_opportunity_pool_acknowledgement_is_valid(self):
        snapshot = {"snapshot_as_of": "2026-10-03T00:00:00+00:00", "cards": [], "opportunity_pool": []}
        class Response:
            status = 200
            def __init__(self, count):
                self.count = count
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps({
                    "ok": True,
                    "snapshot_as_of": snapshot["snapshot_as_of"],
                    "opportunity_pool_count": self.count,
                }).encode()

        with patch.dict(os.environ, {"VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "offline-test-token-with-32-characters"}), \
             patch.object(runtime, "urlopen", return_value=Response(0)):
            accepted = runtime._persist_verified_snapshot_durably(snapshot)
        self.assertEqual(accepted["opportunity_pool_count"], 0)
        for invalid_count in (True, 0.1, -0.5, None):
            with patch.dict(os.environ, {"VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "offline-test-token-with-32-characters"}), \
                 patch.object(runtime, "urlopen", return_value=Response(invalid_count)):
                with self.assertRaises(runtime.CollectorStageBlocked):
                    runtime._persist_verified_snapshot_durably(snapshot)

        cache = self._canonical_cache()
        accepted = {"snapshot_as_of": "2026-10-03T00:00:00+00:00", "opportunity_pool_count": 0}
        with patch.object(runtime, "_persist_verified_snapshot_durably", return_value=accepted):
            result = runtime._run_publish(cache, self._completed_stage_state())
        self.assertEqual(result["opportunity_pool_count"], 0)
        self.assertTrue(result["durable_snapshot_persisted"])

    def test_http_503_durable_receipt_is_trusted_only_for_matching_candidate_clock(self):
        snapshot = {"snapshot_as_of": "2026-10-03T00:00:00+00:00", "cards": [], "opportunity_pool": []}

        def http_error(payload):
            return HTTPError(
                runtime.DURABLE_PUBLISH_URL,
                503,
                "Service Unavailable",
                hdrs=None,
                fp=BytesIO(json.dumps(payload).encode()),
            )

        valid = {"durable_accepted": True, "snapshot_as_of": snapshot["snapshot_as_of"]}
        with patch.dict(os.environ, {"VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "offline-test-token-with-32-characters"}), \
             patch.object(runtime, "urlopen", side_effect=http_error(valid)):
            with self.assertRaises(runtime.CollectorStageBlocked) as caught:
                runtime._persist_verified_snapshot_durably(snapshot)
        self.assertTrue(caught.exception.durable_accepted)
        self.assertEqual(caught.exception.durable_snapshot_as_of, snapshot["snapshot_as_of"])
        self.assertEqual(runtime._safe_error_code(caught.exception), "DURABLE_SNAPSHOT_PUBLISH_HTTP_503")

        invalid_receipts = (
            {"durable_accepted": False, "snapshot_as_of": snapshot["snapshot_as_of"]},
            {"durable_accepted": True, "snapshot_as_of": "2026-10-02T00:00:00+00:00"},
            {"durable_accepted": 1, "snapshot_as_of": snapshot["snapshot_as_of"]},
            {"durable_accepted": True},
            ["durable_accepted", snapshot["snapshot_as_of"]],
        )
        for payload in invalid_receipts:
            with patch.dict(os.environ, {"VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "offline-test-token-with-32-characters"}), \
                 patch.object(runtime, "urlopen", side_effect=http_error(payload)):
                with self.assertRaises(runtime.CollectorStageBlocked) as rejected:
                    runtime._persist_verified_snapshot_durably(snapshot)
            self.assertFalse(rejected.exception.durable_accepted)
            self.assertIsNone(rejected.exception.durable_snapshot_as_of)

    def test_missing_canonical_shard_with_confirmed_snapshot_never_falls_back_to_seed(self):
        old = {"snapshot_as_of": "2026-10-02T00:00:00+00:00", "collection_coverage": {"complete": True}}
        cache = MemoryCache({runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY: old})
        with patch.object(runtime, "_bootstrap_tjmugh_records", side_effect=AssertionError("seed overwrite")):
            with self.assertRaises(runtime.CollectorPrecondition) as caught:
                runtime._cached_list(cache, runtime.TJMUGH_RECORDS_KEY, runtime._bootstrap_tjmugh_records)
        self.assertEqual(str(caught.exception), "COLLECTOR_CANONICAL_HISTORY_UNAVAILABLE")

    def test_incremental_revision_keeps_last_complete_anchor_and_inherits_known_failures(self):
        now = "2026-10-03T00:00:00+00:00"
        anchor = "2026-10-01T00:00:00+00:00"
        cache = self._canonical_cache()
        old_snapshot = {
            "snapshot_as_of": "2026-10-02T00:00:00+00:00",
            "cards": [], "opportunity_pool": [],
            "collection_coverage": {
                "complete": False,
                "last_complete_as_of": anchor,
                "failed_source_ids": ["ccgp"],
            },
        }
        cache.values[runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY] = old_snapshot
        cache.values[runtime.LATEST_RUNTIME_SNAPSHOT_KEY] = old_snapshot
        cache.values[runtime.META_KEY] = {
            "local_date": "2026-10-03",
            "stages": {
                "teda": {"status": "FAILED", "terminal": True, "diagnostics": [{"source_id": "teda"}]},
                "tjmugh": {"status": "COMPLETED", "terminal": True, "result": {"failure_count": 0}},
            },
        }
        accepted = {}
        def accept(candidate):
            accepted["snapshot"] = candidate
            return {"snapshot_as_of": candidate["snapshot_as_of"], "opportunity_pool_count": 0}
        with patch.object(runtime, "_persist_verified_snapshot_durably", side_effect=accept):
            runtime._run_publish(cache, {
                "cycle_as_of": now,
                "incremental_source": "tjmugh",
                "last_complete_as_of": anchor,
            })
        coverage = accepted["snapshot"]["collection_coverage"]
        self.assertEqual(accepted["snapshot"]["snapshot_as_of"], now)
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["last_complete_as_of"], anchor)
        self.assertEqual(coverage["updated_source_ids"], ["tjmugh"])
        self.assertEqual(coverage["failed_source_ids"], ["ccgp", "teda"])

    def test_incremental_canonical_write_failure_retains_pending_fact_for_same_bucket_retry(self):
        class FailCanonicalWriteOnce(MemoryCache):
            def __init__(self, values):
                super().__init__(values)
                self.failed = False

            def set(self, key, value, options=None):
                if key == runtime.TJNOTHOP_RECORDS_KEY and value and not self.failed:
                    self.failed = True
                    raise RuntimeError("OFFLINE_CANONICAL_WRITE_FAILED secret-value")
                return super().set(key, value, options)

        cache = FailCanonicalWriteOnce(self._canonical_cache().values)
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        record = dict(runtime._bootstrap_tjmugh_records()[-1])
        record["opportunity_id"] = "offline-canonical-write-failure"
        candidate = {
            "detail_url": "https://www.tjnothop.com/system/2026/10/02/offline.shtml",
            "title": "医疗设备市场调研",
            "published_at": "2026-10-02",
            "index_url": "https://www.tjnothop.com/index",
        }
        with patch.dict(incremental._DISCOVERY, {"tjnothop": lambda _now: [candidate]}), \
             patch.dict(incremental._VERIFICATION, {"tjnothop": lambda *_args: record}), \
             patch("collector_incremental_bootstrap.bootstrap_incremental_ledger_from_canonical", return_value=None), \
             patch.object(runtime.time, "sleep"), \
             patch.object(incremental, "_publish_snapshot_if_ready", return_value=(True, {"snapshot_as_of": now.isoformat()})) as publish:
            status1, result1 = incremental.run_incremental_source("tjnothop", now=now, cache=cache)
            self.assertEqual(status1, 503)
            self.assertEqual(result1["error"], "INCREMENTAL_CANONICAL_COMMIT_FAILED")
            self.assertEqual(len(cache.get(runtime.TJNOTHOP_RECORDS_KEY)), 0)
            self.assertEqual(len(incremental._load_pending_records(cache, "tjnothop")), 1)
            self.assertNotIn("secret-value", repr(result1))

            status2, result2 = incremental.run_incremental_source(
                "tjnothop", now=now.replace(minute=1), cache=cache,
            )
        self.assertEqual(status2, 200)
        self.assertEqual(result2["action"], "COMPLETED")
        self.assertTrue(result2["snapshot_refreshed"])
        self.assertEqual(len(cache.get(runtime.TJNOTHOP_RECORDS_KEY)), 1)
        self.assertEqual(incremental._load_pending_records(cache, "tjnothop"), [])
        publish.assert_called_once()

    def test_incremental_pending_write_failure_keeps_candidate_retryable(self):
        class FailPendingWriteOnce(MemoryCache):
            def __init__(self, values):
                super().__init__(values)
                self.failed = False

            def set(self, key, value, options=None):
                if key == incremental._pending_cache_key("tjnothop") and value and not self.failed:
                    self.failed = True
                    raise RuntimeError("OFFLINE_PENDING_WRITE_FAILED")
                return super().set(key, value, options)

        cache = FailPendingWriteOnce(self._canonical_cache().values)
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        record = dict(runtime._bootstrap_tjmugh_records()[-1])
        record["opportunity_id"] = "offline-pending-write-failure"
        candidate = {
            "detail_url": "https://www.tjnothop.com/system/2026/10/02/pending.shtml",
            "title": "医疗设备市场调研",
            "published_at": "2026-10-02",
            "index_url": "https://www.tjnothop.com/index",
        }
        with patch.dict(incremental._DISCOVERY, {"tjnothop": lambda _now: [candidate]}), \
             patch.dict(incremental._VERIFICATION, {"tjnothop": lambda *_args: record}), \
             patch("collector_incremental_bootstrap.bootstrap_incremental_ledger_from_canonical", return_value=None), \
             patch.object(runtime.time, "sleep"), \
             patch.object(incremental, "_publish_snapshot_if_ready", return_value=(True, {"snapshot_as_of": now.isoformat()})) as publish:
            status1, result1 = incremental.run_incremental_source("tjnothop", now=now, cache=cache)
            self.assertEqual(status1, 503)
            self.assertEqual(result1["error"], "INCREMENTAL_PENDING_RECORD_PERSIST_FAILED")
            self.assertEqual(len(cache.get(runtime.TJNOTHOP_RECORDS_KEY)), 0)
            self.assertEqual(incremental._load_pending_records(cache, "tjnothop"), [])

            status2, result2 = incremental.run_incremental_source(
                "tjnothop", now=now.replace(minute=1), cache=cache,
            )
        self.assertEqual(status2, 200)
        self.assertEqual(result2["action"], "COMPLETED")
        self.assertTrue(result2["snapshot_refreshed"])
        self.assertEqual(len(cache.get(runtime.TJNOTHOP_RECORDS_KEY)), 1)
        publish.assert_called_once()

    def test_incremental_empty_scan_does_not_advance_global_snapshot(self):
        old = {"snapshot_as_of": "2026-10-02T00:00:00+00:00", "cards": [], "opportunity_pool": [],
               "collection_coverage": {"complete": True, "last_complete_as_of": "2026-10-02T00:00:00+00:00", "failed_source_ids": []}}
        cache = self._canonical_cache()
        cache.values[runtime.TJMUGH_RECORDS_KEY] = []
        cache.values[runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY] = old
        cache.values[runtime.LATEST_RUNTIME_SNAPSHOT_KEY] = old
        with patch.dict(incremental._DISCOVERY, {"tjmugh": lambda _now: []}), \
             patch("collector_incremental_bootstrap.bootstrap_incremental_ledger_from_canonical", return_value=None), \
             patch.object(incremental, "_publish_snapshot_if_ready") as publish:
            status, result = incremental.run_incremental_source(
                "tjmugh", now=datetime(2026, 10, 3, tzinfo=timezone.utc), cache=cache,
            )
        self.assertEqual(status, 200)
        self.assertFalse(result["snapshot_refreshed"])
        self.assertEqual(result["deferred_reason"], "NO_SOURCE_CANONICAL_CHANGE")
        publish.assert_not_called()
        self.assertEqual(cache.get(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY), old)

    def test_incremental_same_facts_with_new_observed_at_does_not_publish(self):
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        previous = dict(runtime._bootstrap_tjmugh_records()[-1])
        url = previous["source"]["url"]
        previous["source"]["observed_at"] = "2026-10-02T00:00:00+00:00"
        rescanned = {
            **previous,
            "source": {**previous["source"], "observed_at": now.isoformat()},
        }
        cache = self._canonical_cache()
        cache.values[runtime.TJMUGH_RECORDS_KEY] = [previous]
        candidate = {
            "detail_url": url,
            "title": previous["facts"]["project_name"],
            "published_at": previous["facts"]["published_at"],
            "index_url": url,
        }
        with patch.dict(incremental._DISCOVERY, {"tjmugh": lambda _now: [candidate]}), \
             patch.dict(incremental._VERIFICATION, {"tjmugh": lambda *_args: rescanned}), \
             patch("collector_incremental_bootstrap.bootstrap_incremental_ledger_from_canonical", return_value=None), \
             patch.object(runtime.time, "sleep"), \
             patch.object(incremental, "_publish_snapshot_if_ready") as publish:
            status, result = incremental.run_incremental_source("tjmugh", now=now, cache=cache)
        self.assertEqual(status, 200)
        self.assertFalse(result["snapshot_refreshed"])
        self.assertEqual(result["deferred_reason"], "NO_SOURCE_CANONICAL_CHANGE")
        self.assertEqual(cache.get(runtime.TJMUGH_RECORDS_KEY), [previous])
        publish.assert_not_called()

    def test_canonical_change_comparison_ignores_observation_timestamp_only(self):
        previous = [{"opportunity_id": "a", "source": {"observed_at": "2026-10-02T00:00:00Z"}, "facts": {"title": "same"}}]
        rescanned = [{"opportunity_id": "a", "source": {"observed_at": "2026-10-03T00:00:00Z"}, "facts": {"title": "same"}}]
        self.assertEqual(runtime._canonical_content_digest(previous), runtime._canonical_content_digest(rescanned))
        changed_fact = [{"opportunity_id": "a", "source": {"observed_at": "2026-10-03T00:00:00Z"}, "facts": {"title": "changed"}}]
        self.assertNotEqual(runtime._canonical_content_digest(previous), runtime._canonical_content_digest(changed_fact))

    def test_real_tjmugh_adapter_reverification_changes_no_canonical_facts(self):
        from medical_channel_pipeline.tjmugh_market_research import parse_tjmugh_market_research

        html = """
        <html><body>
        <h3>天津医科大学总医院医疗设备项目市场调研论证邀请函</h3>
        <div>2026-08-31 09:00</div>
        <p>天津医科大学总医院设备采购科拟开展院内项目市场调研论证。</p>
        <p>一、论证项目名称：</p><p>（1）设备甲（2）设备乙2套</p>
        <p>二、供应商参加本次论证活动必须提供下列相关材料：</p>
        <p>本次报名现场报名，报名截止时间为：2026年9月3日下午17：00点前。</p>
        </body></html>
        """
        first = parse_tjmugh_market_research(
            html,
            source_url="https://www.tjmugh.com.cn/system/2026/08/31/030337994.shtml",
            observed_at="2026-09-01T18:43:00Z",
            opportunity_id="tjmugh_20260831_030337994",
        )
        second = parse_tjmugh_market_research(
            html,
            source_url="https://www.tjmugh.com.cn/system/2026/08/31/030337994.shtml",
            observed_at="2026-09-02T18:43:00Z",
            opportunity_id="tjmugh_20260831_030337994",
        )
        self.assertNotEqual(first["source"]["observed_at"], second["source"]["observed_at"])
        self.assertEqual(runtime._canonical_content_digest([first]), runtime._canonical_content_digest([second]))

    def test_wrapped_http_403_codes_map_to_access_denied(self):
        for code in ("TJMUGH_HTTP_403", "TJNOTHOP_HTTP_403", "TEDA_HTTP_403"):
            self.assertEqual(runtime._diagnostic_category(RuntimeError(code)), "ACCESS_DENIED")

    def test_failed_dependency_blocks_events_but_does_not_block_independent_source(self):
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        state = runtime._new_cycle(now)
        state["stages"]["ccgp"] = {"status": "FAILED", "terminal": True, "attempt_count": 2}
        cache = MemoryCache({runtime.META_KEY: state})
        event_state, blocked = runtime._prepare_stage(cache, "event1", now)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertTrue(blocked["terminal"])
        self.assertEqual(blocked["diagnostics"][0]["category"], "DEPENDENCY_BLOCKED")
        for stage in runtime.STAGE_ORDER[1:runtime.STAGE_ORDER.index("tjmugh")]:
            event_state["stages"][stage] = {"status": "FAILED", "terminal": True, "attempt_count": 2}
        cache.values[runtime.META_KEY] = event_state
        independent_state, previous = runtime._prepare_stage(cache, "tjmugh", now)
        self.assertIsNone(previous)
        self.assertEqual(independent_state["stages"]["tjmugh"]["status"], "RUNNING")

    def test_failure_diagnostic_drops_raw_message_and_untrusted_url_parts(self):
        exc = runtime.CollectorStageBlocked(
            "TJMUGH_INDEX_DISCOVERY_FAILED",
            diagnostics=[{
                "stage": "verified_detail",
                "error": "HTTPError",
                "message": "HTTP Error 403: Bearer secret-token patient-name",
                "url": "https://www.tjmugh.com.cn/cgxxtzgg/index.shtml?token=secret#x",
            }],
        )
        diagnostic = runtime._bounded_diagnostics("tjmugh", exc)[0]
        self.assertEqual(diagnostic["source_id"], "tjmugh")
        self.assertEqual(diagnostic["category"], "ACCESS_DENIED")
        self.assertEqual(diagnostic["error_code"], "HTTP_403")
        serialized = repr(diagnostic)
        for secret in ("Bearer", "secret-token", "patient-name", "?token", "#x"):
            self.assertNotIn(secret, serialized)

    def test_terminal_failure_advances_queue_without_starting_intraday(self):
        cycle_as_of = "2026-10-03T00:00:00+00:00"
        stage_result = {"action": "FAILED", "terminal": True, "error_code": "HTTP_403"}
        with patch.object(queue, "same_china_business_date", return_value=True), \
             patch.object(queue, "_active_cycle_matches", return_value=True), \
             patch.object(runtime, "run_stage", return_value=(503, stage_result)), \
             patch.object(queue, "_enqueue_stage", new_callable=AsyncMock) as enqueue, \
             patch.object(queue, "_release_active_cycle_if_owned") as release:
            asyncio.run(queue.process_collector_payload({
                "schema_version": "0.1", "schedule_version": queue.SCHEDULE_VERSION, "stage": "tjmugh", "cycle_id": "prod:2026-10-03:morning:twice-daily-v1", "cycle_as_of": cycle_as_of,
            }))
        enqueue.assert_awaited_once()
        self.assertEqual(enqueue.await_args.kwargs["stage"], "tjnothop")
        release.assert_not_called()

        blocked_publish = {"action": "BLOCKED", "terminal": True, "error_code": "COLLECTOR_PUBLISH_SOURCE_FAILED"}
        with patch.object(queue, "same_china_business_date", return_value=True), \
             patch.object(queue, "_active_cycle_matches", return_value=True), \
             patch.object(runtime, "run_stage", return_value=(409, blocked_publish)), \
             patch.object(queue, "_start_intraday_chain_after_deep", new_callable=AsyncMock) as intraday, \
             patch.object(queue, "_release_active_cycle_if_owned") as release, \
             patch.object(incremental, "clear_incremental_pending") as clear_pending:
            asyncio.run(queue.process_collector_payload({
                "schema_version": "0.1", "schedule_version": queue.SCHEDULE_VERSION, "stage": "publish", "cycle_id": "prod:2026-10-03:morning:twice-daily-v1", "cycle_as_of": cycle_as_of,
            }))
        intraday.assert_not_awaited()
        release.assert_called_once_with("prod:2026-10-03:morning:twice-daily-v1")
        clear_pending.assert_not_called()

    def test_run_stage_reports_state_read_failure_as_structured_503(self):
        class FailingReadCache:
            def get(self, _key):
                raise RuntimeError("cache read secret-value")
        with patch.object(runtime, "RuntimeCache", FailingReadCache):
            status, result = runtime.run_stage("tjmugh", now=datetime(2026, 10, 3, tzinfo=timezone.utc))
        self.assertEqual(status, 503)
        self.assertEqual(result["action"], "FAILED")
        self.assertEqual(result["error_code"], "COLLECTOR_STATE_READ_FAILED")
        self.assertNotIn("secret-value", repr(result))

    def test_run_stage_keeps_source_failure_when_failure_status_write_fails(self):
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        state = runtime._new_cycle(now)
        source_error = runtime.CollectorStageBlocked(
            "TJMUGH_INDEX_DISCOVERY_FAILED",
            diagnostics=[{
                "stage": "index_discovery", "error": "HTTPError",
                "message": "HTTP Error 403: private-response-token",
                "url": "https://www.tjmugh.com.cn/cgxxtzgg/index.shtml",
            }],
        )
        with patch.object(runtime, "RuntimeCache", return_value=MemoryCache()), \
             patch.object(runtime, "_prepare_stage", return_value=(state, None)), \
             patch.object(runtime, "_run_tjmugh", side_effect=source_error), \
             patch.object(runtime, "_mark_failed", side_effect=RuntimeError("cache write secret-value")):
            status, result = runtime.run_stage("tjmugh", now=now)
        self.assertEqual(status, 503)
        self.assertEqual(result["error_code"], "COLLECTOR_FAILURE_STATE_PERSIST_FAILED")
        self.assertFalse(result["state_persisted"])
        self.assertEqual(result["diagnostics"][0]["source_id"], "tjmugh")
        self.assertEqual(result["diagnostics"][0]["category"], "ACCESS_DENIED")
        self.assertEqual(result["diagnostics"][1]["error_code"], "CACHE_WRITE_FAILED")
        self.assertNotIn("private-response-token", repr(result))
        self.assertNotIn("secret-value", repr(result))

    def test_run_stage_completion_status_write_failure_is_structured_503(self):
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        state = runtime._new_cycle(now)
        with patch.object(runtime, "RuntimeCache", return_value=MemoryCache()), \
             patch.object(runtime, "_prepare_stage", return_value=(state, None)), \
             patch.object(runtime, "_run_tjmugh", return_value={"new_verified_record_count": 0}), \
             patch.object(runtime, "_mark_completed", side_effect=RuntimeError("cache write failed")):
            status, result = runtime.run_stage("tjmugh", now=now)
        self.assertEqual(status, 503)
        self.assertEqual(result["error_code"], "COLLECTOR_COMPLETION_STATE_PERSIST_FAILED")

    def test_run_stage_reports_matching_durable_acceptance_after_http_failure(self):
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        accepted_as_of = "2026-10-03T00:00:00+00:00"
        error = runtime.CollectorStageBlocked(
            "DURABLE_SNAPSHOT_PUBLISH_HTTP_503",
            durable_accepted=True,
            durable_snapshot_as_of=accepted_as_of,
        )
        with patch.object(runtime, "RuntimeCache", return_value=MemoryCache()), \
             patch.object(runtime, "_prepare_stage", return_value=(runtime._new_cycle(now), None)), \
             patch.object(runtime, "_run_publish", side_effect=error):
            status, result = runtime.run_stage("publish", now=now)
        self.assertEqual(status, 503)
        self.assertTrue(result["durable_snapshot_accepted"])
        self.assertEqual(result["durable_snapshot_as_of"], accepted_as_of)
        self.assertFalse(result["state_persisted"])


if __name__ == "__main__":
    unittest.main()
