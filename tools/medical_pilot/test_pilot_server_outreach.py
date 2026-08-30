from __future__ import annotations

import unittest

from tools.medical_pilot.outreach_client import AgnesOutreachClient
from tools.medical_pilot.pilot_server import build_outreach_model_call_from_env


class PilotServerOutreachConfigTests(unittest.TestCase):
    def test_missing_key_keeps_pilot_running_without_outreach_provider(self) -> None:
        self.assertIsNone(build_outreach_model_call_from_env({}))
        self.assertIsNone(build_outreach_model_call_from_env({"MCAI_AGNES_API_KEY": "   "}))

    def test_server_key_builds_official_agnes_outreach_client(self) -> None:
        client = build_outreach_model_call_from_env({"MCAI_AGNES_API_KEY": "server-secret"})
        self.assertIsInstance(client, AgnesOutreachClient)

    def test_unapproved_base_url_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_outreach_model_call_from_env(
                {
                    "MCAI_AGNES_API_KEY": "server-secret",
                    "MCAI_AGNES_BASE_URL": "https://example.invalid/v1",
                }
            )


if __name__ == "__main__":
    unittest.main()
