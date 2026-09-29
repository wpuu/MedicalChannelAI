from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PIPELINE_ROOT / "scripts"
for path in (PIPELINE_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import sync_ccgp_awards as tj_sync  # noqa: E402
import sync_regional_awards as regional  # noqa: E402
from medical_channel_pipeline.ccgp_discovery import DiscoveryCandidate  # noqa: E402

FIXTURES = PIPELINE_ROOT / "tests" / "fixtures"
AS_OF = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
BJ_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27412423.htm"
HE_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27412443.htm"
DETAILS = {
    BJ_URL: "ccgp_award_tianjin_single_package.html",
    HE_URL: "ccgp_award_tianjin_multi_package.html",
}


def _candidate(url: str, title: str, region: str) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        title=title,
        detail_url=url,
        published_at="2026-09-28",
        buyer_name=None,
        region=region,
        notice_type="中标公告",
        search_keyword="医院",
    )


class RegionalAwardSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.search_urls: list[str] = []
        self.sleeps: list[float] = []
        # The same rows come back for every scoped search; only the geography
        # field decides which market may keep them.
        self.rows = [
            _candidate(BJ_URL, "北京某医院设备采购项目中标公告", "北京市"),
            _candidate(HE_URL, "河北某医院设备采购项目中标公告", "河北省"),
            _candidate("https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_00000001.htm", "河南某医院中标公告", "河南省"),
        ]
        self._orig_parse = tj_sync.parse_search_html
        tj_sync.parse_search_html = lambda html, keyword: list(self.rows) if keyword == "医院" else []

    def tearDown(self) -> None:
        tj_sync.parse_search_html = self._orig_parse

    def _fetch_search(self, url: str) -> str:
        self.search_urls.append(url)
        return url

    @staticmethod
    def _fetch_detail(url: str) -> str:
        return (FIXTURES / DETAILS[url]).read_text(encoding="utf-8")

    def test_plan_lists_the_five_non_tianjin_markets_with_a_per_market_budget(self) -> None:
        codes, budget = regional.load_market_codes(regional.DEFAULT_PLAN)
        self.assertEqual(codes, ["BJ", "HE", "LN", "JL", "HL"])
        self.assertIsNotNone(budget)
        self.assertGreaterEqual(budget, 30)
        with self.assertRaisesRegex(ValueError, "REGIONAL_AWARD_MARKET_NOT_IN_PLAN"):
            regional.run_regional_award_sync(
                plan_path=regional.DEFAULT_PLAN,
                as_of=AS_OF,
                existing_awards=[],
                pool_records=[],
                market_codes=["TJ"],
                fetch_search=self._fetch_search,
                fetch_detail=self._fetch_detail,
                sleep=self.sleeps.append,
            )

    def test_each_market_keeps_only_rows_its_geography_proves(self) -> None:
        pool = [
            {"facts": {"project_number": "XCSD-2026-A-589", "market_code": "BJ"}},
            {"facts": {"project_number": "XCSD-2026-A-535", "market_code": "JL"}},
        ]
        awards, report = regional.run_regional_award_sync(
            plan_path=regional.DEFAULT_PLAN,
            as_of=AS_OF,
            existing_awards=[],
            pool_records=pool,
            market_codes=["BJ", "HE", "JL"],
            fetch_search=self._fetch_search,
            fetch_detail=self._fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual(len(self.search_urls), 30)  # 3 markets x 5 keywords x 2 notice types
        self.assertEqual(sum("zoneId=11" in url for url in self.search_urls), 10)
        self.assertEqual(sum("zoneId=13" in url for url in self.search_urls), 10)
        self.assertEqual(sum("zoneId=22" in url for url in self.search_urls), 10)
        by_market = {record["facts"]["market_code"]: record["facts"]["project_number"] for record in awards}
        self.assertEqual(by_market, {"BJ": "XCSD-2026-A-589", "HE": "XCSD-2026-A-535"})
        self.assertEqual(report["market_codes"], ["BJ", "HE", "JL"])
        self.assertEqual(report["new_award_record_count"], 2)
        self.assertEqual(report["merged_award_record_count_by_market"], {"BJ": 1, "HE": 1})
        # 河南 row never proves any market; BJ/HE rows are mismatches for each other and for JL.
        self.assertEqual(report["markets"]["BJ"]["region_mismatch_count"], 4)
        self.assertEqual(report["markets"]["HE"]["region_mismatch_count"], 4)
        self.assertEqual(report["markets"]["JL"]["region_mismatch_count"], 6)
        self.assertEqual(report["markets"]["JL"]["new_award_record_count"], 0)
        # Pool matches are scoped to the market's own records.
        self.assertEqual(report["markets"]["BJ"]["matched_pool_project_numbers"], ["XCSD-2026-A-589"])
        self.assertEqual(report["markets"]["HE"]["matched_pool_project_numbers"], [])
        self.assertTrue(report["publish_allowed"])
        self.assertEqual(report["markets_publish_allowed"], {"BJ": True, "HE": True, "JL": True})
        self.assertTrue(all(item["time_budget_seconds"] == 150.0 for item in report["markets"].values()))

    def test_previous_awards_are_carried_forward_when_every_search_fails(self) -> None:
        stored = json.loads((PIPELINE_ROOT / "data" / "tianjin_award_records.json").read_text(encoding="utf-8"))
        existing = [copy.deepcopy(stored[0])]
        existing[0]["facts"]["market_code"] = "HE"
        expected_id = existing[0]["award_id"]

        def failing_search(url: str) -> str:
            raise TimeoutError("blocked")

        awards, report = regional.run_regional_award_sync(
            plan_path=regional.DEFAULT_PLAN,
            as_of=AS_OF,
            existing_awards=existing,
            pool_records=[],
            market_codes=["HE"],
            fetch_search=failing_search,
            fetch_detail=self._fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual([record["award_id"] for record in awards], [expected_id])
        self.assertEqual(awards[0]["facts"]["market_code"], "HE")
        self.assertFalse(report["publish_allowed"])
        self.assertEqual(report["publish_gate_reason"], "ALL_MARKETS_AWARD_DISCOVERY_FAILED")
        self.assertEqual(report["markets"]["HE"]["failure_count"], 10)


if __name__ == "__main__":
    unittest.main()
