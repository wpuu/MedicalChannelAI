from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from .session_auth import SESSION_COOKIE_NAME
from .test_opportunity_match_gate import complete_profile
from .today_actions_http import TrustedPrincipal
from .today_runtime import build_sqlite_today_runtime


NOW = datetime(2026, 8, 30, 13, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def cookie_pair(set_cookie: str) -> str:
    return set_cookie.split(";", 1)[0]


class AuthHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = build_sqlite_today_runtime(
            Path(self.tmp.name) / "pilot.sqlite",
            now_provider=lambda: NOW,
        )
        self.profile = complete_profile()
        self.runtime.repository.upsert_profile(self.profile)
        self.principal = TrustedPrincipal(
            self.profile["tenant_id"],
            self.profile["profile_id"],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def redeem(self, code: str, *, payload: dict | None = None):
        body = payload if payload is not None else {"code": code}
        return self.runtime.auth_transport.handle(
            method="POST",
            target="/auth/redeem",
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=json.dumps(body).encode("utf-8"),
            now=NOW,
        )

    def test_redeem_sets_http_only_session_without_client_tenant_identity(self) -> None:
        invite = self.runtime.issue_profile_invite(principal=self.principal, now=NOW)

        response = self.redeem(invite.code)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json_body(), {"authenticated": True})
        set_cookie = response.headers["Set-Cookie"]
        self.assertTrue(set_cookie.startswith(f"{SESSION_COOKIE_NAME}="))
        self.assertIn("Secure", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertNotIn(self.profile["tenant_id"], set_cookie)
        self.assertNotIn(self.profile["profile_id"], set_cookie)
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_redeem_body_cannot_override_tenant_or_profile(self) -> None:
        invite = self.runtime.issue_profile_invite(principal=self.principal, now=NOW)

        rejected = self.redeem(
            invite.code,
            payload={
                "code": invite.code,
                "tenant_id": "attacker",
                "profile_id": "attacker",
            },
        )
        accepted = self.redeem(invite.code)

        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(accepted.status_code, 200)

    def test_invite_replay_is_rejected(self) -> None:
        invite = self.runtime.issue_profile_invite(principal=self.principal, now=NOW)

        first = self.redeem(invite.code)
        replay = self.redeem(invite.code)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.json_body(), {"error": "INVITE_INVALID_OR_EXPIRED"})

    def test_logout_revokes_current_session_and_clears_cookie(self) -> None:
        invite = self.runtime.issue_profile_invite(principal=self.principal, now=NOW)
        redeemed = self.redeem(invite.code)
        cookie = cookie_pair(redeemed.headers["Set-Cookie"])
        before = self.runtime.transport.handle(
            method="GET",
            target="/today",
            headers={"Cookie": cookie},
            now=NOW,
        )

        logout = self.runtime.auth_transport.handle(
            method="POST",
            target="/auth/logout",
            headers={"Cookie": cookie},
            body=b"",
            now=NOW,
        )
        after = self.runtime.transport.handle(
            method="GET",
            target="/today",
            headers={"Cookie": cookie},
            now=NOW,
        )

        self.assertNotEqual(before.status_code, 401)
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(logout.json_body(), {"authenticated": False})
        self.assertIn("Max-Age=0", logout.headers["Set-Cookie"])
        self.assertEqual(after.status_code, 401)

    def test_redeem_requires_post_and_json(self) -> None:
        invite = self.runtime.issue_profile_invite(principal=self.principal, now=NOW)
        get_response = self.runtime.auth_transport.handle(
            method="GET",
            target="/auth/redeem",
            headers={},
            body=b"",
            now=NOW,
        )
        bad_content_type = self.runtime.auth_transport.handle(
            method="POST",
            target="/auth/redeem",
            headers={"Content-Type": "text/plain"},
            body=invite.code.encode("utf-8"),
            now=NOW,
        )

        self.assertEqual(get_response.status_code, 405)
        self.assertEqual(bad_content_type.status_code, 400)


if __name__ == "__main__":
    unittest.main()
