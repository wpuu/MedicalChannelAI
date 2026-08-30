from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from .invite_auth import SQLiteInviteStore, issue_invite, redeem_invite
from .today_actions_http import TrustedPrincipal


NOW = datetime(2026, 8, 30, 4, 55, tzinfo=timezone.utc)


class InviteAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "pilot.sqlite"
        self.store = SQLiteInviteStore(self.db_path)
        self.principal = TrustedPrincipal("tenant-a", "profile-a")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_invite_redeems_once_to_bound_principal(self) -> None:
        invite = issue_invite(self.store, principal=self.principal, now=NOW)

        first = redeem_invite(self.store, invite.code, now=NOW + timedelta(seconds=1))
        second = redeem_invite(self.store, invite.code, now=NOW + timedelta(seconds=2))

        self.assertEqual(first, self.principal)
        self.assertIsNone(second)

    def test_raw_invite_code_is_not_stored(self) -> None:
        invite = issue_invite(self.store, principal=self.principal, now=NOW)
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT code_hash, tenant_id, profile_id FROM medical_invites"
            ).fetchone()

        self.assertIsNotNone(row)
        code_hash, tenant_id, profile_id = row
        self.assertNotEqual(code_hash, invite.code)
        self.assertEqual(len(code_hash), 64)
        self.assertEqual((tenant_id, profile_id), ("tenant-a", "profile-a"))

    def test_expired_invite_cannot_redeem(self) -> None:
        invite = issue_invite(
            self.store,
            principal=self.principal,
            now=NOW,
            ttl_seconds=60,
        )

        self.assertIsNone(
            redeem_invite(self.store, invite.code, now=NOW + timedelta(seconds=61))
        )

    def test_tampered_invite_cannot_redeem(self) -> None:
        invite = issue_invite(self.store, principal=self.principal, now=NOW)
        replacement = "A" if invite.code[-1] != "A" else "B"
        tampered = invite.code[:-1] + replacement

        self.assertIsNone(redeem_invite(self.store, tampered, now=NOW))


if __name__ == "__main__":
    unittest.main()
