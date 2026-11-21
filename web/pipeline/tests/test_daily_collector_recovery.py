from contextlib import contextmanager
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

WEB_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def collector_modules():
    fake_functions = ModuleType("vercel.functions")
    fake_functions.RuntimeCache = MagicMock()
    fake_queue = ModuleType("vercel.queue")
    fake_queue.send = AsyncMock()
    with patch.dict(sys.modules, {"vercel": ModuleType("vercel"),
                                  "vercel.functions": fake_functions,
                                  "vercel.queue": fake_queue}), patch.object(
                                      sys, "path", [str(WEB_ROOT), *sys.path]):
        yield importlib.import_module("collector_queue")


class DailyCollectorRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_restriction_never_schedules_next_stage_or_second_request(self):
        with collector_modules() as queue, patch.object(
            queue, "_active_cycle_matches", return_value=True
        ), patch.object(queue, "_release_active_cycle_if_owned") as release, patch.object(
            queue, "_enqueue_stage", new_callable=AsyncMock
        ) as enqueue, patch.object(
            queue.runtime, "run_stage", return_value=(
                503, {"error": "CCGP_UPSTREAM_ACCESS_RESTRICTED:HTTP_429"}
            )
        ) as run_stage:
            await queue.process_collector_payload({"schema_version": "0.1", "stage": "ccgp",
                                                  "cycle_id": "test-cycle",
                                                  "cycle_as_of": "2026-11-21T00:20:00+00:00"})
            run_stage.assert_called_once()
            release.assert_called_once_with("test-cycle")
            enqueue.assert_not_awaited()

    def test_blocked_source_does_not_write_or_publish_a_partial_snapshot(self):
        with collector_modules() as queue, patch.object(
            queue.runtime, "_cached_list", return_value=([], False)
        ), patch.object(queue.runtime, "_cache_set") as write, patch.object(
            queue.runtime, "discover_candidates"
        ) as discover:
            def restricted(**kwargs):
                kwargs["failures"].append({
                    "stage": "discovery_search", "diagnostic_code": "HTTP_429",
                })
                return []
            discover.side_effect = restricted
            with self.assertRaisesRegex(queue.runtime.CollectorStageBlocked,
                                        "CCGP_UPSTREAM_ACCESS_RESTRICTED:HTTP_429"):
                queue.runtime._run_ccgp(MagicMock(), {
                    "cycle_as_of": "2026-11-21T08:20:00+08:00",
                })
            discover.assert_called_once()
            write.assert_not_called()

    def test_detail_restriction_stops_before_second_detail_or_cache_write(self):
        from types import SimpleNamespace
        urls = ["https://www.ccgp.gov.cn/cggg/a", "https://www.ccgp.gov.cn/cggg/b"]
        candidates = [("公开招标", SimpleNamespace(detail_url=url, published_at="2026-11-21")) for url in urls]
        for response in (RuntimeError("CCGP_DETAIL_HTTP_429"), "<p>您的访问过于频繁</p>"):
            with self.subTest(response=response), collector_modules() as queue, patch.object(
                queue.runtime, "_cached_list", return_value=([], False)
            ), patch.object(queue.runtime, "_cache_set") as write, patch.object(
                queue.runtime, "discover_candidates", side_effect=[candidates, [], [], [], []]
            ), patch.object(queue.runtime.time, "sleep"), patch.object(
                queue.runtime, "fetch_ccgp_detail_html"
            ) as fetch:
                if isinstance(response, Exception):
                    fetch.side_effect = response
                else:
                    fetch.return_value = response
                with self.assertRaisesRegex(queue.runtime.CollectorStageBlocked,
                                            "CCGP_UPSTREAM_ACCESS_RESTRICTED:"):
                    queue.runtime._run_ccgp(MagicMock(), {
                        "cycle_as_of": "2026-11-21T08:20:00+08:00",
                    })
                fetch.assert_called_once()
                write.assert_not_called()

    def test_event_search_restriction_stops_batch_without_writing_events(self):
        from urllib.error import HTTPError
        with collector_modules() as queue, patch.object(
            queue.runtime, "_cached_list", return_value=([], False)
        ), patch.object(queue.runtime, "_cache_set") as write, patch(
            "sync_ccgp_query.fetch_search_page",
            side_effect=HTTPError("https://example.invalid/", 429, "", None, None),
        ) as fetch:
            cache = MagicMock()
            cache.get.return_value = ["TEST-01", "TEST-02"]
            with self.assertRaisesRegex(queue.runtime.CollectorStageBlocked,
                                        "CCGP_UPSTREAM_ACCESS_RESTRICTED:HTTP_429"):
                queue.runtime._run_event_batch(cache, {
                    "cycle_as_of": "2026-11-21T08:20:00+08:00",
                    "stages": {"ccgp": {"result": {
                        "start_date": "2026-11-19", "end_date": "2026-11-21",
                    }}},
                }, "event1")
            fetch.assert_called_once()
            write.assert_not_called()

    def test_durable_acknowledgement_accepts_zero_and_rejects_inexact_counts(self):
        with collector_modules() as queue:
            runtime = queue.runtime
            snapshot = {"snapshot_as_of": "2026-11-21T00:20:00+00:00",
                        "opportunity_pool": []}
            for actual in (0, None, False, "0", 1):
                with self.subTest(actual=actual), patch.dict(
                    "os.environ", {"VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "test-only-token-" * 3, "VERCEL_ENV": "production"}
                ), patch.object(runtime, "urlopen") as open_url:
                    response = open_url.return_value.__enter__.return_value
                    response.status = 200
                    response.read.return_value = json.dumps({
                        "ok": True, "snapshot_as_of": snapshot["snapshot_as_of"],
                        "opportunity_pool_count": actual,
                    }).encode()
                    if type(actual) is int and actual == 0:
                        self.assertEqual(runtime._persist_verified_snapshot_durably(snapshot)
                                         ["opportunity_pool_count"], 0)
                    else:
                        with self.assertRaisesRegex(runtime.CollectorStageBlocked,
                                                    "DURABLE_SNAPSHOT_PUBLISH_POOL_MISMATCH"):
                            runtime._persist_verified_snapshot_durably(snapshot)

    def test_crashed_prior_day_can_restart_but_recent_or_current_cycle_is_protected(self):
        from datetime import datetime, timezone
        from importlib.util import module_from_spec, spec_from_file_location
        with collector_modules() as queue:
            spec = spec_from_file_location("collector_cron_test", WEB_ROOT / "api" / "collector-run.py")
            trigger = module_from_spec(spec)
            spec.loader.exec_module(trigger)
            now = datetime(2026, 11, 22, 0, 20, tzinfo=timezone.utc)
            for yesterday_started, active_date, allowed in (
                ("2026-11-21T00:25:00+00:00", "2026-11-21", True),
                ("2026-11-21T00:25:00+00:00", None, True),
                ("2026-11-22T00:10:00+00:00", "2026-11-21", False),
                ("2026-11-21T00:25:00+00:00", "2026-11-22", False),
                ("unknown", None, False),
            ):
                with self.subTest(started=yesterday_started, active_date=active_date):
                    data = {trigger.META_KEY: {"local_date": "2026-11-21", "stages": {
                        "event1": {"status": "RUNNING", "started_at": yesterday_started}
                    }}, trigger.ACTIVE_CYCLE_KEY: (
                        {"local_date": active_date, "cycle_id": f"prod:{active_date}"} if active_date else None
                    )}
                    cache = MagicMock()
                    cache.get.side_effect = data.get
                    cache.set.side_effect = lambda key, value, opts: data.__setitem__(key, value)
                    args = dict(cycle_id="prod:2026-11-22", now=now,
                                local_date="2026-11-22", source="test")
                    if allowed:
                        trigger._activate_cycle(cache, **args)
                        self.assertEqual(data[trigger.ACTIVE_CYCLE_KEY]["cycle_id"], "prod:2026-11-22")
                    else:
                        with self.assertRaises(trigger.CollectorStartConflict):
                            trigger._activate_cycle(cache, **args)
                        cache.set.assert_not_called()

    def test_late_prior_day_message_cannot_run_even_if_old_lease_still_matches(self):
        with collector_modules() as queue:
            result = queue.deep_message_lease_disposition(
                {"cycle_id": "prod:2026-11-21"}, {}, cycle_id="prod:2026-11-21",
                cycle_local_date="2026-11-21", current_local_date="2026-11-22")
            self.assertEqual(result, "EXPIRED_STALE")

    def test_event_batch_with_one_timeout_never_writes_partial_result(self):
        with collector_modules() as queue, patch.object(
            queue.runtime, "_cached_list", return_value=([], False)
        ), patch.object(queue.runtime, "_cache_set") as write, patch.object(
            queue.runtime, "scan_events"
        ) as scan:
            def partial(project, **kwargs):
                kwargs["failures"].append(
                    {"stage": "event_search", "project_number": project,
                     "diagnostic_code": "FETCH_TIMEOUT"}
                )
                return []
            scan.side_effect = partial
            cache = MagicMock()
            cache.get.return_value = ["TEST-01"]
            with self.assertRaisesRegex(queue.runtime.CollectorStageBlocked,
                                        "EVENT_WATCH_SEARCH_INCOMPLETE:TEST-01"):
                queue.runtime._run_event_batch(cache, {
                    "cycle_as_of": "2026-11-21T08:20:00+08:00",
                    "stages": {"ccgp": {"result": {
                        "start_date": "2026-11-19", "end_date": "2026-11-21",
                    }}},
                }, "event1")
            write.assert_not_called()

    def test_retry_reuses_successful_empty_search_and_only_reissues_failed_type(self):
        from urllib.parse import parse_qs, urlsplit
        with collector_modules() as queue, patch.object(
            queue.runtime, "_cached_list", return_value=([], False)
        ), patch.object(queue.runtime.time, "sleep"), patch(
            "sync_ccgp_query.fetch_search_page"
        ) as fetch:
            rt = queue.runtime
            data = {rt.CCGP_WATCH_KEY: ["TEST-01"]}
            cache = MagicMock()
            cache.get.side_effect = data.get
            cache.set.side_effect = lambda k, v, opts: data.__setitem__(k, json.loads(json.dumps(v)))
            def state(date):
                return {"cycle_as_of": f"{date}T08:20:00+08:00",
                        "stages": {"ccgp": {"result": {
                            "start_date": "2026-11-19", "end_date": date,
                        }}}}
            empty = '<ul class="vT-srch-result-list-bid"></ul>'
            fetch.side_effect = [empty, TimeoutError(), empty, empty, empty]
            with self.assertRaisesRegex(rt.CollectorStageBlocked, "EVENT_WATCH_SEARCH_INCOMPLETE"):
                rt._run_event_batch(cache, state("2026-11-21"), "event1")
            self.assertNotIn(rt.CCGP_EVENTS_KEY, data)
            self.assertEqual(fetch.call_count, 2)
            rt._run_event_batch(cache, state("2026-11-21"), "event1")
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual(data[rt.CCGP_EVENTS_KEY], [])
            rt._run_event_batch(cache, state("2026-11-22"), "event1")
            self.assertEqual(fetch.call_count, 5)
            sent_types = [parse_qs(urlsplit(call.args[0]).query)["bidType"][0]
                          for call in fetch.call_args_list]
            self.assertEqual(sent_types, ["6", "10", "10", "6", "10"])

    async def test_two_daily_cycles_keep_serving_old_snapshot_until_verified_publish(self):
        from datetime import datetime

        with collector_modules() as queue:
            rt = queue.runtime
            published_key = rt.PUBLISHED_RUNTIME_SNAPSHOT_KEY
            prior = {"snapshot_as_of": "2026-11-20T08:20:00+08:00", "opportunity_pool": []}
            data = {published_key: prior}
            cache = MagicMock()
            cache.get.side_effect = data.get
            cache.set.side_effect = lambda k, v, opts: data.__setitem__(k, json.loads(json.dumps(v)))
            cache.delete.side_effect = lambda k: data.pop(k, None)

            def seed_other_sources(_cache, _state, *_extra):
                for key in (rt.TJMUGH_RECORDS_KEY, rt.TJNOTHOP_RECORDS_KEY,
                            rt.TEDA_RECORDS_KEY, rt.TJFCH_RECORDS_KEY,
                            *(rt._regional_records_key(m) for m in rt.REGIONAL_STAGE_MARKET_CODES.values())):
                    data[key] = []
                return {}

            def ack(request, timeout):
                snapshot = json.loads(request.data)
                return fake_response(snapshot)

            def fake_response(snapshot):
                obj = MagicMock()
                response = obj.__enter__.return_value
                response.status = 200
                response.read.return_value = json.dumps({
                    "ok": True, "snapshot_as_of": snapshot["snapshot_as_of"],
                    "opportunity_pool_count": len(snapshot["opportunity_pool"]),
                }).encode()
                return obj

            def message(day, stage):
                return {"schema_version": "0.1", "stage": stage,
                        "cycle_as_of": f"{day}T08:20:00+08:00", "cycle_id": f"prod:{day}"}

            def seed_ccgp(_cache, _state):
                data[rt.CCGP_WATCH_KEY] = ["TEST-01"]
                data[rt.CCGP_RECORDS_KEY] = []
                data[rt.CCGP_EVENTS_KEY] = []
                return {"start_date": "2026-11-19", "end_date": _state["local_date"]}

            class FixedDate(datetime):
                current = None
                @classmethod
                def now(cls, tz=None):
                    return cls.current if tz is None else cls.current.astimezone(tz)

            from contextlib import ExitStack
            with ExitStack() as st:
                for m in (queue, rt):
                    st.enter_context(patch.object(m, "RuntimeCache", return_value=cache))
                st.enter_context(patch.object(queue, "datetime", FixedDate))
                st.enter_context(patch.object(rt, "_run_ccgp", side_effect=seed_ccgp))
                for meth in ("_run_tjmugh", "_run_tjnothop", "_run_teda", "_run_tjfch", "_run_regional_market"):
                    st.enter_context(patch.object(rt, meth, side_effect=seed_other_sources))
                st.enter_context(patch.object(rt.time, "sleep"))
                st.enter_context(patch.dict("os.environ", {"VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "isolated-test-only-" * 3, "VERCEL_ENV": "production"}))
                st.enter_context(patch.object(queue.incremental_runtime, "clear_incremental_pending"))
                st.enter_context(patch.object(queue, "_start_intraday_chain_after_deep", new_callable=AsyncMock))
                push = st.enter_context(patch.object(queue, "_enqueue_stage", new_callable=AsyncMock))
                durable = st.enter_context(patch.object(rt, "urlopen", side_effect=ack))
                empty = '<ul class="vT-srch-result-list-bid"></ul>'
                fetch = st.enter_context(patch("sync_ccgp_query.fetch_search_page",
                    side_effect=[empty, TimeoutError(), empty, empty, empty]))
                for day_index, day in enumerate(("2026-11-21", "2026-11-22")):
                    FixedDate.current = datetime.fromisoformat(day + "T00:20:00+00:00")
                    data[queue.ACTIVE_CYCLE_KEY] = {"cycle_id": f"prod:{day}", "local_date": day}
                    before = data[published_key]
                    for stage in queue.STAGE_ORDER:
                        if day_index == 0 and stage == "event1":
                            with self.assertRaisesRegex(RuntimeError, "EVENT_WATCH_SEARCH_INCOMPLETE"):
                                await queue.process_collector_payload(message(day, stage))
                            self.assertEqual(data[published_key], before)
                            self.assertEqual(durable.call_count, 0)
                            self.assertEqual(push.await_args.kwargs["stage"], "event1")
                        await queue.process_collector_payload(message(day, stage))
                    self.assertEqual(data[published_key]["snapshot_as_of"], f"{day}T08:20:00+08:00")
                    self.assertEqual(data[rt.META_KEY]["stages"]["publish"]["status"], "COMPLETED")
                    self.assertNotIn(queue.ACTIVE_CYCLE_KEY, data)
                self.assertEqual(durable.call_count, 2)
                self.assertEqual(fetch.call_count, 5)
                self.assertEqual(push.await_count, 2 * (len(queue.STAGE_ORDER) - 1))

    async def test_unavailable_ccgp_moves_to_independent_official_hospital(self):
        with collector_modules() as queue, patch.object(
            queue, "_active_cycle_matches", return_value=True
        ), patch.object(queue, "_release_active_cycle_if_owned") as release, patch.object(
            queue, "_enqueue_stage", new_callable=AsyncMock
        ) as enqueue, patch.object(
            queue.runtime, "quarantine_unavailable_source", return_value=True
        ) as quarantined, patch.object(
            queue.runtime, "run_stage",
            return_value=(503, {"error": "CCGP_PUBLISH_GATE:ALL_DISCOVERY_QUERIES_FAILED"})
        ):
            await queue.process_collector_payload({
                "schema_version": "0.1", "stage": "ccgp", "cycle_id": "test-cycle",
                "cycle_as_of": "2026-11-21T00:20:00+00:00",
            })
            quarantined.assert_called_once_with(
                stage="ccgp", local_date="2026-11-21",
                error="CCGP_PUBLISH_GATE:ALL_DISCOVERY_QUERIES_FAILED",
            )
            enqueue.assert_awaited_once()
            self.assertEqual(enqueue.await_args.kwargs["stage"], "tjmugh")
            release.assert_not_called()

    def test_unavailable_source_quarantine_preserves_failure_provenance(self):
        with collector_modules() as queue:
            rt = queue.runtime
            state = {"local_date": "2026-11-21", "stages": {
                "ccgp": {"status": "FAILED", "attempt_count": 2,
                         "error_message": "CCGP_PUBLISH_GATE:ALL_DISCOVERY_QUERIES_FAILED"},
            }}
            cache = MagicMock()
            with patch.object(rt, "RuntimeCache", return_value=cache), patch.object(
                rt, "load_status", return_value=state
            ), patch.object(rt, "_carry_forward_verified", return_value=65), patch.object(
                rt, "_write_status"
            ) as saved:
                self.assertFalse(rt.quarantine_unavailable_source(
                    stage="ccgp", local_date="2026-11-21",
                    error="CCGP_DETAIL_PARSE_INVALID",
                ))
                saved.assert_not_called()
                self.assertTrue(rt.quarantine_unavailable_source(
                    stage="ccgp", local_date="2026-11-21",
                    error="CCGP_PUBLISH_GATE:ALL_DISCOVERY_QUERIES_FAILED",
                ))
                saved.assert_called_once()
                self.assertEqual(state["stages"]["ccgp"]["status"], "SKIPPED")
                self.assertEqual(state["stages"]["ccgp"]["error_code"], "SOURCE_UNAVAILABLE")
                self.assertEqual(state["stages"]["ccgp"]["result"]["new_verified_record_count"], 0)
                self.assertEqual(state["stages"]["ccgp"]["result"]["verified_carryover_count"], 65)
                for stage in ("event1", "event2", "event3", "event4", "event5", "event6"):
                    self.assertEqual(state["stages"][stage]["status"], "SKIPPED")

    def test_publish_never_relabels_carryover_only_as_fresh_scan(self):
        with collector_modules() as queue:
            rt = queue.runtime
            cache = MagicMock()
            cache.get.return_value = []
            state = {"cycle_as_of": "2026-11-21T08:20:00+08:00",
                     "stages": {"ccgp": {"status": "SKIPPED", "result": {}},
                                "tjmugh": {"status": "SKIPPED", "result": {}},
                                "tjnothop": {"status": "SKIPPED", "result": {}},
                                "teda": {"status": "SKIPPED", "result": {}},
                                "tjfch": {"status": "SKIPPED", "result": {}}}}
            with patch.object(rt, "build_public_snapshot") as build, patch.object(
                rt, "_persist_verified_snapshot_durably"
            ) as durable:
                with self.assertRaisesRegex(rt.CollectorStageBlocked,
                                            "COLLECTOR_NO_SUCCESSFUL_OFFICIAL_SOURCE_TODAY"):
                    rt._run_publish(cache, state)
                build.assert_not_called()
                durable.assert_not_called()

    async def test_synthetic_skipped_regional_stages_keep_queue_moving(self):
        with collector_modules() as queue, patch.object(
            queue, "_active_cycle_matches", return_value=True
        ), patch.object(queue, "_enqueue_stage", new_callable=AsyncMock) as enqueue, patch.object(
            queue.runtime, "run_stage", return_value=(
                200, {"action": "SKIPPED_SOURCE_UNAVAILABLE", "stage": "regional_bj"}
            )
        ):
            await queue.process_collector_payload({
                "schema_version": "0.1", "stage": "regional_bj",
                "cycle_id": "test-cycle",
                "cycle_as_of": "2026-11-21T00:20:00+00:00",
            })
            self.assertEqual(enqueue.await_args.kwargs["stage"], "regional_bj_fallback")

    async def test_source_restriction_retries_only_local_quarantine_not_upstream(self):
        with collector_modules() as queue, patch.object(
            queue, "_active_cycle_matches", return_value=True
        ), patch.object(queue, "_release_active_cycle_if_owned") as release, patch.object(
            queue, "_enqueue_stage", new_callable=AsyncMock
        ) as enqueue, patch.object(
            queue.runtime, "quarantine_unavailable_source", side_effect=[False, True]
        ) as quarantine, patch.object(
            queue.runtime, "run_stage", return_value=(
                503, {"error": "CCGP_UPSTREAM_ACCESS_RESTRICTED:HTTP_429"}
            )
        ) as run_stage:
            await queue.process_collector_payload({
                "schema_version": "0.1", "stage": "ccgp",
                "cycle_id": "test-cycle",
                "cycle_as_of": "2026-11-21T00:20:00+00:00",
            })
            self.assertEqual(quarantine.call_count, 2)
            run_stage.assert_called_once()
            release.assert_not_called()
            enqueue.assert_awaited_once()
            self.assertEqual(enqueue.await_args.kwargs["stage"], "tjmugh")

    async def test_unconfirmed_rate_limit_never_reprobes_and_records_failure(self):
        for stage in ("ccgp", "event2"):
            with self.subTest(stage=stage):
                with collector_modules() as queue, patch.object(
                    queue, "_active_cycle_matches", return_value=True
                ), patch.object(
                    queue, "_release_active_cycle_if_owned"
                ) as release, patch.object(
                    queue, "_enqueue_stage", new_callable=AsyncMock
                ) as enqueue, patch.object(
                    queue.runtime, "quarantine_unavailable_source", return_value=False
                ) as quarantine, patch.object(
                    queue.runtime, "run_stage", return_value=(
                        503, {"error": "CCGP_UPSTREAM_ACCESS_RESTRICTED:SOURCE_RATE_LIMIT"}
                    )
                ) as run_stage, patch("builtins.print") as log:
                    await queue.process_collector_payload({
                        "schema_version": "0.1", "stage": stage,
                        "cycle_id": "test-cycle",
                        "cycle_as_of": "2026-11-21T00:20:00+00:00",
                    })
                    self.assertEqual(quarantine.call_count, 2)
                    run_stage.assert_called_once()
                    release.assert_called_once_with("test-cycle")
                    enqueue.assert_not_awaited()
                    log.assert_called_once_with(
                        f"COLLECTOR_QUARANTINE_UNCONFIRMED:{stage}", flush=True
                    )

    def test_preview_cannot_use_production_snapshot_publisher(self):
        with collector_modules() as queue, patch.dict("os.environ", {"VERCEL_ENV": "preview"}), patch.object(
            queue.runtime, "urlopen"
        ) as open_url:
            with self.assertRaisesRegex(queue.runtime.CollectorStageBlocked,
                                        "DURABLE_PRODUCTION_PUBLISH_DISABLED_OUTSIDE_PRODUCTION"):
                queue.runtime._persist_verified_snapshot_durably({})
            open_url.assert_not_called()
