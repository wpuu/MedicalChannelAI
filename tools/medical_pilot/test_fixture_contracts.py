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
    FIXTURE_DIR / "tianjin-expanded-opportunity-cases-v0.2.json",
    FIXTURE_DIR / "tianjin-expanded-opportunity-cases-v0.3.json",
)


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def all_opportunity_cases() -> list[dict]:
    cases: list[dict] = []
    for path in OPPORTUNITY_FIXTURE_FILES:
        cases.extend(load_cases(path))
    return cases


class ResearchFixtureContractTests(unittest.TestCase):
    def test_opportunity_fixture_ids_are_unique_and_all_cases_are_verified_official_records(self) -> None:
        cases = all_opportunity_cases()
        ids = [case["case_id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(cases), 50)
        for case in cases:
            self.assertTrue(case["source_url"].startswith("https://"), case["case_id"])
            expected = case.get("expected", {})
            self.assertEqual(expected.get("verification_status"), "VERIFIED", case["case_id"])
            self.assertTrue(case.get("forbidden_inference"), case["case_id"])

    def test_procurement_intent_fixtures_with_native_record_id_use_valid_uuid_shape(self) -> None:
        cases = all_opportunity_cases()
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
        self.assertNotEqual(cases[0]["expected"]["budget_amount_cny"], cases[1]["expected"]["budget_amount_cny"])
        self.assertTrue(payload["pair_regression"]["must_have_distinct_canonical_project_id"])
        self.assertTrue(payload["pair_regression"]["must_have_distinct_opportunity_id"])

    def test_multi_item_market_research_pages_are_not_split_into_fake_fixture_counts(self) -> None:
        for filename, case_ids in {
            "tianjin-expanded-opportunity-cases-v0.2.json": {
                "tjmugh_imaging_ultrasound_maintenance_market_research_20260508",
                "tjmugh_repair_services_market_research_20260205",
                "tjmugh_rehab_neuro_devices_market_research_20260529",
            },
            "tianjin-expanded-opportunity-cases-v0.3.json": {
                "tjmugh_aug5_medical_equipment_market_research_20260805",
            },
        }.items():
            cases = {case["case_id"]: case for case in load_cases(FIXTURE_DIR / filename)}
            for case_id in case_ids:
                case = cases[case_id]
                self.assertEqual(case["expected"]["notice_type"], "MARKET_RESEARCH")
                self.assertEqual(case["expected"]["lifecycle_state"], "MARKET_RESEARCH")
                self.assertNotIn("sub_opportunities", case)

    def test_maintenance_market_research_never_claims_equipment_purchase_award(self) -> None:
        maintenance_cases: list[dict] = []
        for filename, case_ids in {
            "tianjin-expanded-opportunity-cases-v0.2.json": {
                "tjmugh_imaging_ultrasound_maintenance_market_research_20260508",
                "tjmugh_repair_services_market_research_20260205",
            },
            "tianjin-expanded-opportunity-cases-v0.3.json": {
                "tjmugh_jan23_repair_market_research_20260123",
            },
        }.items():
            cases = {case["case_id"]: case for case in load_cases(FIXTURE_DIR / filename)}
            maintenance_cases.extend(cases[case_id] for case_id in case_ids)
        for case in maintenance_cases:
            expected = case["expected"]
            self.assertEqual(expected["notice_type"], "MARKET_RESEARCH")
            self.assertNotIn("award_total_cny", expected)
            self.assertNotIn("budget_amount_cny", expected)

    def test_index_only_result_evidence_does_not_lock_unavailable_amount_or_supplier(self) -> None:
        cases = {
            case["case_id"]: case
            for case in load_cases(FIXTURE_DIR / "tianjin-expanded-opportunity-cases-v0.3.json")
        }
        for case_id in {
            "first_central_endoscope_cleaner_award_20260420",
            "first_central_microscope_camera_award_20260615",
        }:
            case = cases[case_id]
            expected = case["expected"]
            self.assertEqual(expected["notice_type"], "AWARD")
            self.assertEqual(expected["lifecycle_state"], "AWARDED")
            self.assertNotIn("award_total_cny", expected)
            self.assertNotIn("official_supplier", case)
            evidence_note = case["source_evidence_note"].lower()
            self.assertTrue(
                "unavailable" in evidence_note or "not available" in evidence_note,
                case_id,
            )

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
                self.assertEqual(attachment["parser_validation_status"], "NOT_RUN_ON_REAL_BYTES", case["case_id"])

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
