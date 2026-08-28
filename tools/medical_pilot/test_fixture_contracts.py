from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OPPORTUNITY_FIXTURES = REPO_ROOT / "docs/research/fixtures/tianjin-opportunity-cases-v0.1.json"
ATTACHMENT_FIXTURES = REPO_ROOT / "docs/research/fixtures/tianjin-attachment-cases-v0.1.json"


class ResearchFixtureContractTests(unittest.TestCase):
    def test_opportunity_fixture_ids_are_unique_and_verified_cases_have_source_urls(self) -> None:
        payload = json.loads(OPPORTUNITY_FIXTURES.read_text(encoding="utf-8"))
        cases = payload["cases"]
        ids = [case["case_id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases:
            self.assertTrue(case["source_url"].startswith("https://"), case["case_id"])
            expected = case.get("expected", {})
            self.assertEqual(expected.get("verification_status"), "VERIFIED", case["case_id"])

    def test_attachment_declarations_never_claim_real_parser_success_without_binary(self) -> None:
        payload = json.loads(ATTACHMENT_FIXTURES.read_text(encoding="utf-8"))
        cases = payload["cases"]
        ids = [case["case_id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases:
            attachment = case["attachment"]
            self.assertEqual(case["verification_status"], "VERIFIED_ATTACHMENT_DECLARATION")
            self.assertTrue(case["notice_url"].startswith("https://"), case["case_id"])
            if attachment["binary_capture_status"] == "PENDING_DIRECT_ATTACHMENT_BYTES":
                self.assertIsNone(attachment["sha256"], case["case_id"])
                self.assertEqual(
                    attachment["parser_validation_status"],
                    "NOT_RUN_ON_REAL_BYTES",
                    case["case_id"],
                )

    def test_parser_status_matches_current_extension_support(self) -> None:
        payload = json.loads(ATTACHMENT_FIXTURES.read_text(encoding="utf-8"))
        for case in payload["cases"]:
            attachment = case["attachment"]
            extension = attachment["extension"]
            if extension in {".docx", ".xlsx"}:
                self.assertEqual(attachment["local_parser_status"], "IMPLEMENTED", case["case_id"])
                self.assertEqual(attachment["expected_parser"], "ooxml-stdlib-v0.1", case["case_id"])
            elif extension in {".pdf", ".doc", ".xls"}:
                self.assertEqual(attachment["local_parser_status"], "PARSER_PENDING", case["case_id"])

    def test_nonmedical_format_fixture_is_not_counted_as_medical_opportunity(self) -> None:
        payload = json.loads(ATTACHMENT_FIXTURES.read_text(encoding="utf-8"))
        xlsx_cases = [case for case in payload["cases"] if case["attachment"]["extension"] == ".xlsx"]
        self.assertTrue(xlsx_cases)
        for case in xlsx_cases:
            if case["case_id"] == "tianjin_database_framework_award_xlsx_20260313":
                self.assertFalse(case["medical_opportunity"])


if __name__ == "__main__":
    unittest.main()
