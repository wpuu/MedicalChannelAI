from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import sync_regional_events as sync  # noqa: E402
from medical_channel_pipeline.ccgp_discovery import DiscoveryCandidate  # noqa: E402
from medical_channel_pipeline.public_snapshot import OFFICIAL_PACKAGE_NOTICE_FLAG  # noqa: E402
from publish_web_snapshot import regional_notice_events  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLAN_PATH = ROOT / "data" / "regional_event_query_plan.json"
AS_OF = datetime(2026, 9, 29, 4, 0, tzinfo=timezone.utc)

FAILED_BID_URL = "https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202609/t20260924_27401689.htm"
PACKAGE_CORRECTION_URL = "https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260924_27397249.htm"
FOREIGN_NUMBER_URL = "https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260928_27407474.htm"
BROKEN_URL = "https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202609/t20260929_00000009.htm"
UNMATCHED_URL = "https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260924_00000008.htm"

DETAILS = {
    FAILED_BID_URL: "ccgp_event_beijing_package_failed_bid.html",
    PACKAGE_CORRECTION_URL: "ccgp_event_beijing_package_correction.html",
    FOREIGN_NUMBER_URL: "ccgp_event_heilongjiang_project_correction.html",
}

POOL = [
    {
        "facts": {
            "market_code": "BJ",
            "project_number": "202601",
            "project_name": "市属医院2026年医用设备集中带量采购放射组",
            "bid_deadline": "2026-10-15T08:00:00+08:00",
        }
    },
    {
        "facts": {
            "market_code": "BJ",
            "project_number": "11010226210200025327-XM001",
            "project_name": "公改示范项目（第一批）-西城区骨健康特色诊疗中心项目（丰盛医院）",
            "bid_deadline": "2026-10-14T09:30:00+08:00",
        }
    },
    {
        "facts": {
            "market_code": "BJ",
            "project_number": "BJ-EXPIRED-2026-001",
            "project_name": "已截止的北京某医院设备采购项目",
            "bid_deadline": "2026-09-01T09:30:00+08:00",
        }
    },
    {
        "facts": {
            "market_code": "BJ",
            "project_number": "11010026210200099999-XM001",
            "project_name": "北京某医院数字化手术室建设项目",
            "bid_deadline": None,
        }
    },
    {
        "facts": {
            "market_code": "HE",
            "project_number": "202601",
            "project_name": "河北某医院同号项目",
            "bid_deadline": "2026-10-20T09:00:00+08:00",
        }
    },
]


def _candidate(url: str, title: str, *, region: str = "北京市", published_at: str = "2026-09-24", notice_type: str = "终止公告") -> DiscoveryCandidate:
    return DiscoveryCandidate(
        title=title,
        detail_url=url,
        published_at=published_at,
        buyer_name=None,
        region=region,
        notice_type=notice_type,
        search_keyword="医院",
    )


def _fetch_detail(url: str) -> str:
    if url == BROKEN_URL:
        return "<html><body>页面不存在</body></html>"
    return (FIXTURES / DETAILS[url]).read_text(encoding="utf-8")


class PlanAndMatchingTests(unittest.TestCase):
    def test_repo_plan_is_regional_only_and_event_typed(self) -> None:
        plan = sync.load_plan(PLAN_PATH)
        self.assertEqual(plan["market_codes"], ["BJ", "HE", "LN", "JL", "HL"])
        self.assertEqual(plan["notice_types"], ["更正公告", "终止公告"])
        self.assertGreaterEqual(plan["delay_seconds"], 4.0)
        self.assertEqual(plan["per_market_time_budget_seconds"], 150.0)

    def test_titles_match_pool_by_long_number_or_name_only(self) -> None:
        index = sync.pool_index(POOL, "BJ", AS_OF, min_name_chars=10)
        self.assertEqual(
            sorted(entry["project_number"] for entry in index),
            ["11010026210200099999-xm001", "11010226210200025327-xm001", "202601"],
        )  # expired project excluded, deadline-less project kept
        self.assertEqual(
            sync.match_candidate(_candidate(FAILED_BID_URL, "市属医院2026年医用设备集中带量采购放射组第14包、第16包废标公告"), index),
            ("NAME", "202601"),
        )
        self.assertEqual(
            sync.match_candidate(_candidate(PACKAGE_CORRECTION_URL, "公改示范项目（第一批）-西城区骨健康特色诊疗中心项目（丰盛医院）06包更正公告"), index),
            ("NAME", "11010226210200025327-xm001"),
        )
        self.assertEqual(
            sync.match_candidate(_candidate(BROKEN_URL, "关于 11010226210200025327-XM001 项目的终止公告"), index),
            ("NUMBER", "11010226210200025327-xm001"),
        )
        # Short numbers never match by number (they hide inside dates and other ids).
        self.assertIsNone(sync.match_candidate(_candidate(BROKEN_URL, "某项目202601终止公告"), index))
        self.assertIsNone(sync.match_candidate(_candidate(UNMATCHED_URL, "房山区良乡医院租赁腹腔镜机器人采购项目更正公告"), index))


class MarketEventSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = sync.load_plan(PLAN_PATH)
        self.sleeps: list[float] = []
        self.search_urls: list[str] = []
        self.fetched: list[str] = []
        self.candidates = [
            _candidate(FAILED_BID_URL, "市属医院2026年医用设备集中带量采购放射组第14包、第16包废标公告"),
            _candidate(PACKAGE_CORRECTION_URL, "公改示范项目（第一批）-西城区骨健康特色诊疗中心项目（丰盛医院）06包更正公告", notice_type="更正公告"),
            _candidate(FOREIGN_NUMBER_URL, "市属医院2026年医用设备集中带量采购放射组（二）第8包更正公告", notice_type="更正公告"),
            _candidate(BROKEN_URL, "11010026210200099999-XM001 北京某医院数字化手术室建设项目终止公告", published_at="2026-09-29"),
            _candidate(UNMATCHED_URL, "房山区良乡医院租赁腹腔镜机器人采购项目更正公告", notice_type="更正公告"),
            _candidate("https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260924_00000007.htm", "市属医院2026年医用设备集中带量采购放射组第1包更正公告", region="河北省"),
        ]
        self._orig_parse = sync.parse_search_html
        sync.parse_search_html = lambda html, keyword: list(self.candidates) if keyword == "医院" else []

    def tearDown(self) -> None:
        sync.parse_search_html = self._orig_parse

    def _fetch_search(self, url: str) -> str:
        self.search_urls.append(url)
        return url

    def _fetch_detail(self, url: str) -> str:
        self.fetched.append(url)
        return _fetch_detail(url)

    def test_market_run_verifies_matched_titles_only_and_stamps_market(self) -> None:
        events, report = sync.run_market_event_sync(
            plan=self.plan,
            market_code="BJ",
            as_of=AS_OF,
            existing_events=[],
            pool_records=POOL,
            fetch_search=self._fetch_search,
            fetch_detail=self._fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual(len(self.search_urls), 10)
        self.assertTrue(all("zoneId=11" in url for url in self.search_urls))
        self.assertTrue(all("bidType=8" in url or "bidType=12" in url for url in self.search_urls))
        self.assertTrue(all(delay >= 4 for delay in self.sleeps))
        # Unmatched and region-mismatched rows never cost a detail request.
        self.assertNotIn(UNMATCHED_URL, self.fetched)
        self.assertEqual(report["region_mismatch_count"], 2)  # the foreign row, once per "医院" query
        self.assertEqual(report["unmatched_title_count"], 2)
        self.assertEqual(report["matched_candidate_count"], 4)
        self.assertEqual(sorted(self.fetched), sorted([FAILED_BID_URL, PACKAGE_CORRECTION_URL, FOREIGN_NUMBER_URL, BROKEN_URL]))

        by_url = {event["source_url"]: event for event in events}
        self.assertEqual(set(by_url), {FAILED_BID_URL, PACKAGE_CORRECTION_URL, BROKEN_URL})
        self.assertTrue(all(event["market_code"] == "BJ" for event in events))
        failed_bid = by_url[FAILED_BID_URL]
        self.assertEqual((failed_bid["event_type"], failed_bid["scope"], failed_bid["packages"]), ("TERMINATION", "PACKAGE", ["第14包", "第16包"]))
        self.assertEqual(by_url[PACKAGE_CORRECTION_URL]["scope"], "PACKAGE")
        # Title quoted the pool number but the detail could not be parsed: discovery-only fallback.
        fallback = by_url[BROKEN_URL]
        self.assertEqual(fallback["summary"], "DISCOVERY_ONLY_EVENT_REQUIRES_DETAIL_REVIEW")
        self.assertEqual(fallback["project_number"], "11010026210200099999-xm001")
        self.assertTrue(fallback["terminal"])
        # A name match whose official detail names another project number is dropped.
        self.assertEqual(report["number_mismatch_count"], 1)
        self.assertEqual(report["number_mismatches"][0]["url"], FOREIGN_NUMBER_URL)
        self.assertEqual(report["number_mismatches"][0]["detail_project_number"], "[230225]CQXMGL[GK]20260003-1")
        self.assertEqual(report["failure_count"], 1)
        self.assertEqual(report["failures"][0]["url"], BROKEN_URL)
        self.assertEqual(report["new_event_count"], 3)
        self.assertTrue(report["publish_allowed"])
        self.assertTrue(report["policy"]["every_event_carries_market_code"])

    def test_regional_run_merges_markets_and_keeps_existing_events(self) -> None:
        existing = [
            {
                "schema_version": "0.1",
                "event_id": "termination_existing_he",
                "event_type": "TERMINATION",
                "project_number": "HE-OLD-2026-001",
                "project_name": "河北旧项目",
                "published_at": "2026-09-20",
                "source_url": "https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202609/t20260920_00000001.htm",
                "observed_at": "2026-09-20T10:00:00+00:00",
                "summary": None,
                "changed_fact_paths": [],
                "fact_overrides": {},
                "unresolved_fact_paths": [],
                "requires_reconciliation": False,
                "terminal": True,
                "market_code": "HE",
            }
        ]
        merged, report = sync.run_regional_event_sync(
            plan_path=PLAN_PATH,
            as_of=AS_OF,
            existing_events=existing,
            pool_records=POOL,
            market_codes=["BJ", "HE"],
            fetch_search=self._fetch_search,
            fetch_detail=self._fetch_detail,
            sleep=self.sleeps.append,
        )
        self.assertEqual(report["market_codes"], ["BJ", "HE"])
        self.assertEqual(report["merged_event_count_by_market"], {"BJ": 3, "HE": 1})
        self.assertEqual(report["markets"]["HE"]["new_event_count"], 0)  # every row is Beijing geography
        self.assertEqual(report["markets"]["HE"]["region_mismatch_count"], 10)  # five Beijing rows × two "医院" queries
        self.assertTrue(report["publish_allowed"])
        self.assertEqual(regional_notice_events(merged), merged)
        with self.assertRaisesRegex(ValueError, "REGIONAL_EVENT_MARKET_CODE_REQUIRED"):
            regional_notice_events([dict(existing[0], market_code=None)])
        with self.assertRaisesRegex(ValueError, "REGIONAL_EVENT_MARKET_NOT_IN_PLAN"):
            sync.run_regional_event_sync(
                plan_path=PLAN_PATH,
                as_of=AS_OF,
                existing_events=[],
                pool_records=POOL,
                market_codes=["TJ"],
                fetch_search=self._fetch_search,
                fetch_detail=self._fetch_detail,
                sleep=self.sleeps.append,
            )

    def test_time_budget_stops_requests_but_keeps_verified_events(self) -> None:
        ticks = iter([0.0, 0.0, 0.0, 0.0, 0.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0])
        events, report = sync.run_market_event_sync(
            plan=self.plan,
            market_code="BJ",
            as_of=AS_OF,
            existing_events=[],
            pool_records=POOL,
            time_budget_seconds=120,
            fetch_search=self._fetch_search,
            fetch_detail=self._fetch_detail,
            sleep=self.sleeps.append,
            clock=lambda: next(ticks, 200.0),
        )
        self.assertTrue(report["time_budget_exhausted"])
        self.assertGreater(report["skipped_count"], 0)
        self.assertLess(len(self.search_urls), 10)
        self.assertEqual(report["new_event_count"], len(events))
        self.assertEqual(self.fetched, [])  # the budget was gone before any detail request

    def test_official_notice_flag_is_exported_for_the_ui(self) -> None:
        self.assertEqual(OFFICIAL_PACKAGE_NOTICE_FLAG, "OFFICIAL_PACKAGE_NOTICE_REPORTED")


if __name__ == "__main__":
    unittest.main()
