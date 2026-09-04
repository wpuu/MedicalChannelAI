from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot
from medical_channel_pipeline.public_snapshot import _actionability, _public_score_components

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "tianjin_verified_seed.json"


class ProcurementIntentActionabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.seed = json.loads(SEED.read_text(encoding="utf-8"))[0]
        cls.as_of = datetime.fromisoformat("2026-09-04T12:00:00+08:00")

    def _facts(self, lifecycle: str) -> dict:
        facts = copy.deepcopy(self.seed["facts"])
        facts["lifecycle_state"] = lifecycle
        facts["registration_deadline"] = None
        facts["registration_deadline_date"] = None
        facts["bid_deadline"] = None
        return facts

    def test_procurement_intent_is_pre_market_signal_not_open_opportunity(self) -> None:
        mode, intervention, model_status = _actionability(
            self._facts("PROCUREMENT_INTENT"),
            self.as_of,
        )
        self.assertEqual(mode, "PRE_MARKET_SIGNAL")
        self.assertEqual(intervention, 12)
        self.assertEqual(model_status, "AWAITING_MODEL")

    def test_procurement_intent_without_deadline_has_no_fake_urgency(self) -> None:
        components = _public_score_components(
            self._facts("PROCUREMENT_INTENT"),
            self.as_of,
        )
        self.assertEqual(components["INTERVENTION_STAGE"], 12)
        self.assertEqual(components["DEADLINE_URGENCY"], 0)

    def test_market_research_without_deadline_keeps_existing_intervention_contract(self) -> None:
        mode, intervention, model_status = _actionability(
            self._facts("MARKET_RESEARCH"),
            self.as_of,
        )
        self.assertEqual(mode, "PUBLIC_OPPORTUNITY")
        self.assertEqual(intervention, 25)
        self.assertEqual(model_status, "AWAITING_MODEL")

    def test_procurement_intent_remains_visible_for_advance_layout(self) -> None:
        record = copy.deepcopy(self.seed)
        record["opportunity_id"] = "procurement_intent_actionability_contract"
        record["facts"]["project_number"] = "INTENT-CONTRACT-001"
        record["facts"]["project_name"] = "流式细胞仪等医疗设备采购意向公告"
        record["facts"]["lifecycle_state"] = "PROCUREMENT_INTENT"
        record["facts"]["registration_deadline"] = None
        record["facts"]["registration_deadline_date"] = None
        record["facts"]["bid_deadline"] = None
        record["facts"]["budget_cny"] = None
        record["facts"]["procurement_method"] = None
        record["facts"]["product_items"] = []
        record["facts"]["product_categories"] = []
        record["facts"]["department"] = None
        record["facts"]["public_contact"] = None

        # Keep evidence only for facts that remain populated. The lifecycle
        # evidence path is already part of the verified seed contract.
        populated = {
            f"facts.{key}"
            for key, value in record["facts"].items()
            if value not in (None, "", [], {})
        }
        record["evidence"] = [
            item for item in record["evidence"]
            if item["field_path"] in populated
        ]

        payload = build_public_snapshot([record], self.as_of)
        self.assertEqual(payload["opportunity_pool_count"], 1)
        card = payload["opportunity_pool"][0]
        self.assertEqual(card["recommendation_mode"], "PRE_MARKET_SIGNAL")
        components = {item["code"]: item["points"] for item in card["priority"]["components"]}
        self.assertEqual(components["INTERVENTION_STAGE"], 12)
        self.assertEqual(components["DEADLINE_URGENCY"], 0)
        self.assertIsNone(card["facts"]["registration_deadline"])
        self.assertIsNone(card["facts"]["registration_deadline_date"])
        self.assertIsNone(card["facts"]["bid_deadline"])


if __name__ == "__main__":
    unittest.main()
