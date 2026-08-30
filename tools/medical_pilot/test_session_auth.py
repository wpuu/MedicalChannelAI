from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from .session_auth import (
    OpaqueCookiePrincipalResolver,
    SESSION_COOKIE_NAME,
    SQLiteSessionStore,
    issue_session,
    revoke_session,
)
from .today_actions_http import TrustedPrincipal


NOW = datetime(2026, 8, 30, 4, 45, tzinfo=timezone.utc)


class SessionAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "pilot.sqlite"
        self.store = SQLiteSessionStore(self.db_path)
        self.principal = TrustedPrincipal("tenant-a", "profile-a")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_issued_cookie_resolves_to_server_stored_principal(self) -> None:
        issued = issue_session(self.store, principal=self.principal, now=NOW)
        resolver = OpaqueCookiePrincipalResolver(self.store, now_provider=lambda: NOW)

        resolved = resolver.resolve({"Cookie": f"other=x; {SESSION_COOKIE_NAME}={issued.token}"})

        self.assertEqual(resolved, self.principal)
        self.assertIn("Secure", issued.set_cookie)
        self.assertIn("HttpOnly", issued.set_cookie)
        self.assertIn("SameSite=Strict", issued.set_cookie)
        self.assertNotIn("tenant-a", issued.set_cookie)
        self.assertNotIn("profile-a", issued.set_cookie)

    def test_raw_bearer_token_is_not_stored_in_database(self) -> None:
        issued = issue_session(self.store, principal=self.principal, now=NOW)
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT token_hash, tenant_id, profile_id FROM medical_sessions"
            ).fetchone()

        self.assertIsNotNone(row)
        token_hash, tenant_id, profile_id = row
        self.assertNotEqual(token_hash, issued.token)
        self.assertEqual(len(token_hash), 64)
        self.assertEqual((tenant_id, profile_id), ("tenant-a", "profile-a"))

    def test_tampered_cookie_does_not_resolve(self) -> None:
        issued = issue_session(self.store, principal=self.principal, now=NOW)
        replacement = "A" if issued.token[-1] != "A" else "B"
        tampered = issued.token[:-1] + replacement
        resolver = OpaqueCookiePrincipalResolver(self.store, now_provider=lambda: NOW)

        self.assertIsNone(resolver.resolve({"Cookie": f"{SESSION_COOKIE_NAME}={tampered}"}))

    def test_revoked_session_stops_resolving(self) -> None:
        issued = issue_session(self.store, principal=self.principal, now=NOW)
        resolver = OpaqueCookiePrincipalResolver(
            self.store,
            now_provider=lambda: NOW + timedelta(seconds=1),
        )
        self.assertTrue(revoke_session(self.store, issued.token, now=NOW))

        self.assertIsNone(resolver.resolve({"Cookie": f"{SESSION_COOKIE_NAME}={issued.token}"}))

    def test_expired_session_stops_resolving(self) -> None:
        issued = issue_session(
            self.store,
            principal=self.principal,
            now=NOW,
            ttl_seconds=300,
        )
        resolver = OpaqueCookiePrincipalResolver(
            self.store,
            now_provider=lambda: NOW + timedelta(seconds=301),
        )

        self.assertIsNone(resolver.resolve({"Cookie": f"{SESSION_COOKIE_NAME}={issued.token}"}))

    def test_duplicate_session_cookie_is_rejected(self) -> None:
        issued = issue_session(self.store, principal=self.principal, now=NOW)
        resolver = OpaqueCookiePrincipalResolver(self.store, now_provider=lambda: NOW)
        raw = (
            f"{SESSION_COOKIE_NAME}={issued.token}; "
            f"{SESSION_COOKIE_NAME}={issued.token}"
        )

        self.assertIsNone(resolver.resolve({"Cookie": raw}))


if __name__ == "__main__":
    unittest.main()
