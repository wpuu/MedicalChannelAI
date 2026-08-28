from __future__ import annotations

import unittest

from tools.medical_pilot.cross_stage_link import (
    LinkableRecord,
    suggest_cross_stage_link,
    suggest_cross_stage_links,
)


def record(
    *,
    project_id: str,
    event_id: str,
    event_type: str,
    buyer: str = "天津测试医院",
    title: str = "PCR仪采购项目",
    published_at: str,
    verification: str = "VERIFIED",
    project_number: str | None = None,
) -> LinkableRecord:
    return LinkableRecord(
        canonical_project_id=project_id,
        event_id=event_id,
        event_type=event_type,
        buyer_name=buyer,
        project_name=title,
        published_at=published_at,
        verification_status=verification,
        source_url=f"https://example.invalid/{event_id}",
        project_number=project_number,
    )


class CrossStageLinkCandidateTests(unittest.TestCase):
    def test_exact_verified_intent_to_tender_becomes_candidate_but_never_auto_merges(self) -> None:
        earlier = record(
            project_id="mprj_11111111-1111-1111-1111-111111111111",
            event_id="evt_11111111-1111-1111-1111-111111111111",
            event_type="PROCUREMENT_INTENT",
            published_at="2026-03-10T23:51:00+08:00",
        )
        later = record(
            project_id="mprj_22222222-2222-2222-2222-222222222222",
            event_id="evt_22222222-2222-2222-2222-222222222222",
            event_type="TENDER",
            published_at="2026-08-20T18:50:00+08:00",
            project_number="TJ-2026-001",
        )
        candidate = suggest_cross_stage_link(earlier, later)
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.status, "CANDIDATE_REQUIRES_EVIDENCE")
        self.assertFalse(candidate.auto_merge_allowed)
        self.assertEqual(candidate.confidence, 0.70)
        self.assertIn("EXACT_NORMALIZED_PROJECT_TITLE", candidate.reasons)

    def test_different_buyer_or_title_is_not_a_candidate(self) -> None:
        earlier = record(
            project_id="mprj_11111111-1111-1111-1111-111111111111",
            event_id="evt_11111111-1111-1111-1111-111111111111",
            event_type="MARKET_RESEARCH",
            published_at="2026-01-01T00:00:00+08:00",
        )
        different_buyer = record(
            project_id="mprj_22222222-2222-2222-2222-222222222222",
            event_id="evt_22222222-2222-2222-2222-222222222222",
            event_type="TENDER",
            buyer="天津另一家医院",
            published_at="2026-02-01T00:00:00+08:00",
        )
        different_title = record(
            project_id="mprj_33333333-3333-3333-3333-333333333333",
            event_id="evt_33333333-3333-3333-3333-333333333333",
            event_type="TENDER",
            title="另一套PCR仪采购项目",
            published_at="2026-02-01T00:00:00+08:00",
        )
        self.assertIsNone(suggest_cross_stage_link(earlier, different_buyer))
        self.assertIsNone(suggest_cross_stage_link(earlier, different_title))

    def test_unverified_or_backward_chronology_is_not_candidate(self) -> None:
        unverified = record(
            project_id="mprj_11111111-1111-1111-1111-111111111111",
            event_id="evt_11111111-1111-1111-1111-111111111111",
            event_type="PROCUREMENT_INTENT",
            published_at="2026-03-10T23:51:00+08:00",
            verification="UNVERIFIED",
        )
        tender = record(
            project_id="mprj_22222222-2222-2222-2222-222222222222",
            event_id="evt_22222222-2222-2222-2222-222222222222",
            event_type="TENDER",
            published_at="2026-08-20T18:50:00+08:00",
        )
        self.assertIsNone(suggest_cross_stage_link(unverified, tender))

        later_intent = record(
            project_id="mprj_33333333-3333-3333-3333-333333333333",
            event_id="evt_33333333-3333-3333-3333-333333333333",
            event_type="PROCUREMENT_INTENT",
            published_at="2026-09-01T00:00:00+08:00",
        )
        earlier_tender = record(
            project_id="mprj_44444444-4444-4444-4444-444444444444",
            event_id="evt_44444444-4444-4444-4444-444444444444",
            event_type="TENDER",
            published_at="2026-08-20T18:50:00+08:00",
        )
        self.assertIsNone(suggest_cross_stage_link(later_intent, earlier_tender))

    def test_conflicting_explicit_project_numbers_block_candidate(self) -> None:
        earlier = record(
            project_id="mprj_11111111-1111-1111-1111-111111111111",
            event_id="evt_11111111-1111-1111-1111-111111111111",
            event_type="INTERNAL_SELECTION",
            published_at="2026-01-01T00:00:00+08:00",
            project_number="A-001",
        )
        later = record(
            project_id="mprj_22222222-2222-2222-2222-222222222222",
            event_id="evt_22222222-2222-2222-2222-222222222222",
            event_type="TENDER",
            published_at="2026-02-01T00:00:00+08:00",
            project_number="B-999",
        )
        self.assertIsNone(suggest_cross_stage_link(earlier, later))

    def test_batch_suggestion_does_not_mutate_or_merge_records(self) -> None:
        records = [
            record(
                project_id="mprj_11111111-1111-1111-1111-111111111111",
                event_id="evt_11111111-1111-1111-1111-111111111111",
                event_type="PROCUREMENT_INTENT",
                published_at="2026-01-01T00:00:00+08:00",
            ),
            record(
                project_id="mprj_22222222-2222-2222-2222-222222222222",
                event_id="evt_22222222-2222-2222-2222-222222222222",
                event_type="TENDER",
                published_at="2026-02-01T00:00:00+08:00",
            ),
        ]
        candidates = suggest_cross_stage_links(records)
        self.assertEqual(len(candidates), 1)
        self.assertNotEqual(
            candidates[0].earlier_canonical_project_id,
            candidates[0].later_canonical_project_id,
        )
        self.assertFalse(candidates[0].auto_merge_allowed)


if __name__ == "__main__":
    unittest.main()
