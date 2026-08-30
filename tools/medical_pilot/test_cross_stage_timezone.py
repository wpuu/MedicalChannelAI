from __future__ import annotations

import unittest

from tools.medical_pilot.cross_stage_link import LinkableRecord, suggest_cross_stage_link


def rec(project_id: str, event_id: str, event_type: str, published_at: str) -> LinkableRecord:
    return LinkableRecord(
        canonical_project_id=project_id,
        event_id=event_id,
        event_type=event_type,
        buyer_name="天津测试医院",
        project_name="同一采购项目",
        published_at=published_at,
        verification_status="VERIFIED",
        source_url=f"https://example.invalid/{event_id}",
    )


class CrossStageTimezoneTests(unittest.TestCase):
    def test_z_and_plus8_are_compared_as_real_instants_not_strings(self) -> None:
        # 00:30Z = 08:30+08, so the later tender at 09:00+08 is chronologically valid.
        intent = rec(
            "mprj_11111111-1111-1111-1111-111111111111",
            "evt_11111111-1111-1111-1111-111111111111",
            "PROCUREMENT_INTENT",
            "2026-08-28T00:30:00Z",
        )
        tender = rec(
            "mprj_22222222-2222-2222-2222-222222222222",
            "evt_22222222-2222-2222-2222-222222222222",
            "TENDER",
            "2026-08-28T09:00:00+08:00",
        )
        self.assertIsNotNone(suggest_cross_stage_link(intent, tender))

    def test_z_time_that_is_actually_later_blocks_backward_bridge(self) -> None:
        # 02:00Z = 10:00+08, which is later than the tender at 09:00+08.
        intent = rec(
            "mprj_11111111-1111-1111-1111-111111111111",
            "evt_11111111-1111-1111-1111-111111111111",
            "PROCUREMENT_INTENT",
            "2026-08-28T02:00:00Z",
        )
        tender = rec(
            "mprj_22222222-2222-2222-2222-222222222222",
            "evt_22222222-2222-2222-2222-222222222222",
            "TENDER",
            "2026-08-28T09:00:00+08:00",
        )
        self.assertIsNone(suggest_cross_stage_link(intent, tender))

    def test_naive_timestamp_fails_closed(self) -> None:
        intent = rec(
            "mprj_11111111-1111-1111-1111-111111111111",
            "evt_11111111-1111-1111-1111-111111111111",
            "PROCUREMENT_INTENT",
            "2026-08-28T08:00:00",
        )
        tender = rec(
            "mprj_22222222-2222-2222-2222-222222222222",
            "evt_22222222-2222-2222-2222-222222222222",
            "TENDER",
            "2026-08-28T09:00:00+08:00",
        )
        self.assertIsNone(suggest_cross_stage_link(intent, tender))


if __name__ == "__main__":
    unittest.main()
