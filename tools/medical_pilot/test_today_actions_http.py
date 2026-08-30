from __future__ import annotations

from datetime import datetime, timezone
import unittest

from .today_actions_api import TodayActionsApiResponse
from .today_actions_http import (
    TodayActionsHttpTransport,
    TrustedPrincipal,
)


NOW = datetime(2026, 8, 30, 4, 30, tzinfo=timezone.utc)


class StaticResolver:
    def __init__(self, principal: TrustedPrincipal | None) -> None:
        self.principal = principal
        self.seen_headers = None

    def resolve(self, headers):
        self.seen_headers = dict(headers)
        return self.principal


class FakeApplication:
    def __init__(self) -> None:
        self.calls = []
        self.raise_error: Exception | None = None

    def get_today(self, principal, now):
        self.calls.append(("today", principal, now))
        if self.raise_error:
            raise self.raise_error
        return TodayActionsApiResponse(
            200,
            {
                "schema_version": "0.1",
                "mode": "TODAY_ACTIONS",
                "cards": [],
            },
        )

    def get_opportunity(self, principal, opportunity_id, now):
        self.calls.append(("opportunity", principal, opportunity_id, now))
        if self.raise_error:
            raise self.raise_error
        return TodayActionsApiResponse(
            200,
            {"opportunity_id": opportunity_id},
        )


class TodayActionsHttpTransportTests(unittest.TestCase):
    def test_unauthenticated_request_never_calls_application(self):
        resolver = StaticResolver(None)
        application = FakeApplication()
        transport = TodayActionsHttpTransport(
            principal_resolver=resolver,
            application=application,
        )

        response = transport.handle(
            method="GET",
            target="/today?tenant_id=attacker&profile_id=attacker",
            headers={"X-Tenant-Id": "attacker", "X-Profile-Id": "attacker"},
            now=NOW,
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json_body(), {"error": "UNAUTHORIZED"})
        self.assertEqual(application.calls, [])

    def test_today_uses_only_trusted_principal_from_resolver(self):
        principal = TrustedPrincipal("tenant_real", "profile_real")
        resolver = StaticResolver(principal)
        application = FakeApplication()
        transport = TodayActionsHttpTransport(
            principal_resolver=resolver,
            application=application,
        )

        response = transport.handle(
            method="GET",
            target="/today?tenant_id=attacker&profile_id=attacker",
            headers={"X-Tenant-Id": "attacker", "X-Profile-Id": "attacker"},
            now=NOW,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(application.calls[0], ("today", principal, NOW))
        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_opportunity_route_decodes_one_safe_path_segment(self):
        principal = TrustedPrincipal("tenant_real", "profile_real")
        application = FakeApplication()
        transport = TodayActionsHttpTransport(
            principal_resolver=StaticResolver(principal),
            application=application,
        )

        response = transport.handle(
            method="GET",
            target="/opportunity/opp_abc-123",
            headers={},
            now=NOW,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            application.calls[0],
            ("opportunity", principal, "opp_abc-123", NOW),
        )

    def test_encoded_slash_is_rejected_as_route_not_found(self):
        principal = TrustedPrincipal("tenant_real", "profile_real")
        application = FakeApplication()
        transport = TodayActionsHttpTransport(
            principal_resolver=StaticResolver(principal),
            application=application,
        )

        response = transport.handle(
            method="GET",
            target="/opportunity/opp_a%2Fb",
            headers={},
            now=NOW,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(application.calls, [])

    def test_non_get_is_rejected_before_auth_or_application(self):
        resolver = StaticResolver(TrustedPrincipal("tenant_real", "profile_real"))
        application = FakeApplication()
        transport = TodayActionsHttpTransport(
            principal_resolver=resolver,
            application=application,
        )

        response = transport.handle(
            method="POST",
            target="/today",
            headers={},
            now=NOW,
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers["Allow"], "GET")
        self.assertIsNone(resolver.seen_headers)
        self.assertEqual(application.calls, [])

    def test_internal_runtime_error_is_sanitized(self):
        application = FakeApplication()
        application.raise_error = RuntimeError("secret provider payload")
        transport = TodayActionsHttpTransport(
            principal_resolver=StaticResolver(TrustedPrincipal("tenant_real", "profile_real")),
            application=application,
        )

        response = transport.handle(
            method="GET",
            target="/today",
            headers={},
            now=NOW,
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json_body(), {"error": "INTERNAL_RESPONSE_REJECTED"})
        self.assertNotIn(b"secret provider payload", response.body)


if __name__ == "__main__":
    unittest.main()
