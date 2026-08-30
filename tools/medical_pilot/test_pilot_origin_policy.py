from __future__ import annotations

from datetime import datetime, timezone
import unittest

from tools.medical_pilot.pilot_api import (
    CanonicalOriginPolicy,
    dispatch_pilot_api,
    enforce_origin_policy,
)
from tools.medical_pilot.pilot_server import build_origin_policy_from_env


class CanonicalOriginPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = CanonicalOriginPolicy.parse("https://Pilot.Example.com:443/")

    def test_canonical_origin_is_normalized(self) -> None:
        self.assertEqual(self.policy.origin, "https://pilot.example.com")
        self.assertEqual(self.policy.authority, "pilot.example.com")

    def test_canonical_origin_rejects_non_https_and_extra_url_parts(self) -> None:
        for value in (
            "http://pilot.example.com",
            "https://user@pilot.example.com",
            "https://pilot.example.com/path",
            "https://pilot.example.com?x=1",
            "https://pilot.example.com#fragment",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CanonicalOriginPolicy.parse(value)

    def test_server_env_requires_canonical_origin(self) -> None:
        with self.assertRaises(ValueError):
            build_origin_policy_from_env({})
        policy = build_origin_policy_from_env(
            {"MCAI_CANONICAL_ORIGIN": "https://pilot.example.com"}
        )
        self.assertEqual(policy.origin, "https://pilot.example.com")

    def test_get_requires_canonical_host_but_not_origin(self) -> None:
        accepted = enforce_origin_policy(
            method="GET",
            path="/today",
            headers={"Host": "PILOT.EXAMPLE.COM:443"},
            policy=self.policy,
        )
        self.assertIsNone(accepted)

        rejected = enforce_origin_policy(
            method="GET",
            path="/today",
            headers={"Host": "evil.example.com"},
            policy=self.policy,
        )
        self.assertIsNotNone(rejected)
        assert rejected is not None
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.json_body(), {"error": "FORBIDDEN"})

    def test_unsafe_method_requires_exact_canonical_origin(self) -> None:
        accepted = enforce_origin_policy(
            method="POST",
            path="/followup/opp-1",
            headers={
                "Host": "pilot.example.com",
                "Origin": "https://PILOT.EXAMPLE.COM:443",
            },
            policy=self.policy,
        )
        self.assertIsNone(accepted)

        for origin in (None, "https://evil.example.com", "https://sibling.qd.je"):
            headers = {"Host": "pilot.example.com"}
            if origin is not None:
                headers["Origin"] = origin
            rejected = enforce_origin_policy(
                method="POST",
                path="/followup/opp-1",
                headers=headers,
                policy=self.policy,
            )
            self.assertIsNotNone(rejected)
            assert rejected is not None
            self.assertEqual(rejected.status_code, 403)

    def test_loopback_exception_is_health_only(self) -> None:
        for host in ("127.0.0.1:8787", "localhost:8787", "[::1]:8787"):
            with self.subTest(host=host):
                accepted = enforce_origin_policy(
                    method="GET",
                    path="/healthz",
                    headers={"Host": host},
                    policy=self.policy,
                )
                self.assertIsNone(accepted)

                rejected = enforce_origin_policy(
                    method="GET",
                    path="/today",
                    headers={"Host": host},
                    policy=self.policy,
                )
                self.assertIsNotNone(rejected)
                assert rejected is not None
                self.assertEqual(rejected.status_code, 403)

    def test_loopback_health_does_not_allow_write_method(self) -> None:
        rejected = enforce_origin_policy(
            method="POST",
            path="/healthz",
            headers={"Host": "127.0.0.1:8787"},
            policy=self.policy,
        )
        self.assertIsNotNone(rejected)
        assert rejected is not None
        self.assertEqual(rejected.status_code, 403)

    def test_dispatch_health_accepts_loopback_and_rejects_wrong_external_host(self) -> None:
        now = datetime(2026, 8, 30, tzinfo=timezone.utc)
        ok = dispatch_pilot_api(
            None,  # health route must not touch business runtime
            method="GET",
            target="/api/healthz",
            headers={"Host": "127.0.0.1:8787"},
            body=b"",
            now=now,
            origin_policy=self.policy,
        )
        self.assertEqual(ok.status_code, 200)

        rejected = dispatch_pilot_api(
            None,
            method="GET",
            target="/api/healthz",
            headers={"Host": "evil.example.com"},
            body=b"",
            now=now,
            origin_policy=self.policy,
        )
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.json_body(), {"error": "FORBIDDEN"})


if __name__ == "__main__":
    unittest.main()
