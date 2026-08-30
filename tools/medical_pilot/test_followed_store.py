from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.followed_store import SQLiteFollowedOpportunityStore
from tools.medical_pilot.followup_store import SQLiteFollowupStore
from tools.medical_pilot.today_actions_http import TrustedPrincipal


NOW = datetime(2026, 8, 30, 8, 55, tzinfo=timezone.utc)
OPP_A = "opp_11111111-1111-1111-1111-111111111111"
OPP_B = "opp_22222222-2222-2222-2222-222222222222"


class FollowedStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "pilot.sqlite"
        self.followup = SQLiteFollowupStore(self.path)
        self.store = SQLiteFollowedOpportunityStore(self.path)
        self.a = TrustedPrincipal("tenant-a", "profile-a")
        self.b = TrustedPrincipal("tenant-b", "profile-b")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def append(self, principal, opportunity_id: str, status: str, mutation: str) -> None:
        self.followup.append(
            principal=principal,
            opportunity_id=opportunity_id,
            request={
                "status": status,
                "note": f"note-{status}",
                "remind_at": None,
                "mutation_id": mutation,
            },
            now=NOW,
        )

    def test_only_latest_state_per_opportunity_is_returned(self) -> None:
        self.append(self.a, OPP_A, "REVIEWING", "followed_store_mutation_0001")
        self.append(self.a, OPP_A, "CONTACTED", "followed_store_mutation_0002")
        self.append(self.a, OPP_B, "MONITOR", "followed_store_mutation_0003")
        rows = self.store.list_current(principal=self.a)
        by_id = {item.opportunity_id: item for item in rows}
        self.assertEqual(len(by_id), 2)
        self.assertEqual(by_id[OPP_A].status, "CONTACTED")
        self.assertEqual(by_id[OPP_B].status, "MONITOR")

    def test_tenant_profile_isolation_and_archived_default_filter(self) -> None:
        self.append(self.a, OPP_A, "CONTACTED", "followed_store_mutation_0004")
        self.append(self.b, OPP_B, "REVIEWING", "followed_store_mutation_0004")
        self.assertEqual(
            [item.opportunity_id for item in self.store.list_current(principal=self.a)],
            [OPP_A],
        )
        self.assertEqual(
            [item.opportunity_id for item in self.store.list_current(principal=self.b)],
            [OPP_B],
        )

        self.append(self.a, OPP_A, "ARCHIVED", "followed_store_mutation_0005")
        self.assertEqual(self.store.list_current(principal=self.a), [])
        archived = self.store.list_current(principal=self.a, include_archived=True)
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].status, "ARCHIVED")


if __name__ == "__main__":
    unittest.main()
