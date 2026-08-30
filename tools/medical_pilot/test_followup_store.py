from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from .followup_store import FollowupConflictError, SQLiteFollowupStore
from .today_actions_http import TrustedPrincipal


NOW = datetime(2026, 8, 30, 5, 30, tzinfo=timezone.utc)
OPP_A = "opp_11111111-1111-1111-1111-111111111111"
OPP_B = "opp_22222222-2222-2222-2222-222222222222"
PRINCIPAL_A = TrustedPrincipal("tenant-a", "profile-a")
PRINCIPAL_B = TrustedPrincipal("tenant-b", "profile-b")


def request(
    *,
    status: str = "CONTACTED",
    mutation_id: str = "followup_mutation_0001",
    reason: str | None = None,
    remind_at: str | None = None,
    note: str | None = None,
) -> dict:
    payload = {
        "status": status,
        "mutation_id": mutation_id,
    }
    if reason is not None:
        payload["reason"] = reason
    if remind_at is not None:
        payload["remind_at"] = remind_at
    if note is not None:
        payload["note"] = note
    return payload


class FollowupStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SQLiteFollowupStore(Path(self.tmp.name) / "pilot.sqlite")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_default_state_is_new_and_contains_no_tenant_identity(self) -> None:
        state = self.store.state(principal=PRINCIPAL_A, opportunity_id=OPP_A)
        public = state.as_public_dict()
        self.assertEqual(public["current_status"], "NEW")
        self.assertEqual(public["history"], [])
        self.assertIsNone(public["remind_at"])
        self.assertNotIn("tenant_id", public)
        self.assertNotIn("profile_id", public)

    def test_same_mutation_and_same_payload_is_idempotent(self) -> None:
        first = self.store.append(
            principal=PRINCIPAL_A,
            opportunity_id=OPP_A,
            request=request(),
            now=NOW,
        )
        second = self.store.append(
            principal=PRINCIPAL_A,
            opportunity_id=OPP_A,
            request=request(),
            now=NOW,
        )
        self.assertTrue(first.inserted)
        self.assertFalse(second.inserted)
        self.assertEqual(first.event["followup_id"], second.event["followup_id"])
        self.assertEqual(len(self.store.list_events(principal=PRINCIPAL_A, opportunity_id=OPP_A)), 1)

    def test_mutation_id_is_bound_to_opportunity_and_payload(self) -> None:
        self.store.append(
            principal=PRINCIPAL_A,
            opportunity_id=OPP_A,
            request=request(mutation_id="followup_mutation_0002"),
            now=NOW,
        )
        with self.assertRaises(FollowupConflictError):
            self.store.append(
                principal=PRINCIPAL_A,
                opportunity_id=OPP_B,
                request=request(mutation_id="followup_mutation_0002"),
                now=NOW,
            )
        with self.assertRaises(FollowupConflictError):
            self.store.append(
                principal=PRINCIPAL_A,
                opportunity_id=OPP_A,
                request=request(status="REVIEWING", mutation_id="followup_mutation_0002"),
                now=NOW,
            )

    def test_tenant_and_profile_followup_histories_are_isolated(self) -> None:
        self.store.append(
            principal=PRINCIPAL_A,
            opportunity_id=OPP_A,
            request=request(status="CONTACTED", mutation_id="followup_mutation_0003"),
            now=NOW,
        )
        self.store.append(
            principal=PRINCIPAL_B,
            opportunity_id=OPP_A,
            request=request(status="ARCHIVED", mutation_id="followup_mutation_0003"),
            now=NOW,
        )
        state_a = self.store.state(principal=PRINCIPAL_A, opportunity_id=OPP_A)
        state_b = self.store.state(principal=PRINCIPAL_B, opportunity_id=OPP_A)
        self.assertEqual(state_a.current_status, "CONTACTED")
        self.assertEqual(state_b.current_status, "ARCHIVED")
        self.assertEqual(len(state_a.history), 1)
        self.assertEqual(len(state_b.history), 1)

    def test_same_timestamp_uses_actual_append_order_not_random_uuid_order(self) -> None:
        self.store.append(
            principal=PRINCIPAL_A,
            opportunity_id=OPP_A,
            request=request(status="REVIEWING", mutation_id="followup_mutation_0004"),
            now=NOW,
        )
        self.store.append(
            principal=PRINCIPAL_A,
            opportunity_id=OPP_A,
            request=request(status="CONTACTED", mutation_id="followup_mutation_0005"),
            now=NOW,
        )
        state = self.store.state(principal=PRINCIPAL_A, opportunity_id=OPP_A)
        self.assertEqual(state.current_status, "CONTACTED")
        self.assertEqual(state.history[0]["status"], "CONTACTED")
        self.assertEqual(state.history[1]["status"], "REVIEWING")

    def test_not_fit_generates_review_suggestion_but_never_auto_applies(self) -> None:
        self.store.append(
            principal=PRINCIPAL_A,
            opportunity_id=OPP_A,
            request=request(
                status="NOT_FIT",
                mutation_id="followup_mutation_0006",
                reason="NO_PRODUCT_CAPABILITY",
            ),
            now=NOW,
        )
        state = self.store.state(principal=PRINCIPAL_A, opportunity_id=OPP_A)
        self.assertEqual(state.current_status, "NOT_FIT")
        self.assertIsNotNone(state.profile_learning)
        assert state.profile_learning is not None
        self.assertEqual(state.profile_learning["learning_status"], "PROFILE_REVIEW_SUGGESTED")
        self.assertFalse(state.profile_learning["suggestions"][0]["auto_apply_allowed"])

    def test_not_fit_requires_known_reason_and_extra_identity_fields_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.append(
                principal=PRINCIPAL_A,
                opportunity_id=OPP_A,
                request=request(status="NOT_FIT", mutation_id="followup_mutation_0007"),
                now=NOW,
            )
        payload = request(mutation_id="followup_mutation_0008")
        payload["tenant_id"] = "attacker"
        with self.assertRaises(ValueError):
            self.store.append(
                principal=PRINCIPAL_A,
                opportunity_id=OPP_A,
                request=payload,
                now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
