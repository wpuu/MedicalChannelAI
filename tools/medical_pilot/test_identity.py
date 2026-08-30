from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.collector_core import ParsedNotice, Snapshot, build_event_and_facts


def snap(url: str, text: str = "fixture") -> Snapshot:
    body = text.encode("utf-8")
    return Snapshot(
        source_url=url,
        fetched_at="2026-08-28T10:00:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        text=text,
        sha256=hashlib.sha256(body).hexdigest(),
    )


def notice(*, source_id: str, url: str, project_number: str | None) -> ParsedNotice:
    return ParsedNotice(
        source_id=source_id,
        source_url=url,
        source_authority="OFFICIAL_HOSPITAL",
        notice_type="MARKET_RESEARCH",
        project_name="医疗设备市场调研",
        buyer_name="天津测试医院",
        published_at="2026-08-28T00:00:00+08:00",
        published_at_precision="DAY",
        project_number=project_number,
        evidence_fragments={
            "project_name": "医疗设备市场调研",
            "buyer_name": "天津测试医院",
            "published_at": "2026年08月28日",
        },
    )


class CanonicalIdentityTests(unittest.TestCase):
    def test_same_official_project_number_can_link_across_different_source_urls(self) -> None:
        first_url = "https://primary.example/project/1"
        second_url = "https://mirror.example/project/1"
        first_event, _ = build_event_and_facts(
            notice(source_id="primary_source", url=first_url, project_number="ABC-2026-001"),
            snap(first_url),
        )
        second_event, _ = build_event_and_facts(
            notice(source_id="official_mirror", url=second_url, project_number="ABC-2026-001"),
            snap(second_url),
        )
        self.assertEqual(first_event["canonical_project_id"], second_event["canonical_project_id"])
        self.assertNotEqual(first_event["event_id"], second_event["event_id"])

    def test_same_buyer_and_title_without_project_number_do_not_auto_merge_across_urls(self) -> None:
        first_url = "https://hospital.example/system/2026/08/01/100.shtml"
        second_url = "https://hospital.example/system/2026/08/28/200.shtml"
        first_event, first_facts = build_event_and_facts(
            notice(source_id="hospital_procurement", url=first_url, project_number=None),
            snap(first_url),
        )
        second_event, second_facts = build_event_and_facts(
            notice(source_id="hospital_procurement", url=second_url, project_number=None),
            snap(second_url),
        )
        self.assertNotEqual(first_event["canonical_project_id"], second_event["canonical_project_id"])
        self.assertNotEqual(
            {fact["opportunity_id"] for fact in first_facts},
            {fact["opportunity_id"] for fact in second_facts},
        )

    def test_same_source_record_url_is_stable_without_project_number(self) -> None:
        url = "https://hospital.example/system/2026/08/28/200.shtml"
        first_event, _ = build_event_and_facts(
            notice(source_id="hospital_procurement", url=url, project_number=None),
            snap(url, "first snapshot"),
        )
        second_event, _ = build_event_and_facts(
            notice(source_id="hospital_procurement", url=url, project_number=None),
            snap(url, "updated snapshot"),
        )
        self.assertEqual(first_event["canonical_project_id"], second_event["canonical_project_id"])


if __name__ == "__main__":
    unittest.main()
