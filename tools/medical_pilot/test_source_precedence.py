from __future__ import annotations

import unittest

from tools.medical_pilot.lifecycle import resolve_project_lifecycle
from tools.medical_pilot.registry import RegisteredSource, load_registry
from tools.medical_pilot.source_precedence import preferred_event


def event(
    event_id: str,
    source_id: str,
    event_type: str,
    published_at: str,
    precision: str,
) -> dict:
    return {
        "event_id": event_id,
        "canonical_project_id": "mprj_00000000-0000-0000-0000-000000000001",
        "event_type": event_type,
        "source_id": source_id,
        "verification_status": "VERIFIED",
        "published_at": published_at,
        "effective_at": published_at,
        "published_at_precision": precision,
    }


def registered(source_id: str, role: str) -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        source_name=source_id,
        canonical_base_url="https://example.invalid/",
        allowed_url_patterns=(),
        enabled=True,
        authority_type="OFFICIAL_GOVERNMENT",
        source_type="GOVERNMENT_PROCUREMENT",
        provenance_role=role,
        parser_version=None,
        raw={"provenance_role": role},
    )


class SourcePrecedenceTests(unittest.TestCase):
    def test_runtime_registry_classifies_ccgp_and_public_resource_as_mirrors(self) -> None:
        roles = {source.source_id: source.provenance_role for source in load_registry()}
        self.assertEqual(roles["ccgp_local_notices"], "OFFICIAL_MIRROR")
        self.assertEqual(roles["ccgp_procurement_intent"], "OFFICIAL_MIRROR")
        self.assertEqual(roles["tj_public_resource_exchange"], "OFFICIAL_MIRROR")
        self.assertEqual(roles["tjmugh_procurement"], "PRIMARY_SOURCE")

    def test_primary_source_beats_more_precise_mirror_on_same_calendar_day(self) -> None:
        primary = event(
            "evt_00000000-0000-0000-0000-000000000001",
            "primary",
            "AWARD",
            "2026-07-31T00:00:00+08:00",
            "DAY",
        )
        mirror = event(
            "evt_00000000-0000-0000-0000-000000000002",
            "mirror",
            "AWARD",
            "2026-07-31T23:50:00+08:00",
            "MINUTE",
        )
        chosen = preferred_event(
            [primary, mirror],
            registry=[registered("primary", "PRIMARY_SOURCE"), registered("mirror", "OFFICIAL_MIRROR")],
        )
        self.assertEqual(chosen["event_id"], primary["event_id"])

    def test_day_precision_prevents_fake_ordering_of_conflicting_same_day_states(self) -> None:
        tender = event(
            "evt_00000000-0000-0000-0000-000000000010",
            "ccgp_local_notices",
            "TENDER",
            "2026-08-24T18:50:00+08:00",
            "MINUTE",
        )
        termination = event(
            "evt_00000000-0000-0000-0000-000000000011",
            "tj_public_resource_exchange",
            "TERMINATION",
            "2026-08-24T00:00:00+08:00",
            "DAY",
        )
        aggregate = resolve_project_lifecycle([tender, termination])
        self.assertEqual(aggregate.verification_status, "CONFLICTED")
        self.assertEqual(aggregate.lifecycle_state, "UNKNOWN")
        self.assertEqual(set(aggregate.conflict_event_ids), {tender["event_id"], termination["event_id"]})

    def test_minute_precision_keeps_real_chronology_when_both_times_are_known(self) -> None:
        tender = event(
            "evt_00000000-0000-0000-0000-000000000020",
            "ccgp_local_notices",
            "TENDER",
            "2026-08-24T09:00:00+08:00",
            "MINUTE",
        )
        termination = event(
            "evt_00000000-0000-0000-0000-000000000021",
            "ccgp_local_notices",
            "TERMINATION",
            "2026-08-24T18:50:00+08:00",
            "MINUTE",
        )
        aggregate = resolve_project_lifecycle([tender, termination])
        self.assertEqual(aggregate.verification_status, "VERIFIED")
        self.assertEqual(aggregate.lifecycle_state, "TERMINATED")
        self.assertEqual(aggregate.current_event_id, termination["event_id"])


if __name__ == "__main__":
    unittest.main()
