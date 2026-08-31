from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.medical_pilot.pilot_host_preflight import run_preflight


class PilotHostPreflightTests(unittest.TestCase):
    def _db_path(self, root: str) -> Path:
        return Path(root) / "pilot.sqlite"

    def test_api_role_requires_valid_canonical_https_origin(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            missing = run_preflight(role="api", db_path=self._db_path(root), environ={})
            self.assertEqual(missing["status"], "FAIL")
            self.assertIn(
                "CANONICAL_ORIGIN_MISSING",
                [item.get("error_code") for item in missing["checks"]],
            )

            invalid = run_preflight(
                role="api",
                db_path=self._db_path(root),
                environ={"MCAI_CANONICAL_ORIGIN": "http://pilot.example.com"},
            )
            self.assertEqual(invalid["status"], "FAIL")
            self.assertIn(
                "CANONICAL_ORIGIN_INVALID",
                [item.get("error_code") for item in invalid["checks"]],
            )

            valid = run_preflight(
                role="api",
                db_path=self._db_path(root),
                environ={"MCAI_CANONICAL_ORIGIN": "https://pilot.example.com"},
            )
            self.assertEqual(valid["status"], "PASS")

    def test_worker_role_requires_key_and_allowlisted_base_url(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            missing = run_preflight(role="worker", db_path=self._db_path(root), environ={})
            self.assertEqual(missing["status"], "FAIL")
            self.assertIn(
                "AGNES_API_KEY_MISSING",
                [item.get("error_code") for item in missing["checks"]],
            )

            invalid = run_preflight(
                role="worker",
                db_path=self._db_path(root),
                environ={
                    "MCAI_AGNES_API_KEY": "server-only-test-key",
                    "MCAI_AGNES_BASE_URL": "https://example.com/v1",
                },
            )
            self.assertEqual(invalid["status"], "FAIL")
            self.assertIn(
                "AGNES_BASE_URL_INVALID",
                [item.get("error_code") for item in invalid["checks"]],
            )

            valid = run_preflight(
                role="worker",
                db_path=self._db_path(root),
                environ={"MCAI_AGNES_API_KEY": "server-only-test-key"},
            )
            self.assertEqual(valid["status"], "PASS")

    def test_all_role_requires_both_api_and_worker_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = run_preflight(
                role="all",
                db_path=self._db_path(root),
                environ={
                    "MCAI_CANONICAL_ORIGIN": "https://pilot.example.com",
                    "MCAI_AGNES_API_KEY": "server-only-test-key",
                },
            )
            self.assertEqual(result["status"], "PASS")
            ids = {item["check_id"] for item in result["checks"]}
            self.assertIn("canonical_origin", ids)
            self.assertIn("agnes_api_key", ids)
            self.assertIn("agnes_base_url", ids)

    def test_database_path_must_be_absolute_and_parent_must_exist(self) -> None:
        relative = run_preflight(
            role="worker",
            db_path=Path("pilot.sqlite"),
            environ={"MCAI_AGNES_API_KEY": "server-only-test-key"},
        )
        self.assertEqual(relative["status"], "FAIL")
        self.assertIn(
            "DATABASE_PATH_MUST_BE_ABSOLUTE",
            [item.get("error_code") for item in relative["checks"]],
        )

        with tempfile.TemporaryDirectory() as root:
            missing_parent = run_preflight(
                role="worker",
                db_path=Path(root) / "missing" / "pilot.sqlite",
                environ={"MCAI_AGNES_API_KEY": "server-only-test-key"},
            )
            self.assertEqual(missing_parent["status"], "FAIL")
            self.assertIn(
                "DATABASE_PARENT_MISSING",
                [item.get("error_code") for item in missing_parent["checks"]],
            )

    def test_safe_result_never_echoes_environment_values(self) -> None:
        secret = "top-secret-never-echo"
        origin = "https://private-pilot.example.com"
        with tempfile.TemporaryDirectory() as root:
            result = run_preflight(
                role="all",
                db_path=self._db_path(root),
                environ={
                    "MCAI_CANONICAL_ORIGIN": origin,
                    "MCAI_AGNES_API_KEY": secret,
                },
            )
            rendered = repr(result)
            self.assertNotIn(secret, rendered)
            self.assertNotIn(origin, rendered)
            self.assertFalse(result["secrets_echoed"])


if __name__ == "__main__":
    unittest.main()
