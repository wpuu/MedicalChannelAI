from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "docs/research/fixtures"
ATTACHMENT_FIXTURES = FIXTURE_DIR / "tianjin-attachment-cases-v0.1.json"
OPPORTUNITY_FIXTURE_FILES = (
    FIXTURE_DIR / "tianjin-opportunity-cases-v0.1.json",
    FIXTURE_DIR / "tianjin-opportunity-attachment-backed-cases-v0.1.json",
    FIXTURE_DIR / "tianjin-procurement-intent-identity-cases-v0.1.json",
    FIXTURE_DIR / "tianjin-expanded-opportunity-cases-v0.1.json",
)


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


class ResearchFixtureContractTests(unittest.TestCase):
    def test_opportunity_fixture_ids_are_unique_across_all_files_and_verified_cases_have_source_urls(self) -> None:
        cases: list[dict] = []
        for path in OPPORTUNITY_FIXTURE_FILES:
            cases.extend(load_cases(path))
        ids = [case["case_id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(cases), 20)
        for case in cases:
            self.assertTrue(case["source_url"].startswith("https://"), case["case_id"])
            expected = case.get("expected", {})
            self.assertEqual(expected.get("verification_status"), "VERIFIED", case["case_id"])

    def test_procurement_intent_fixtures_with_native_record_id_use_valid_uuid_shape(self) -> None:
        cases: list[dict] = []
        for path in OPPORTUNITY_FIXTURE_FILES:
            cases.extend(load_cases(path))
        native_ids = [case["native_record_id"] for case in cases if case.get("native_record_id")]
        self.assertGreaterEqual(len(native_ids), 5)
        for native_record_id in native_ids:
            parts = native_record_id.split("-")
            self.assertEqual([len(part) for part in parts], [8, 4, 4, 4, 12], native_record_id)
            int(native_record_id.replace("-", ""), 16)

    def test_same_name_procurement_intent_fixture_pair_requires_distinct_native_identity(self) -> None:
        path = FIXTURE_DIR / "tianjin-procurement-intent-identity-cases-v0.1.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases = payload["cases"]
        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0]["expected"]["buyer_name"], cases[1]["expected"]["buyer_name"])
        self.assertEqual(cases[0]["expected"]["project_name"], cases[1]["expected"]["project_name"])
        self.assertNotEqual(cases[0]["native_record_id"], cases[1]["native_record_id"])
        self.assertNotEqual(
            cases[0]["expected"]["budget_amount_cny"],
            cases[1]["expected"]["budget_amount_cny"],
        )
        self.assertTrue(payload["pair_regression"]["must_have_distinct_canonical_project_id"])
        self.assertTrue(payload["pair_regression"]["must_have_distinct_opportunity_id"])

    def test_attachment_declarations_never_claim_real_parser_success_without_binary(self) -> None:
        cases = load_cases(ATTACHMENT_FIXTURES)
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
        cases = load_cases(ATTACHMENT_FIXTURES)
        for case in cases:
            attachment = case["attachment"]
            extension = attachment["extension"]
            if extension in {".docx", ".xlsx"}:
                self.assertEqual(attachment["local_parser_status"], "IMPLEMENTED", case["case_id"])
                self.assertEqual(attachment["expected_parser"], "ooxml-stdlib-v0.1", case["case_id"])
            elif extension in {".pdf", ".doc", ".xls"}:
                self.assertEqual(attachment["local_parser_status"], "PARSER_PENDING", case["case_id"])

    def test_nonmedical_format_fixture_is_not_counted_as_medical_opportunity(self) -> None:
        cases = load_cases(ATTACHMENT_FIXTURES)
        xlsx_cases = [case for case in cases if case["attachment"]["extension"] == ".xlsx"]
        self.assertTrue(xlsx_cases)
        for case in xlsx_cases:
            if case["case_id"] == "tianjin_database_framework_award_xlsx_20260313":
                self.assertFalse(case["medical_opportunity"])


if __name__ == "__main__":
    unittest.main()
