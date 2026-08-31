from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.pilot_host_acceptance import (
    PilotHostAcceptanceError,
    load_acceptance_manifest,
    run_host_acceptance,
)


ATTACHMENT_URL = (
    "https://www.ccgp-tianjin.gov.cn/portal/documentView.do"
    "?id=1OQ5vSM9GqM%2A&method=downEnId"
)


def write_manifest(root: Path, *, attachment_url: str = ATTACHMENT_URL) -> Path:
    deploy = root / "deploy"
    deploy.mkdir(parents=True, exist_ok=True)
    path = deploy / "pilot-host-acceptance-v0.1.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "purpose": "test acceptance",
                "bootstrap_manifest": "deploy/tianjin-pilot-bootstrap-urls-2026-08-30.json",
                "attachment": {
                    "project_code": "XCSD-2026-C-181",
                    "filename": "XCSD-2026-C-181项目需求书.docx",
                    "url": attachment_url,
                },
                "required_environment": ["MCAI_CANONICAL_ORIGIN", "MCAI_AGNES_API_KEY"],
                "acceptance_requires": {
                    "official_bootstrap_success_count": 5,
                    "official_bootstrap_failure_count": 0,
                    "attachment_binary_capture": True,
                    "attachment_parser_pass": True,
                    "agnes_authenticated_contract_smoke": True,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


class PilotHostAcceptanceTests(unittest.TestCase):
    def test_manifest_accepts_only_frozen_official_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_manifest(Path(temp_dir))
            manifest = load_acceptance_manifest(path)
        self.assertEqual(manifest.expected_bootstrap_success_count, 5)
        self.assertEqual(manifest.attachment_project_code, "XCSD-2026-C-181")
        self.assertEqual(manifest.attachment_url, ATTACHMENT_URL)

    def test_manifest_rejects_unapproved_attachment_host(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_manifest(
                Path(temp_dir),
                attachment_url="https://example.com/portal/documentView.do?id=x&method=downEnId",
            )
            with self.assertRaises(PilotHostAcceptanceError) as context:
                load_acceptance_manifest(path)
        self.assertEqual(context.exception.code, "ACCEPTANCE_ATTACHMENT_NOT_ALLOWED")

    def test_full_acceptance_passes_without_touching_production_data_or_exposing_key(self) -> None:
        calls = {"bootstrap": 0, "attachment": 0, "provider": 0}

        def bootstrap_runner(*, db_path, manifest_path):
            calls["bootstrap"] += 1
            self.assertIn("mcai-pilot-host-acceptance-", str(db_path))
            self.assertTrue(str(manifest_path).endswith("deploy/tianjin-pilot-bootstrap-urls-2026-08-30.json"))
            return 0, {
                "success_count": 5,
                "failure_count": 0,
                "results": [
                    {
                        "expected_project_code": f"P{i}",
                        "status": "OK",
                        "verification_status": "VERIFIED",
                        "lifecycle_state": "TENDERING",
                        "product_labels": ["LAB_NGS_SEQUENCER"],
                    }
                    for i in range(5)
                ],
            }

        def attachment_runner(*, url, filename):
            calls["attachment"] += 1
            self.assertEqual(url, ATTACHMENT_URL)
            self.assertTrue(filename.endswith(".docx"))
            return {
                "status_code": 200,
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size_bytes": 12345,
                "sha256": "a" * 64,
                "parser_version": "ooxml-v0.1",
                "block_count": 12,
                "taxonomy_validation_status": "VALIDATED",
                "taxonomy_labels": ["LAB_NGS_SEQUENCER"],
            }

        def provider_runner(*, api_key, base_url, lease_db_path):
            calls["provider"] += 1
            self.assertEqual(api_key, "super-secret-test-key")
            self.assertEqual(base_url, "https://apihub.agnes-ai.com/v1")
            self.assertIn("mcai-pilot-host-acceptance-", str(lease_db_path))
            return {
                "status": "PASS",
                "provider_call_executed": True,
                "contract_validation_passed": True,
                "lease_status": "GRANTED",
                "action_type": "MONITOR",
                "supporting_fact_count": 1,
                "requires_human_confirmation": True,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_manifest(Path(temp_dir))
            result = run_host_acceptance(
                manifest_path=path,
                environ={
                    "MCAI_CANONICAL_ORIGIN": "https://pilot.example.com",
                    "MCAI_AGNES_API_KEY": "super-secret-test-key",
                },
                bootstrap_runner=bootstrap_runner,
                attachment_runner=attachment_runner,
                provider_runner=provider_runner,
            )

        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["production_data_touched"])
        self.assertEqual(calls, {"bootstrap": 1, "attachment": 1, "provider": 1})
        self.assertNotIn("super-secret-test-key", json.dumps(result, ensure_ascii=False))

    def test_missing_key_fails_before_any_network_stage(self) -> None:
        calls = []

        def forbidden_runner(**kwargs):
            calls.append(kwargs)
            raise AssertionError("network stage must not run")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_manifest(Path(temp_dir))
            result = run_host_acceptance(
                manifest_path=path,
                environ={"MCAI_CANONICAL_ORIGIN": "https://pilot.example.com"},
                bootstrap_runner=forbidden_runner,
                attachment_runner=forbidden_runner,
                provider_runner=forbidden_runner,
            )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["environment"]["error_class"], "MCAI_AGNES_API_KEY_MISSING")
        self.assertEqual(result["official_bootstrap"]["status"], "SKIPPED")
        self.assertEqual(calls, [])

    def test_one_failed_stage_keeps_other_isolated_diagnostics_and_overall_fail(self) -> None:
        def bootstrap_runner(**kwargs):
            return 0, {"success_count": 5, "failure_count": 0, "results": []}

        def attachment_runner(**kwargs):
            raise TimeoutError("must not be serialized")

        def provider_runner(**kwargs):
            return {
                "status": "PASS",
                "provider_call_executed": True,
                "contract_validation_passed": True,
                "lease_status": "GRANTED",
                "action_type": "NO_ACTION",
                "supporting_fact_count": 1,
                "requires_human_confirmation": True,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_manifest(Path(temp_dir))
            result = run_host_acceptance(
                manifest_path=path,
                environ={
                    "MCAI_CANONICAL_ORIGIN": "https://pilot.example.com",
                    "MCAI_AGNES_API_KEY": "secret",
                },
                bootstrap_runner=bootstrap_runner,
                attachment_runner=attachment_runner,
                provider_runner=provider_runner,
            )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["official_bootstrap"]["status"], "PASS")
        self.assertEqual(result["attachment"]["status"], "FAIL")
        self.assertEqual(result["attachment"]["error_class"], "TimeoutError")
        self.assertEqual(result["agnes_provider"]["status"], "PASS")
        self.assertNotIn("must not be serialized", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
