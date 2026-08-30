from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from .collector_core import ParsedNotice, Snapshot, build_event_and_facts
from .collector_store import SQLitePublicEventLedger, persist_collector_result
from .today_repo import SQLiteTodayActionsRepository


def snapshot(url: str, fetched_at: str) -> Snapshot:
    body = b"verified fixture"
    return Snapshot(
        source_url=url,
        fetched_at=fetched_at,
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        text="verified fixture",
        sha256="0" * 64,
    )


def notice(
    *,
    url: str,
    notice_type: str,
    published_at: str,
    title: str = "流式细胞仪购置项目",
    precision: str = "MINUTE",
    verified: bool = True,
) -> ParsedNotice:
    evidence = {
        "buyer_name": "天津医科大学总医院",
        "published_at": published_at,
        "project_number": "TGPC-PERSIST-001",
        "budget_cny": "3200000.00",
        "procurement_method": "公开招标",
    }
    if verified:
        evidence["project_name"] = title
    return ParsedNotice(
        source_id="ccgp_local_notices",
        source_url=url,
        source_authority="OFFICIAL_GOVERNMENT",
        notice_type=notice_type,
        project_name=title,
        buyer_name="天津医科大学总医院",
        published_at=published_at,
        published_at_precision=precision,
        project_number="TGPC-PERSIST-001",
        budget_cny="3200000.00",
        procurement_method="公开招标",
        evidence_fragments=evidence,
        verification_reason=None if verified else "missing project_name evidence",
    )


def built(value: ParsedNotice, fetched_at: str):
    snap = snapshot(value.source_url, fetched_at)
    return build_event_and_facts(value, snap)


class CollectorStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "pilot.sqlite"
        self.repository = SQLiteTodayActionsRepository(path)
        self.ledger = SQLitePublicEventLedger(path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def persist(self, value: ParsedNotice, fetched_at: str):
        event, facts = built(value, fetched_at)
        return persist_collector_result(
            repository=self.repository,
            event_ledger=self.ledger,
            event=event,
            facts=facts,
        )

    def test_late_old_tender_does_not_regress_existing_award(self) -> None:
        award = notice(
            url="https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202608/t20260830_1.htm",
            notice_type="AWARD",
            published_at="2026-08-30T10:00:00+08:00",
        )
        tender = notice(
            url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260820_1.htm",
            notice_type="TENDER",
            published_at="2026-08-20T09:00:00+08:00",
        )

        first = self.persist(award, "2026-08-30T02:10:00Z")
        second = self.persist(tender, "2026-08-30T05:10:00Z")

        self.assertEqual(first["lifecycle_state"], "AWARDED")
        self.assertEqual(second["lifecycle_state"], "AWARDED")
        self.assertEqual(second["notice_type"], "AWARD")
        self.assertEqual(len(second["source_event_ids"]), 2)

    def test_projection_uses_registry_region_verified_institution_and_deterministic_taxonomy(self) -> None:
        item = self.persist(
            notice(
                url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260830_2.htm",
                notice_type="TENDER",
                published_at="2026-08-30T09:00:00+08:00",
            ),
            "2026-08-30T01:05:00Z",
        )

        self.assertEqual(item["region"]["province"], "天津市")
        self.assertEqual(item["region"]["city"], "天津市")
        self.assertEqual(item["region"]["district"], "和平区")
        self.assertEqual(item["hospital_name"], "天津医科大学总医院")
        self.assertEqual(item["customer_type"], "TERTIARY_HOSPITAL")
        self.assertEqual(item["customer_type_validation_status"], "VALIDATED")
        self.assertIn("LAB_FLOW_CYTOMETER", item["product_labels"])
        self.assertEqual(item["product_label_provenance"], "DETERMINISTIC")
        self.assertEqual(item["product_label_validation_status"], "VALIDATED")
        self.assertIs(item["is_rental_project"], False)
        self.assertEqual(
            item["rental_classification_provenance"],
            "DETERMINISTIC_EXPLICIT_PURCHASE_PHRASE",
        )

    def test_unverified_newer_event_cannot_replace_verified_current_lifecycle(self) -> None:
        verified = notice(
            url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260825_3.htm",
            notice_type="TENDER",
            published_at="2026-08-25T09:00:00+08:00",
        )
        unverified = notice(
            url="https://www.ccgp.gov.cn/cggg/dfgg/更正/202608/t20260831_3.htm",
            notice_type="AMENDMENT",
            published_at="2026-08-31T09:00:00+08:00",
            verified=False,
        )

        before = self.persist(verified, "2026-08-25T01:10:00Z")
        after = self.persist(unverified, "2026-08-31T01:10:00Z")

        self.assertEqual(before["lifecycle_state"], "TENDERING")
        self.assertEqual(after["lifecycle_state"], "TENDERING")
        self.assertEqual(after["verification_status"], "VERIFIED")
        self.assertIn(unverified.source_url, [event["source_url"] for event in self.ledger.list_project_events(after["canonical_project_id"])])

    def test_same_day_low_precision_conflicting_verified_states_fail_closed(self) -> None:
        tender = notice(
            url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260830_4.htm",
            notice_type="TENDER",
            published_at="2026-08-30T00:00:00+08:00",
            precision="DAY",
        )
        award = notice(
            url="https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202608/t20260830_4.htm",
            notice_type="AWARD",
            published_at="2026-08-30T00:00:00+08:00",
            precision="DAY",
        )

        self.persist(tender, "2026-08-30T01:00:00Z")
        item = self.persist(award, "2026-08-30T02:00:00Z")

        self.assertEqual(item["verification_status"], "CONFLICTED")
        self.assertEqual(item["lifecycle_state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
