from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.account_auth import (
    ACCOUNT_ACTIVE,
    ACCOUNT_DISABLED,
    ACCOUNT_INVITED,
    AccountAwarePrincipalResolver,
    SQLiteAccountStore,
)
from tools.medical_pilot.session_auth import (
    OpaqueCookiePrincipalResolver,
    SESSION_COOKIE_NAME,
    SQLiteSessionStore,
    issue_session,
)
from tools.medical_pilot.today_actions_http import TrustedPrincipal


NOW = datetime(2026, 8, 31, 0, 10, tzinfo=timezone.utc)


class AccountAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "pilot.sqlite"
        self.accounts = SQLiteAccountStore(self.db_path)
        self.sessions = SQLiteSessionStore(self.db_path)
        self.principal = TrustedPrincipal("tenant-a", "mprof_11111111-1111-1111-1111-111111111111")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_new_account_starts_invited_and_first_login_activates(self) -> None:
        account = self.accounts.ensure_invited(
            principal=self.principal,
            company_name="天津试用客户",
            now=NOW,
        )
        self.assertEqual(account.status, ACCOUNT_INVITED)
        self.assertIsNone(account.activated_at)

        self.assertTrue(self.accounts.activate_login(self.principal, now=NOW + timedelta(seconds=1)))
        active = self.accounts.get(self.principal)
        self.assertIsNotNone(active)
        self.assertEqual(active.status, ACCOUNT_ACTIVE)
        self.assertIsNotNone(active.activated_at)
        self.assertIsNotNone(active.last_login_at)

    def test_disabled_account_immediately_invalidates_existing_session(self) -> None:
        self.accounts.ensure_invited(
            principal=self.principal,
            company_name="天津试用客户",
            now=NOW,
        )
        self.assertTrue(self.accounts.activate_login(self.principal, now=NOW))
        issued = issue_session(self.sessions, principal=self.principal, now=NOW)
        base = OpaqueCookiePrincipalResolver(self.sessions, now_provider=lambda: NOW + timedelta(seconds=2))
        resolver = AccountAwarePrincipalResolver(base, self.accounts)
        headers = {"Cookie": f"{SESSION_COOKIE_NAME}={issued.token}"}
        self.assertEqual(resolver.resolve(headers), self.principal)

        self.assertTrue(
            self.accounts.set_disabled(
                self.principal,
                disabled=True,
                now=NOW + timedelta(seconds=3),
            )
        )
        disabled = self.accounts.get(self.principal)
        self.assertIsNotNone(disabled)
        self.assertEqual(disabled.status, ACCOUNT_DISABLED)
        self.assertIsNone(resolver.resolve(headers))

    def test_reenabled_account_restores_account_gate_for_unexpired_session(self) -> None:
        self.accounts.ensure_invited(
            principal=self.principal,
            company_name="天津试用客户",
            now=NOW,
        )
        self.accounts.activate_login(self.principal, now=NOW)
        issued = issue_session(self.sessions, principal=self.principal, now=NOW)
        resolver = AccountAwarePrincipalResolver(
            OpaqueCookiePrincipalResolver(self.sessions, now_provider=lambda: NOW + timedelta(seconds=5)),
            self.accounts,
        )
        headers = {"Cookie": f"{SESSION_COOKIE_NAME}={issued.token}"}
        self.accounts.set_disabled(self.principal, disabled=True, now=NOW + timedelta(seconds=1))
        self.assertIsNone(resolver.resolve(headers))

        self.accounts.set_disabled(self.principal, disabled=False, now=NOW + timedelta(seconds=2))
        self.assertEqual(self.accounts.get(self.principal).status, ACCOUNT_ACTIVE)
        self.assertEqual(resolver.resolve(headers), self.principal)

    def test_invited_account_does_not_authorize_session_until_activation(self) -> None:
        self.accounts.ensure_invited(
            principal=self.principal,
            company_name="天津试用客户",
            now=NOW,
        )
        issued = issue_session(self.sessions, principal=self.principal, now=NOW)
        resolver = AccountAwarePrincipalResolver(
            OpaqueCookiePrincipalResolver(self.sessions, now_provider=lambda: NOW),
            self.accounts,
        )
        headers = {"Cookie": f"{SESSION_COOKIE_NAME}={issued.token}"}
        self.assertIsNone(resolver.resolve(headers))


if __name__ == "__main__":
    unittest.main()
