"""Offline core tests. HTML below is synthetic, NOT captured official evidence.

Network, production dispatch, window attestation and total HTTP deadlines are
deliberately not implemented or accepted by these tests.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from test_collector_native_reliability import MemoryCache, runtime, queue
from collector_schedule import scheduled_cycle
from collector_namespace import ACTIVE_CYCLE_KEY, META_KEY


AS_OF = datetime(2026, 9, 29, 0, 40, tzinfo=timezone.utc)
OBSERVED = AS_OF + timedelta(minutes=1)
DATA = Path(__file__).resolve().parents[1] / "data"


def synthetic_case(stage, *, number="030199113", title=None):
    """Minimal contract fixtures; the 9/28 title/date come from task evidence."""
    if stage == "tjzyefy":
        title = title or "院内调研公告（2026年23号）-肢体康复训练等医疗设备采购项目"
        hospital = "天津中医药大学第二附属医院"
        body = "我院拟对肢体康复训练医疗设备进行院内调研。报名时间：2026年9月28日-2026年10月9日16:00。"
    elif stage == "tjzyefy_intent":
        title = title or "采购意向公告（2026年31号）-脉动真空灭菌器采购项目"
        hospital = "天津中医药大学第二附属医院"
        body = "我院将于近期对天津中医药大学第二附属医院脉动真空灭菌器采购项目进行采购，欢迎各位有资质的供应商咨询。"
    else:
        title = title or "天津市中心妇产科医院病理设备采购项目市场调研公告"
        hospital = "天津市中心妇产科医院"
        body = "天津市中心妇产科医院拟对病理设备开展市场调研。报名时限：自公告发布之日起至2026年10月9日16:00。"
    adapter, _, _, _, _ = runtime._official_source_adapter(stage)
    host = "www.tjzxfc.cn" if stage == "tjzxfc" else "www.tjzyefy.com"
    url = f"https://{host}/system/2026/09/28/{number}.shtml"
    index = f'<a href="{url}">{title}</a>'
    published = "时间：2026-09-28 来源：设备科" if stage == "tjzxfc" else "2026-09-28 发布人：设备科"
    detail = f"<html><h1>{title}</h1><div>{published}</div><p>{hospital}</p><p>{body}</p></html>"
    return index, {url: detail}, adapter.INDEX_URL


class TrackingCache(MemoryCache):
    def __init__(self, values=None):
        super().__init__(values)
        self.writes = []

    def set(self, key, value, options=None):
        self.writes.append((key, deepcopy(value), deepcopy(options)))
        super().set(key, value, options)


class TwiceDailySourceParityTests(unittest.TestCase):
    def setUp(self):
        self.cid, _ = scheduled_cycle(AS_OF, "morning")
        self.state = {"cycle_id": self.cid, "cycle_as_of": AS_OF.isoformat(), "stages": {}}
        self.cache = TrackingCache({
            META_KEY: deepcopy(self.state),
            ACTIVE_CYCLE_KEY: {"cycle_id": self.cid, "cycle_as_of": AS_OF.isoformat()},
            **{key: [] for key in runtime.PRESERVED_SOURCE_RECORDS_KEYS.values()},
            runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY: {"sentinel": "last-good-published"},
            runtime.LATEST_RUNTIME_SNAPSHOT_KEY: {"sentinel": "last-good-latest"},
        })
        token = runtime._SCHEDULED_CYCLE.set(self.cid)
        self.addCleanup(runtime._SCHEDULED_CYCLE.reset, token)
        clock = patch.object(runtime, "_now_utc", return_value=OBSERVED)
        clock.start()
        self.addCleanup(clock.stop)
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection"):
            network = patch(target, side_effect=AssertionError("OFFLINE_NETWORK_FORBIDDEN"))
            network.start()
            self.addCleanup(network.stop)

    def proof(self, stage, index, index_url):
        end = AS_OF.astimezone(runtime.SHANGHAI).date()
        return runtime.OfficialSourceWindowProof(
            stage, index_url, hashlib.sha256(index.encode()).hexdigest(),
            end - timedelta(days=29), end, OBSERVED,
        )

    def prepare(self, stage="tjzyefy", *, case=None, reader=None, window_override=None):
        index, pages, index_url = case or synthetic_case(stage)
        reader = reader or Mock(side_effect=lambda url, deadline: pages[url])
        window = self.proof(stage, index, index_url)
        if window_override:
            window = replace(window, **window_override)
        return runtime._prepare_official_source_refresh(
            self.cache, self.state, stage, index_html=index, window=window, read_detail=reader,
        )

    def commit(self, prepared):
        return runtime._commit_official_source_refresh(self.cache, self.state, prepared)

    def assert_public_unchanged(self):
        self.assertEqual(self.cache.get(runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY), {"sentinel": "last-good-published"})
        self.assertEqual(self.cache.get(runtime.LATEST_RUNTIME_SNAPSHOT_KEY), {"sentinel": "last-good-latest"})

    def test_three_existing_parser_and_stable_id_paths_are_reused(self):
        specs = (
            ("tjzyefy", runtime.tjzyefy_market_research, "parse_tjzyefy_market_research", "MARKET_RESEARCH"),
            ("tjzyefy_intent", runtime.tjzyefy_procurement_intent, "parse_tjzyefy_procurement_intent", "PROCUREMENT_INTENT"),
            ("tjzxfc", runtime.tjzxfc_market_research, "parse_tjzxfc_market_research", "MARKET_RESEARCH"),
        )
        for stage, module, name, lifecycle in specs:
            with self.subTest(stage=stage), patch.object(module, name, wraps=getattr(module, name)) as parser:
                prepared = self.prepare(stage)
                self.assertEqual(self.cache.writes, [])
                result = self.commit(prepared)
                parser.assert_called_once()
                source = runtime.OFFICIAL_SOURCE_STAGE_IDS[stage]
                rows = self.cache.get(runtime.PRESERVED_SOURCE_RECORDS_KEYS[source])
                self.assertEqual(rows[0]["source"]["source_id"], f'{source}:{rows[0]["opportunity_id"]}')
                self.assertEqual(rows[0]["facts"]["lifecycle_state"], lifecycle)
                self.assertEqual(result["verified_record_count"], 1)
                if stage == "tjzyefy":
                    self.assertEqual(rows[0]["facts"]["registration_deadline"], "2026-10-09T16:00:00+08:00")
                if stage == "tjzyefy_intent":
                    self.assertIsNone(rows[0]["facts"]["registration_deadline"])
                self.assertEqual(self.cache.writes[-1][2], {})
                self.cache.writes.clear()
        self.assert_public_unchanged()

    def test_real_discovery_and_id_functions_are_called(self):
        adapter = runtime.tjzyefy_discovery
        with patch.object(adapter, "parse_tjzyefy_index_html", wraps=adapter.parse_tjzyefy_index_html) as discover, \
             patch.object(adapter, "stable_opportunity_id", wraps=adapter.stable_opportunity_id) as stable:
            self.prepare()
        discover.assert_called_once()
        stable.assert_called()

    def test_three_stores_and_intent_naming_are_independent(self):
        for stage in runtime.OFFICIAL_SOURCE_STAGE_IDS:
            self.commit(self.prepare(stage))
        keys = list(runtime.PRESERVED_SOURCE_RECORDS_KEYS.values())
        self.assertEqual(len(set(keys)), 3)
        self.assertTrue(all(len(self.cache.get(key)) == 1 for key in keys))
        intent = self.cache.get(runtime.PRESERVED_SOURCE_RECORDS_KEYS["tjzyefy-intent"])[0]
        self.assertTrue(intent["opportunity_id"].startswith("tjzyefy_intent_"))
        self.assertTrue(intent["source"]["source_id"].startswith("tjzyefy-intent:"))

    def test_existing_four_intents_are_retained_without_retiming(self):
        rows = json.loads((DATA / "tianjin_live_tjzyefy_intent_records.json").read_text())
        before = deepcopy(rows)
        key = runtime.PRESERVED_SOURCE_RECORDS_KEYS["tjzyefy-intent"]
        self.cache.values[key] = rows
        self.commit(self.prepare("tjzyefy_intent"))
        merged = {row["opportunity_id"]: row for row in self.cache.get(key)}
        self.assertEqual(len(merged), 5)
        for old in before:
            self.assertEqual(merged[old["opportunity_id"]], old)

    def test_non_medical_research_can_be_filtered_at_discovery(self):
        index, pages, url = synthetic_case("tjzyefy", title="天津中医药大学第二附属医院数据安全服务项目调研公告")
        reader = Mock(side_effect=AssertionError("DETAIL_NOT_NEEDED"))
        prepared = self.prepare(case=(index, pages, url), reader=reader)
        result = self.commit(prepared)
        reader.assert_not_called()
        self.assertFalse(result["canonical_changed"])
        self.assertEqual(self.cache.writes, [])

    def test_non_medical_fch_detail_is_a_nonfact_not_source_failure(self):
        title = "天津市中心妇产科医院报告厅提升改造项目市场调研邀请公告"
        index, pages, url = synthetic_case("tjzxfc", title=title)
        detail_url = next(iter(pages))
        pages[detail_url] = (
            f"<h1>{title}</h1><p>时间：2026-09-28 来源：信息科</p><p>天津市中心妇产科医院拟对报告厅音视频、显示屏、扩声和网络系统进行提升改造，现开展市场调研。</p>"
            "<p>截止时间：2026年10月9日17:00。</p>"
        )
        result = self.commit(self.prepare("tjzxfc", case=(index, pages, url)))
        self.assertEqual(result["verified_nonfact_count"], 1)
        self.assertFalse(result["canonical_changed"])
        self.assertEqual(self.cache.writes, [])

    def test_unknown_parse_error_is_not_suppressed(self):
        with patch.object(runtime.tjzyefy_market_research, "parse_tjzyefy_market_research", side_effect=runtime.tjzyefy_market_research.TjzyefyParseError("UNKNOWN_FAILURE")):
            with self.assertRaisesRegex(ValueError, "UNKNOWN_FAILURE"):
                self.prepare()
        self.assertEqual(self.cache.writes, [])
        self.assert_public_unchanged()

    def test_later_detail_failure_never_commits_the_first_record(self):
        one = synthetic_case("tjzyefy")
        two = synthetic_case("tjzyefy", number="030199114")
        pages = {**one[1], **two[1]}
        pages[next(iter(one[1]))] = "<html>unverified wrong page</html>"
        with self.assertRaises(ValueError):
            self.prepare(case=(one[0] + two[0], pages, one[2]))
        self.assertEqual(self.cache.writes, [])
        self.assert_public_unchanged()

    def test_missing_canonical_does_not_bootstrap_or_make_empty_array(self):
        for stage, source in runtime.OFFICIAL_SOURCE_STAGE_IDS.items():
            key = runtime.PRESERVED_SOURCE_RECORDS_KEYS[source]
            self.cache.values.pop(key)
            reader = Mock(side_effect=AssertionError("MUST_NOT_READ_DETAIL"))
            with self.subTest(stage=stage), self.assertRaisesRegex(runtime.CollectorPrecondition, "HISTORY_UNAVAILABLE"):
                self.prepare(stage, reader=reader)
            reader.assert_not_called()
            self.assertNotIn(key, self.cache.values)
            self.cache.values[key] = []

    def test_canonical_wrong_source_identity_market_and_duplicate_are_rejected(self):
        record = json.loads(self.prepare().records_json)[0]
        key = runtime.PRESERVED_SOURCE_RECORDS_KEYS["tjzyefy"]
        wrong_source = deepcopy(record)
        wrong_source["source"]["source_id"] = "tjzxfc:" + record["opportunity_id"]
        wrong_id = deepcopy(record)
        wrong_id["opportunity_id"] = "wrong"
        wrong_market = deepcopy(record)
        wrong_market["facts"]["market_code"] = "BJ"
        for rows in ([wrong_source], [wrong_id], [wrong_market], [record, record], [{}]):
            self.cache.values[key] = rows
            with self.subTest(rows=rows), self.assertRaisesRegex(runtime.CollectorPrecondition, "HISTORY_INVALID"):
                self.prepare()
        self.assertEqual(self.cache.writes, [])

    def test_window_is_bound_to_page_source_time_and_entire_lookback(self):
        overrides = (
            {"stage": "tjzxfc"}, {"index_url": "https://example.com/"},
            {"html_sha256": "bad"}, {"start_date": AS_OF.date()},
            {"end_date": AS_OF.date() - timedelta(days=1)},
            {"observed_at": AS_OF - timedelta(seconds=1)},
            {"observed_at": OBSERVED + timedelta(seconds=1)},
            {"observed_at": OBSERVED.replace(tzinfo=None)},
        )
        for override in overrides:
            with self.subTest(override=override), self.assertRaisesRegex(runtime.CollectorPrecondition, "WINDOW_UNVERIFIED"):
                self.prepare(window_override=override)
        index, pages, _ = synthetic_case("tjzyefy")
        with self.assertRaisesRegex(runtime.CollectorPrecondition, "WINDOW_UNVERIFIED"):
            runtime._prepare_official_source_refresh(self.cache, self.state, "tjzyefy", index_html=index, window=None, read_detail=Mock())
        self.assertEqual(self.cache.writes, [])

    def test_four_candidates_block_before_detail_without_silent_truncation(self):
        cases = [synthetic_case("tjzyefy", number=str(30199113 + i)) for i in range(4)]
        reader = Mock(side_effect=AssertionError("LIMIT_MUST_BLOCK_FIRST"))
        with self.assertRaisesRegex(runtime.CollectorStageBlocked, "CANDIDATE_LIMIT"):
            self.prepare(case=("".join(v[0] for v in cases), {}, cases[0][2]), reader=reader)
        reader.assert_not_called()
        self.assertEqual(self.cache.writes, [])

    def test_reader_overrun_is_rejected_after_return_without_any_commit(self):
        now = [0.0]
        case = synthetic_case("tjzyefy")
        def reader(url, deadline):
            self.assertEqual(deadline, 240)
            now[0] = 241
            return case[1][url]
        with patch.object(runtime.time, "monotonic", side_effect=lambda: now[0]):
            with self.assertRaisesRegex(runtime.CollectorStageBlocked, "BUDGET_EXHAUSTED"):
                self.prepare(case=case, reader=reader)
        self.assertEqual(self.cache.writes, [])

    def test_expired_preparation_cannot_commit(self):
        prepared = self.prepare()
        with patch.object(runtime.time, "monotonic", return_value=prepared.deadline):
            with self.assertRaisesRegex(runtime.CollectorStageBlocked, "BUDGET_EXHAUSTED"):
                self.commit(prepared)
        self.assertEqual(self.cache.writes, [])

    def test_old_morning_preparation_cannot_overwrite_noon_state(self):
        prepared = self.prepare()
        noon = AS_OF + timedelta(hours=4)
        nid, _ = scheduled_cycle(noon, "noon")
        marker = {"cycle_id": nid, "cycle_as_of": noon.isoformat()}
        self.cache.values[ACTIVE_CYCLE_KEY] = marker
        self.cache.values[META_KEY] = deepcopy(marker)
        with self.assertRaisesRegex(runtime.CollectorPrecondition, "SUPERSEDED"):
            self.commit(prepared)
        self.assertEqual(self.cache.values[ACTIVE_CYCLE_KEY], marker)
        self.assertEqual(self.cache.values[META_KEY], marker)
        self.assertEqual(self.cache.writes, [])

    def test_ended_cycle_cannot_commit_even_when_active_marker_is_retained(self):
        prepared = self.prepare()
        for publish in ({"status": "COMPLETED"}, {"status": "BLOCKED", "terminal": True}, {"status": "FAILED", "terminal": True}):
            self.cache.values[META_KEY] = {**self.state, "stages": {"publish": publish}}
            with self.subTest(publish=publish), self.assertRaisesRegex(runtime.CollectorPrecondition, "CYCLE_ENDED"):
                self.commit(prepared)
        self.assertEqual(self.cache.writes, [])

    def test_cycle_change_during_base_read_is_checked_again_before_write(self):
        prepared = self.prepare()
        key = runtime.PRESERVED_SOURCE_RECORDS_KEYS["tjzyefy"]
        get = self.cache.get
        noon = AS_OF + timedelta(hours=4)
        nid, _ = scheduled_cycle(noon, "noon")
        marker = {"cycle_id": nid, "cycle_as_of": noon.isoformat()}
        def switch_cycle(requested):
            value = get(requested)
            if requested == key:
                self.cache.values[ACTIVE_CYCLE_KEY] = deepcopy(marker)
                self.cache.values[META_KEY] = deepcopy(marker)
            return value
        with patch.object(self.cache, "get", side_effect=switch_cycle):
            with self.assertRaisesRegex(runtime.CollectorPrecondition, "SUPERSEDED"):
                self.commit(prepared)
        self.assertEqual(self.cache.writes, [])
        self.assertEqual(self.cache.get(key), [])
        self.assertEqual(self.cache.get(ACTIVE_CYCLE_KEY), marker)

    def test_existing_publish_path_keeps_history_only_and_partial_semantics(self):
        prepared = self.prepare()
        self.commit(prepared)
        self.cache.values.update({
            runtime.CCGP_RECORDS_KEY: [], runtime.CCGP_EVENTS_KEY: [],
            runtime.TJMUGH_RECORDS_KEY: [], runtime.TJNOTHOP_RECORDS_KEY: [],
            runtime.TEDA_RECORDS_KEY: [], runtime.TJFCH_RECORDS_KEY: [],
            **{runtime._regional_records_key(code): [] for code in runtime.REGIONAL_STAGE_MARKET_CODES.values()},
            runtime.PUBLISHED_RUNTIME_SNAPSHOT_KEY: {
                "snapshot_as_of": (AS_OF - timedelta(days=1)).isoformat(),
                "opportunity_pool": [], "opportunity_pool_count": 0,
                "collection_coverage": {"complete": False, "last_complete_as_of": None},
            },
        })
        state = {**self.state, "stages": {
            stage: {"status": "COMPLETED", "result": {"fallback_required": False}}
            for stage in runtime.STAGE_ORDER if stage != "publish"
        }}
        with patch.object(runtime, "_persist_verified_snapshot_durably", return_value={
            "snapshot_as_of": AS_OF.isoformat(), "opportunity_pool_count": 1,
        }) as durable:
            result = runtime._run_publish(self.cache, state)
        self.assertEqual(result["opportunity_pool_count"], 1)
        snapshot = durable.call_args.args[0]
        row = snapshot["opportunity_pool"][0]
        self.assertEqual(row["opportunity_id"], json.loads(prepared.records_json)[0]["opportunity_id"])
        self.assertEqual(row["facts"]["market_code"], "TJ")
        self.assertIs(snapshot["collection_coverage"]["complete"], False)
        self.assertIsNone(snapshot["collection_coverage"]["last_complete_as_of"])
        self.assertEqual(snapshot["collection_coverage"]["history_only_source_ids"], list(runtime.PRESERVED_SOURCE_RECORDS_KEYS))

    def test_historical_positive_is_not_an_open_opportunity_after_deadline(self):
        records = json.loads(self.prepare().records_json)
        current = datetime(2026, 10, 17, 0, 40, tzinfo=timezone.utc)
        snapshot = runtime._build_scheduled_public_snapshot(records, [], current, [])
        self.assertEqual(snapshot["opportunity_pool_count"], 0)
        self.assertEqual(records[0]["facts"]["registration_deadline"], "2026-10-09T16:00:00+08:00")

    def test_same_preparation_commit_is_idempotent_and_uses_no_ttl(self):
        prepared = self.prepare()
        first = self.commit(prepared)
        second = self.commit(prepared)
        self.assertEqual(first, second)
        self.assertEqual(len(self.cache.writes), 1)
        self.assertEqual(self.cache.writes[0][2], {})

    def test_changed_base_is_not_overwritten(self):
        prepared = self.prepare()
        other = self.prepare(case=synthetic_case("tjzyefy", number="030199119"))
        key = runtime.PRESERVED_SOURCE_RECORDS_KEYS["tjzyefy"]
        newer = json.loads(other.records_json)
        self.cache.values[key] = newer
        with self.assertRaisesRegex(runtime.CollectorPrecondition, "BASE_CHANGED"):
            self.commit(prepared)
        self.assertEqual(self.cache.get(key), newer)
        self.assertEqual(self.cache.writes, [])

    def test_candidate_is_revalidated_before_commit(self):
        prepared = replace(self.prepare(), records_json='[{"bad":"record"}]')
        with self.assertRaisesRegex(runtime.CollectorPrecondition, "HISTORY_INVALID"):
            self.commit(prepared)
        self.assertEqual(self.cache.writes, [])

    def test_unchanged_scan_does_not_advance_fact_observed_at(self):
        key = runtime.PRESERVED_SOURCE_RECORDS_KEYS["tjzyefy"]
        rows = json.loads(self.prepare().records_json)
        rows[0]["source"]["observed_at"] = AS_OF.isoformat()
        self.cache.values[key] = deepcopy(rows)
        result = self.commit(self.prepare())
        self.assertFalse(result["canonical_changed"])
        self.assertEqual(result["source_observed_at"], OBSERVED.isoformat())
        self.assertEqual(self.cache.get(key), rows)
        self.assertEqual(self.cache.writes, [])

    def test_cache_write_and_readback_failures_do_not_touch_public_data(self):
        prepared = self.prepare()
        with patch.object(self.cache, "set", side_effect=RuntimeError("WRITE_FAILED")):
            with self.assertRaisesRegex(RuntimeError, "WRITE_FAILED"):
                self.commit(prepared)
        key = runtime.PRESERVED_SOURCE_RECORDS_KEYS["tjzyefy"]
        get = self.cache.get
        def bad_readback(requested):
            if requested == key and self.cache.writes:
                return None
            return get(requested)
        with patch.object(self.cache, "get", side_effect=bad_readback):
            with self.assertRaisesRegex(runtime.CollectorStageBlocked, "READBACK_FAILED"):
                self.commit(prepared)
        self.assert_public_unchanged()

    def test_production_dispatch_and_incremental_sources_remain_inactive(self):
        from collector_incremental_scheduler import SCHEDULED_INCREMENTAL_SOURCES
        self.assertEqual(len(runtime.STAGE_ORDER), 22)
        for stage in runtime.OFFICIAL_SOURCE_STAGE_IDS:
            self.assertNotIn(stage, runtime.STAGE_ORDER)
            self.assertNotIn(stage, SCHEDULED_INCREMENTAL_SOURCES)
        self.assertIs(queue.STAGE_ORDER, runtime.STAGE_ORDER)
        config = json.loads((DATA.parents[1] / "vercel.json").read_text())
        self.assertIs(config["git"]["deploymentEnabled"]["fix/twice-daily-source-parity-20261017"], False)


if __name__ == "__main__":
    unittest.main()
