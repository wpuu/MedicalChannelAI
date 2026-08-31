from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import ValidationError, build_public_snapshot, validate_records

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "tianjin_verified_seed.json"


class EvidencePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = json.loads(SEED.read_text(encoding="utf-8"))

    def test_verified_seed_passes(self) -> None:
        self.assertEqual(len(validate_records(copy.deepcopy(self.records))), 5)

    def test_unsupported_critical_fact_is_rejected(self) -> None:
        record = copy.deepcopy(self.records[0])
        record["facts"]["department"] = "未经来源支持的科室"
        record["evidence"] = [
            item for item in record["evidence"] if item["field_path"] != "facts.department"
        ]
        with self.assertRaisesRegex(
            ValidationError, "UNSUPPORTED_CRITICAL_FACT:facts.department"
        ):
            validate_records([record])

    def test_non_ccgp_host_cannot_claim_ccgp_source(self) -> None:
        record = copy.deepcopy(self.records[0])
        record["source"]["url"] = "https://example.com/fake"
        for item in record["evidence"]:
            item["source_url"] = record["source"]["url"]
        with self.assertRaisesRegex(ValidationError, "CCGP_HOST_MISMATCH"):
            validate_records([record])

    def test_expired_registration_is_not_immediate_public_opportunity(self) -> None:
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat("2026-09-04T00:00:00+08:00"),
        )
        card = next(
            item
            for item in payload["cards"]
            if item["opportunity_id"] == "verified_xks_2026_a_641"
        )
        self.assertEqual(card["recommendation_mode"], "LATE_WINDOW")

    def test_public_snapshot_has_no_demo_customer_relationship(self) -> None:
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat("2026-08-31T16:42:00+08:00"),
        )
        for card in payload["cards"]:
            self.assertIsNone(card["customer_context"]["hospital_relationship"])
            self.assertEqual(
                card["customer_context"]["matching_product_capabilities"], []
            )


if __name__ == "__main__":
    unittest.main()
