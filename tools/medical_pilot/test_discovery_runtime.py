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
    def test_only_two_dedicated_hospital_lists_are_ready(self) -> None:
        self.assertEqual(
            set(DISCOVERY_READY_LISTINGS),
            {"tjmugh_procurement", "tj_first_central_hospital_procurement"},
        )
        self.assertEqual(discovery_readiness("tjmugh_procurement")[0], True)
        ready, reason = discovery_readiness("ccgp_local_notices")
        self.assertFalse(ready)
        self.assertEqual(reason, "GENERIC_NATIONAL_LIST_NOT_TIANJIN_SCOPED")
        self.assertFalse(discovery_readiness("tj_government_procurement")[0])
        self.assertFalse(discovery_readiness("tj_government_procurement_center")[0])

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
