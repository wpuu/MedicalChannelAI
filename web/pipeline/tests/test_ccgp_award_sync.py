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

LN_FAILED_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260929_27413417.htm"
LN_AWARDED_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27407769.htm"

DETAILS = {
    MULTI_URL: "ccgp_award_tianjin_multi_package.html",
    SINGLE_URL: "ccgp_award_tianjin_single_package.html",
    WORKS_URL: "ccgp_deal_tianjin_works_only.html",
    LN_FAILED_URL: "ccgp_award_liaoning_all_packages_failed.html",
    LN_AWARDED_URL: "ccgp_award_liaoning_single_item_awarded.html",
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


class AwardTitleScreenTests(unittest.TestCase):
    def test_explicit_exclusion_titles_never_consume_detail_budget(self) -> None:
        discovered = [
            ("中标公告", _candidate(MULTI_URL, "大连医科大学附属第一医院预包装食品类项目结果公告", published_at="2026-09-29")),
            ("成交公告", _candidate(WORKS_URL, "某医院保洁服务项目成交公告", published_at="2026-09-29", notice_type="成交公告")),
            ("中标公告", _candidate(SINGLE_URL, "某医院医用织物洗涤设备采购项目中标公告", published_at="2026-09-29")),
            ("中标公告", _candidate(BROKEN_URL, "盛京医院大连医院医疗设备购置项目-除颤仪中标结果公告", published_at="2026-09-27")),
            ("中标公告", _candidate(LN_FAILED_URL, "岫岩满族自治县中心人民医院医共体内涵建设项目-设备采购项目结果公告", published_at="2026-09-27")),
        ]
        kept, excluded = sync.screen_award_titles(discovered)
        self.assertEqual([item[1].detail_url for item in kept], [BROKEN_URL, LN_FAILED_URL])
        self.assertEqual([item["url"] for item in excluded], [MULTI_URL, WORKS_URL, SINGLE_URL])
        self.assertTrue(all(item["reason"] == sync.TITLE_EXCLUSION_REASON for item in excluded))
        # The budget is spent on the survivors only, unseen-first as before.
        selected = sync.select_award_candidates(kept, [], 1)
        self.assertEqual([item[1].detail_url for item in selected], [LN_FAILED_URL])


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

    def test_rows_whose_geography_does_not_prove_the_market_are_dropped(self) -> None:
        # zoneId scoping is not trusted: a 河北 row (or one without a 地域 field)
        # returned by the 天津-scoped search never becomes a Tianjin award.
        self.candidates = [
            _candidate(MULTI_URL, "天津市第三中心医院彩色多普勒超声诊断仪采购项目中标公告"),
            DiscoveryCandidate(
                title="河北某医院设备采购项目中标公告",
                detail_url=SINGLE_URL,
                published_at="2026-09-28",
                buyer_name=None,
                region="河北省石家庄市",
                notice_type="中标公告",
                search_keyword="医院",
            ),
            DiscoveryCandidate(
                title="未知地域医院设备采购项目中标公告",
                detail_url=BROKEN_URL,
                published_at="2026-09-28",
                buyer_name=None,
                region=None,
                notice_type="中标公告",
                search_keyword="医院",
            ),
        ]
        awards, report = sync.run_award_sync(
            plan=self.plan,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=[],
            fetch_search=self._fetch_search,
            fetch_detail=_fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual([record["facts"]["project_number"] for record in awards], ["XCSD-2026-A-535"])
        self.assertEqual(report["unique_discovered_result_count"], 1)
        self.assertEqual(report["region_mismatch_count"], 4)  # 2 rows x 2 notice types
        self.assertEqual(
            sorted({item["candidate_region"] or "" for item in report["region_mismatches"]}),
            ["", "河北省石家庄市"],
        )
        self.assertTrue(all(item["expected_market_code"] == "TJ" for item in report["region_mismatches"]))
        self.assertTrue(report["policy"]["row_geography_must_prove_market"])

    def test_plan_can_be_retargeted_at_another_market(self) -> None:
        self.assertEqual(sync.candidate_market_code("北京市"), "BJ")
        self.assertEqual(sync.candidate_market_code("黑龙江省哈尔滨市"), "HL")
        self.assertEqual(sync.candidate_market_code("天津"), "TJ")
        self.assertIsNone(sync.candidate_market_code("河南省"))
        self.assertIsNone(sync.candidate_market_code(None))
        plan = sync.load_plan(PLAN_PATH, market_code="he")
        self.assertEqual((plan["market_code"], plan["region"]), ("HE", "河北"))
        self.assertEqual(plan["keywords"], self.plan["keywords"])
        with self.assertRaisesRegex(ValueError, "AWARD_QUERY_PLAN_MARKET_CODE_INVALID:XX"):
            sync.load_plan(PLAN_PATH, market_code="XX")
        # Retargeted runs search the other zone and stamp the other market.
        self.candidates = [
            DiscoveryCandidate(
                title="河北某医院设备采购项目中标公告",
                detail_url=SINGLE_URL,
                published_at="2026-09-28",
                buyer_name=None,
                region="河北省",
                notice_type="中标公告",
                search_keyword="医院",
            ),
        ]
        awards, report = sync.run_award_sync(
            plan=plan,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=[],
            fetch_search=self._fetch_search,
            fetch_detail=_fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertTrue(all("zoneId=13" in url for url in self.search_urls))
        self.assertEqual([record["facts"]["market_code"] for record in awards], ["HE"])
        self.assertEqual(report["market_code"], "HE")

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

    def test_excluded_titles_are_reported_and_never_fetched(self) -> None:
        fetched: list[str] = []

        def fetch_detail(url: str) -> str:
            fetched.append(url)
            return _fetch_detail(url)

        self.candidates = [
            _candidate(MULTI_URL, "天津市第三中心医院彩色多普勒超声诊断仪采购项目中标公告", published_at="2026-09-27"),
            _candidate(SINGLE_URL, "天津市某医院预包装食品类项目中标公告", published_at="2026-09-29"),
            _candidate(WORKS_URL, "天津市某医院物业服务项目成交公告", published_at="2026-09-29", notice_type="成交公告"),
        ]
        plan = dict(self.plan, max_details=1)
        awards, report = sync.run_award_sync(
            plan=plan,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=[],
            fetch_search=self._fetch_search,
            fetch_detail=fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual(fetched, [MULTI_URL])
        self.assertEqual(report["title_excluded_count"], 2)
        self.assertEqual({item["url"] for item in report["title_excluded"]}, {SINGLE_URL, WORKS_URL})
        self.assertEqual(report["selected_detail_count"], 1)
        self.assertEqual([record["facts"]["project_number"] for record in awards], ["XCSD-2026-A-535"])
        self.assertTrue(report["policy"]["candidate_prefilter_only_rejects_explicit_exclusions"])

    def test_pool_matched_failed_result_bypasses_sparse_scope_text(self) -> None:
        plan = sync.load_plan(PLAN_PATH, market_code="LN")
        # Without a pool match the 废标 notice (no items, generic project name) stays out of scope.
        awards, report = sync.run_award_sync(
            plan=plan,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=[{"facts": {"project_number": "OTHER-1"}}],
            detail_urls=[LN_FAILED_URL],
            fetch_search=self._fetch_search,
            fetch_detail=_fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual(awards, [])
        self.assertEqual(report["out_of_scope_count"], 1)
        self.assertEqual(report["scope_bypassed_for_pool_match_count"], 0)
        # The same notice retires a pool project that already proved its scope with full facts.
        awards, report = sync.run_award_sync(
            plan=plan,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=[{"facts": {"project_number": "ＪＨ26-210323-00239"}}],
            detail_urls=[LN_FAILED_URL],
            fetch_search=self._fetch_search,
            fetch_detail=_fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual([record["facts"]["award_status"] for record in awards], ["ALL_PACKAGES_FAILED"])
        self.assertEqual(awards[0]["facts"]["market_code"], "LN")
        self.assertEqual(report["out_of_scope_count"], 0)
        self.assertEqual(report["scope_bypassed_for_pool_match_count"], 1)
        self.assertEqual(report["scope_bypassed_for_pool_match"][0]["reason"], sync.POOL_MATCH_SCOPE_REASON)
        self.assertEqual(report["matched_pool_project_numbers"], ["JH26-210323-00239"])
        self.assertTrue(report["policy"]["pool_matched_results_bypass_sparse_scope_text"])

    def test_liaoning_awarded_template_yields_priced_item(self) -> None:
        plan = sync.load_plan(PLAN_PATH, market_code="LN")
        awards, report = sync.run_award_sync(
            plan=plan,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=[],
            detail_urls=[LN_AWARDED_URL],
            fetch_search=self._fetch_search,
            fetch_detail=_fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual(report["failure_count"], 0)
        facts = awards[0]["facts"]
        self.assertEqual(facts["project_number"], "LNYCDL20260907")
        self.assertEqual(facts["buyer_name"], "大连金普新区卫生健康局")
        self.assertEqual(facts["award_status"], "AWARDED")
        self.assertEqual((facts["total_amount_cny"], facts["amount_basis"]), (250000, "SUMMARY_TOTAL"))
        self.assertEqual(facts["packages"][0]["supplier_name"], "大连锦皓辰商贸有限公司")
        item = facts["items"][0]
        self.assertEqual((item["name"], item["brand"], item["model"], item["quantity"], item["unit_price_cny"]), ("除颤仪", "科曼", "S1A", "10", 25000))

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
