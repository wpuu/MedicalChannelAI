from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from .collector_core import Snapshot
from .discovery_runtime import (
    DISCOVERY_READY_LISTINGS,
    SQLiteDiscoveryUrlLedger,
    discovery_readiness,
    extract_registered_detail_links,
    listing_pages_for_source,
    run_source_discovery_once,
)


NOW = datetime(2026, 8, 30, 5, 30, tzinfo=timezone.utc)


def listing_snapshot(url: str, html: str) -> Snapshot:
    return Snapshot(
        source_url=url,
        fetched_at=NOW.isoformat(),
        status_code=200,
        content_type="text/html",
        body=html.encode("utf-8"),
        text=html,
        sha256="1" * 64,
    )


class DiscoveryRuntimeTests(unittest.TestCase):
    def test_three_verified_listing_contracts_are_ready(self) -> None:
        self.assertEqual(
            set(DISCOVERY_READY_LISTINGS),
            {"tjmugh_procurement", "tj_first_central_hospital_procurement", "ccgp_local_notices"},
        )
        self.assertEqual(discovery_readiness("tjmugh_procurement")[0], True)
        ready, reason = discovery_readiness("ccgp_local_notices")
        self.assertTrue(ready)
        self.assertEqual(reason, "VERIFIED_EXPLICIT_TIANJIN_REGION_FILTER_BOUNDED_TWO_PAGE_PARTIAL")
        self.assertFalse(discovery_readiness("tj_government_procurement")[0])
        self.assertFalse(discovery_readiness("tj_government_procurement_center")[0])
        self.assertFalse(discovery_readiness("ccgp_procurement_intent")[0])
        self.assertFalse(discovery_readiness("tj_public_resource_exchange")[0])

    def test_hospital_listing_only_admits_registered_detail_urls(self) -> None:
        html = """
        <html><body>
          <a href="/system/2026/08/30/12345.shtml">医疗设备市场调研公告</a>
          <a href="https://attacker.example/system/2026/08/30/999.shtml">医疗设备采购</a>
          <a href="/about/index.shtml">医疗设备介绍</a>
        </body></html>
        """
        links = extract_registered_detail_links("tjmugh_procurement", html)

        self.assertEqual(
            links,
            [("https://www.tjmugh.com.cn/system/2026/08/30/12345.shtml", "医疗设备市场调研公告")],
        )

    def test_ccgp_national_listing_requires_tianjin_in_same_record(self) -> None:
        html = """
        <html><body>
          <div>页面其他位置出现天津不能给任何行授权</div>
          <ul>
            <li>
              <a href="/cggg/dfgg/gkzb/202608/t20260824_27194440.htm">天津市滨海新区海滨人民医院采购人工智能 GPU 算力服务器项目公开招标公告</a>
              <span>公开招标 发布时间：2026-08-24 18:50 地域：天津 采购人：天津市滨海新区海滨人民医院</span>
            </li>
            <li>
              <a href="/cggg/dfgg/gkzb/202608/t20260827_99999999.htm">某省人民医院医疗设备采购项目公开招标公告</a>
              <span>公开招标 发布时间：2026-08-27 18:50 地域：山东 采购人：某人民医院</span>
            </li>
            <li>
              <a href="/cggg/dfgg/gkzb/202608/t20260827_88888888.htm">天津市道路绿化提升工程公开招标公告</a>
              <span>公开招标 发布时间：2026-08-27 18:50 地域：天津市 采购人：天津市某委员会</span>
            </li>
            <li>
              <a href="https://attacker.example/cggg/dfgg/gkzb/202608/t20260827_77777777.htm">天津医院医疗设备采购</a>
              <span>地域：天津 采购人：天津医院</span>
            </li>
          </ul>
        </body></html>
        """

        links = extract_registered_detail_links("ccgp_local_notices", html)
        self.assertEqual(
            links,
            [
                (
                    "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260824_27194440.htm",
                    "天津市滨海新区海滨人民医院采购人工智能 GPU 算力服务器项目公开招标公告",
                )
            ],
        )

    def test_ccgp_region_text_outside_notice_record_never_grants_tianjin_scope(self) -> None:
        html = """
        <html><body>
          <div>地域：天津</div>
          <li>
            <a href="/cggg/dfgg/gkzb/202608/t20260827_99999999.htm">人民医院医疗设备采购项目公开招标公告</a>
            <span>地域：河北 采购人：某人民医院</span>
          </li>
        </body></html>
        """
        self.assertEqual(extract_registered_detail_links("ccgp_local_notices", html), [])

    def test_ccgp_generic_equipment_word_is_not_enough_but_medical_purchaser_is(self) -> None:
        html = """
        <html><body><ul>
          <li>
            <a href="/cggg/dfgg/gkzb/202608/t20260830_30000001.htm">教学设备更新项目公开招标公告</a>
            <span>地域：天津 采购人：天津市某职业学校</span>
          </li>
          <li>
            <a href="/cggg/dfgg/gkzb/202608/t20260830_30000002.htm">信息化设备更新项目公开招标公告</a>
            <span>地域：天津 采购人：天津市某人民医院</span>
          </li>
          <li>
            <a href="/cggg/dfgg/gkzb/202608/t20260830_30000003.htm">科研设备采购项目公开招标公告</a>
            <span>地域：天津市 采购人：天津医科大学</span>
          </li>
        </ul></body></html>
        """
        links = extract_registered_detail_links("ccgp_local_notices", html)
        self.assertEqual(
            [url for url, _title in links],
            [
                "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260830_30000002.htm",
                "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260830_30000003.htm",
            ],
        )

    def test_ccgp_ready_contract_is_explicitly_bounded_two_page_partial_not_exhaustive(self) -> None:
        self.assertEqual(
            DISCOVERY_READY_LISTINGS["ccgp_local_notices"],
            "https://www.ccgp.gov.cn/cggg/dfgg/index.htm",
        )
        self.assertEqual(
            listing_pages_for_source("ccgp_local_notices"),
            (
                "https://www.ccgp.gov.cn/cggg/dfgg/index.htm",
                "https://www.ccgp.gov.cn/cggg/dfgg/index_1.htm",
            ),
        )
        _, reason = discovery_readiness("ccgp_local_notices")
        self.assertIn("BOUNDED_TWO_PAGE_PARTIAL", reason)

    def test_successful_detail_is_not_refetched_until_recheck_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "pilot.sqlite"
            listing_url = DISCOVERY_READY_LISTINGS["tjmugh_procurement"]
            html = '<a href="/system/2026/08/30/12345.shtml">医疗设备市场调研公告</a>'
            calls: list[str] = []

            def fake_fetch(url: str):
                return listing_snapshot(url, html)

            def fake_ingest(url: str, path: Path):
                self.assertEqual(path, db)
                calls.append(url)
                return object()

            first = run_source_discovery_once(
                "tjmugh_procurement",
                db_path=db,
                now=NOW,
                fetch_listing=fake_fetch,
                ingest_detail=fake_ingest,
            )
            second = run_source_discovery_once(
                "tjmugh_procurement",
                db_path=db,
                now=NOW + timedelta(minutes=10),
                fetch_listing=fake_fetch,
                ingest_detail=fake_ingest,
            )

            self.assertEqual(first.persisted_count, 1)
            self.assertEqual(second.attempted_count, 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(first.listing_url, listing_url)
            self.assertEqual(first.listing_page_count, 1)

    def test_ccgp_two_verified_pages_merge_dedupe_and_persist_same_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "pilot.sqlite"
            head_url, page_1_url = listing_pages_for_source("ccgp_local_notices")
            head_html = """
            <li>
              <a href="/cggg/dfgg/gkzb/202608/t20260830_27194440.htm">天津市某医院医疗设备采购项目公开招标公告</a>
              <span>发布时间：2026-08-30 18:50 地域：天津 采购人：天津市某医院</span>
            </li>
            """
            page_1_html = """
            <li>
              <a href="/cggg/dfgg/gkzb/202608/t20260830_27194440.htm">天津市某医院医疗设备采购项目公开招标公告</a>
              <span>发布时间：2026-08-30 18:50 地域：天津 采购人：天津市某医院</span>
            </li>
            <li>
              <a href="/cggg/dfgg/zbgg/202608/t20260830_27194441.htm">天津市另一医院检验设备采购项目中标公告</a>
              <span>发布时间：2026-08-30 17:50 地域：天津市 采购人：天津市另一医院</span>
            </li>
            """
            fetched: list[str] = []
            ingested: list[str] = []

            def fake_fetch(url: str):
                fetched.append(url)
                if url == head_url:
                    return listing_snapshot(url, head_html)
                if url == page_1_url:
                    return listing_snapshot(url, page_1_html)
                raise AssertionError(url)

            result = run_source_discovery_once(
                "ccgp_local_notices",
                db_path=db,
                now=NOW,
                fetch_listing=fake_fetch,
                ingest_detail=lambda url, path: ingested.append(url),
            )

            self.assertEqual(fetched, [head_url, page_1_url])
            self.assertEqual(result.listing_url, head_url)
            self.assertEqual(result.listing_urls, (head_url, page_1_url))
            self.assertEqual(result.listing_page_count, 2)
            self.assertEqual(result.discovered_count, 2)
            self.assertEqual(result.persisted_count, 2)
            self.assertEqual(
                set(ingested),
                {
                    "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260830_27194440.htm",
                    "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202608/t20260830_27194441.htm",
                },
            )

    def test_ccgp_second_listing_page_failure_aborts_before_detail_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "pilot.sqlite"
            head_url, page_1_url = listing_pages_for_source("ccgp_local_notices")
            ingested: list[str] = []

            def fake_fetch(url: str):
                if url == head_url:
                    return listing_snapshot(
                        url,
                        """
                        <li>
                          <a href="/cggg/dfgg/gkzb/202608/t20260830_27194440.htm">天津医院医疗设备采购项目公开招标公告</a>
                          <span>地域：天津 采购人：天津医院</span>
                        </li>
                        """,
                    )
                if url == page_1_url:
                    raise TimeoutError("second listing page unavailable")
                raise AssertionError(url)

            with self.assertRaises(TimeoutError):
                run_source_discovery_once(
                    "ccgp_local_notices",
                    db_path=db,
                    now=NOW,
                    fetch_listing=fake_fetch,
                    ingest_detail=lambda url, path: ingested.append(url),
                )

            self.assertEqual(ingested, [])

    def test_failed_detail_uses_backoff_in_persistent_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "pilot.sqlite"
            ledger = SQLiteDiscoveryUrlLedger(db)
            url = "https://www.tjmugh.com.cn/system/2026/08/30/12345.shtml"
            ledger.register("tjmugh_procurement", [(url, "医疗设备采购")], now=NOW)
            self.assertEqual(ledger.due_urls("tjmugh_procurement", now=NOW), [url])
            ledger.mark_failure("tjmugh_procurement", url, now=NOW, error_code="NETWORK_ERROR")

            self.assertEqual(
                ledger.due_urls("tjmugh_procurement", now=NOW + timedelta(minutes=14)),
                [],
            )
            self.assertEqual(
                ledger.due_urls("tjmugh_procurement", now=NOW + timedelta(minutes=15)),
                [url],
            )


if __name__ == "__main__":
    unittest.main()
