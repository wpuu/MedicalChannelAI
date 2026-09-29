from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_ccgp_awards as sync  # noqa: E402
from medical_channel_pipeline.ccgp_discovery import DiscoveryCandidate  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLAN_PATH = ROOT / "data" / "tianjin_award_query_plan.json"
AS_OF = datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc)

MULTI_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27412443.htm"
SINGLE_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27412423.htm"
WORKS_URL = "https://www.ccgp.gov.cn/cggg/dfgg/cjgg/202609/t20260928_27411167.htm"
CORRECTION_URL = "https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260928_00000001.htm"
BROKEN_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_00000002.htm"

DETAILS = {
    MULTI_URL: "ccgp_award_tianjin_multi_package.html",
    SINGLE_URL: "ccgp_award_tianjin_single_package.html",
    WORKS_URL: "ccgp_deal_tianjin_works_only.html",
}


def _candidate(url: str, title: str, published_at: str = "2026-09-28", notice_type: str = "中标公告") -> DiscoveryCandidate:
    return DiscoveryCandidate(
        title=title,
        detail_url=url,
        published_at=published_at,
        buyer_name=None,
        region="天津",
        notice_type=notice_type,
        search_keyword="医院",
    )


def _fetch_detail(url: str) -> str:
    if url == BROKEN_URL:
        return "<html><head><title>某医院设备采购项目中标公告</title></head><body>详见附件</body></html>"
    return (FIXTURES / DETAILS[url]).read_text(encoding="utf-8")


class AwardPlanTests(unittest.TestCase):
    def test_repo_plan_loads_and_is_locked_to_tianjin_result_notices(self) -> None:
        plan = sync.load_plan(PLAN_PATH)
        self.assertEqual(plan["region"], "天津")
        self.assertEqual(plan["market_code"], "TJ")
        self.assertEqual(plan["notice_types"], ["中标公告", "成交公告"])
        self.assertEqual(plan["keywords"][0], "医院")
        self.assertGreaterEqual(plan["delay_seconds"], 3)
        self.assertLessEqual(plan["max_details"], 30)

    def test_plan_rejects_non_result_notice_types_and_region_mismatch(self) -> None:
        base = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            bad = dict(base, notice_types=["公开招标"])
            path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "NOTICE_TYPE_UNSUPPORTED"):
                sync.load_plan(path)
            bad = dict(base, region="北京")
            path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "REGION_MARKET_MISMATCH"):
                sync.load_plan(path)
            bad = dict(base, delay_seconds=1)
            path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DELAY_TOO_LOW"):
                sync.load_plan(path)

    def test_result_candidate_filter_uses_path_then_title(self) -> None:
        self.assertTrue(sync.is_award_result_candidate(_candidate(MULTI_URL, "彩超采购项目中标公告")))
        self.assertTrue(sync.is_award_result_candidate(_candidate(WORKS_URL, "改造项目成交公告")))
        self.assertTrue(sync.is_award_result_candidate(_candidate("https://www.ccgp.gov.cn/cggg/dfgg/qtgg/202609/t1.htm", "某项目中标（成交）结果公告")))
        self.assertFalse(sync.is_award_result_candidate(_candidate(CORRECTION_URL, "彩超采购项目更正公告")))
        self.assertFalse(sync.is_award_result_candidate(_candidate("https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t2.htm", "中标公告更正公告")))
        self.assertFalse(sync.is_award_result_candidate(_candidate("https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t3.htm", "设备采购项目公开招标公告")))

    def test_unseen_result_notices_are_selected_before_seen_ones(self) -> None:
        seen = {"source": {"url": MULTI_URL}, "facts": {}}
        discovered = [
            ("中标公告", _candidate(MULTI_URL, "seen newest", published_at="2026-09-29")),
            ("中标公告", _candidate(SINGLE_URL, "unseen older", published_at="2026-09-27")),
            ("成交公告", _candidate(WORKS_URL, "unseen newest", published_at="2026-09-28")),
        ]
        selected = sync.select_award_candidates(discovered, [seen], 2)
        self.assertEqual([item[1].detail_url for item in selected], [WORKS_URL, SINGLE_URL])


class AwardSyncRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = sync.load_plan(PLAN_PATH)
        self.sleeps: list[float] = []
        self.search_urls: list[str] = []
        self.candidates = [
            _candidate(MULTI_URL, "天津市第三中心医院彩色多普勒超声诊断仪采购项目中标公告"),
            _candidate(SINGLE_URL, "天津市第五中心医院数字减影血管造影机采购项目中标公告"),
            _candidate(WORKS_URL, "天津市第一中心医院CT室、DR室改造项目成交公告", notice_type="成交公告"),
            _candidate(CORRECTION_URL, "某项目更正公告"),
            _candidate(BROKEN_URL, "某医院设备采购项目中标公告"),
        ]
        self._orig_parse = sync.parse_search_html
        sync.parse_search_html = lambda html, keyword: list(self.candidates) if keyword == "医院" else []

    def tearDown(self) -> None:
        sync.parse_search_html = self._orig_parse

    def _fetch_search(self, url: str) -> str:
        self.search_urls.append(url)
        return url

    def test_run_merges_in_scope_awards_reports_scope_exclusions_and_parse_failures(self) -> None:
        pool = [{"facts": {"project_number": "XCSD-2026-A-589"}}, {"facts": {"project_number": "OTHER"}}]
        awards, report = sync.run_award_sync(
            plan=self.plan,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=pool,
            fetch_search=self._fetch_search,
            fetch_detail=_fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual(len(self.search_urls), 10)
        self.assertTrue(all("bidType=7" in url or "bidType=11" in url for url in self.search_urls))
        self.assertTrue(all("displayZone=" in url and "zoneId=12" in url for url in self.search_urls))
        self.assertEqual(sorted(record["facts"]["project_number"] for record in awards), ["XCSD-2026-A-535", "XCSD-2026-A-589"])
        self.assertTrue(all(record["award_id"].startswith("ccgpaward_") for record in awards))
        self.assertTrue(all(record["facts"]["market_code"] == "TJ" for record in awards))
        self.assertEqual(report["start_date"], "2026-09-22")
        self.assertEqual(report["end_date"], "2026-09-29")
        self.assertEqual(report["unique_discovered_result_count"], 4)  # correction notice filtered out
        self.assertEqual(report["selected_detail_count"], 4)
        self.assertEqual(report["new_award_record_count"], 2)
        self.assertEqual(report["out_of_scope_count"], 1)
        self.assertEqual(report["out_of_scope"][0]["project_number"], "0615-2641031970921")
        self.assertEqual(report["failure_count"], 1)
        self.assertEqual(report["failures"][0]["stage"], "award_detail")
        self.assertEqual(report["failures"][0]["url"], BROKEN_URL)
        self.assertEqual(report["matched_pool_project_numbers"], ["XCSD-2026-A-589"])
        self.assertTrue(report["publish_allowed"])
        self.assertTrue(all(delay >= 3 for delay in self.sleeps))

    def test_all_discovery_failures_block_publish_but_preserve_existing_awards(self) -> None:
        def failing_search(url: str) -> str:
            raise RuntimeError("CCGP_RATE_LIMITED")

        existing, _ = sync.run_award_sync(
            plan=self.plan,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=[],
            fetch_search=self._fetch_search,
            fetch_detail=_fetch_detail,
            sleep=self.sleeps.append,
        )
        awards, report = sync.run_award_sync(
            plan=self.plan,
            as_of=AS_OF,
            existing_awards=existing,
            pool_records=[],
            fetch_search=failing_search,
            fetch_detail=_fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual(len(awards), len(existing))
        self.assertEqual(report["discovery_success_count"], 0)
        self.assertFalse(report["publish_allowed"])
        self.assertEqual(report["publish_gate_reason"], "ALL_AWARD_DISCOVERY_QUERIES_FAILED")
        self.assertEqual({item["stage"] for item in report["failures"]}, {"award_discovery_search"})

    def test_time_budget_stops_new_requests_but_keeps_verified_results(self) -> None:
        ticks = iter([0.0] + [1.0] * 4 + [100.0] * 200)  # first search fits, everything after is over budget

        awards, report = sync.run_award_sync(
            plan=self.plan,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=[],
            time_budget_seconds=50,
            fetch_search=self._fetch_search,
            fetch_detail=_fetch_detail,
            sleep=self.sleeps.append,
            clock=lambda: next(ticks),
        )
        self.assertTrue(report["time_budget_exhausted"])
        self.assertGreater(report["skipped_count"], 0)
        self.assertLess(len(self.search_urls), 10)
        self.assertEqual(report["discovery_success_count"], len(self.search_urls))
        self.assertTrue(all(item["reason"] == "TIME_BUDGET_EXHAUSTED" for item in report["skipped"]))
        # Nothing was fetched after the budget ran out, so no awards were verified and the gate stays open
        # only because at least one discovery query succeeded.
        self.assertEqual(awards, [])
        self.assertTrue(report["publish_allowed"])

    def test_award_stage_runtime_passes_a_time_budget(self) -> None:
        runtime = (ROOT.parent / "collector_runtime.py").read_text(encoding="utf-8")
        self.assertIn("AWARD_STAGE_TIME_BUDGET_SECONDS = 200.0", runtime)
        self.assertIn("time_budget_seconds=AWARD_STAGE_TIME_BUDGET_SECONDS,", runtime)


if __name__ == "__main__":
    unittest.main()
