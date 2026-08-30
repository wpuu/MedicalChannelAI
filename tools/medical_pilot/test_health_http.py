from __future__ import annotations

import unittest

from tools.medical_pilot.health_http import handle_health_request


class HealthHttpTests(unittest.TestCase):
    def test_healthz_is_public_but_contains_no_runtime_identity(self) -> None:
        response = handle_health_request(method="GET", target="/healthz", body=b"")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json_body(),
            {"schema_version": "0.1", "status": "ok", "mode": "SINGLE_HOST_PILOT"},
        )
        encoded = response.body.decode("utf-8")
        for forbidden in ("tenant", "profile", "provider", "model", "api_key"):
            self.assertNotIn(forbidden, encoded.lower())

    def test_query_body_and_non_get_fail_closed(self) -> None:
        self.assertEqual(
            handle_health_request(method="GET", target="/healthz?verbose=1", body=b"").status_code,
            404,
        )
        self.assertEqual(
            handle_health_request(method="GET", target="/healthz", body=b"{}").status_code,
            400,
        )
        self.assertEqual(
            handle_health_request(method="POST", target="/healthz", body=b"").status_code,
            405,
        )


if __name__ == "__main__":
    unittest.main()
