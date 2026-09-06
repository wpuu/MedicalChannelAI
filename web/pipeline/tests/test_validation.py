from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import ValidationError, build_public_snapshot, validate_records
from medical_channel_pipeline.public_snapshot import _product_specificity_points

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
        record["evidence"] = [item for item in record["evidence"] if item["field_path"] != "facts.department"]
        with self.assertRaisesRegex(ValidationError, "UNSUPPORTED_CRITICAL_FACT:facts.department"):
            validate_records([record])

    def test_non_ccgp_host_cannot_claim_ccgp_source(self) -> None:
        record = copy.deepcopy(self.records[0])
        record["source"]["url"] = "https://example.com/fake"
        for item in record["evidence"]:
            item["source_url"] = record["source"]["url"]
        with self.assertRaisesRegex(ValidationError, "CCGP_HOST_MISMATCH"):
            validate_records([record])

    def test_expired_registration_is_not_immediate_public_opportunity(self) -> None:
        payload = build_public_snapshot(copy.deepcopy(self.records), datetime.fromisoformat("2026-09-04T00:00:00+08:00"))
        card = next(item for item in payload["cards"] if item["opportunity_id"] == "verified_xks_2026_a_641")
        self.assertEqual(card["recommendation_mode"], "LATE_WINDOW")

    def test_final_day_cutoff_uses_exact_official_time(self) -> None:
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat("2026-08-31T16:42:00+08:00"),
        )
        cdc = next(item for item in payload["cards"] if item["opportunity_id"] == "verified_bhcdc_2026_c_181")
        gpu = next(item for item in payload["cards"] if item["opportunity_id"] == "verified_hbrmyy_gpu_0052")
        self.assertEqual(cdc["recommendation_mode"], "LATE_WINDOW")
        self.assertEqual(gpu["recommendation_mode"], "PUBLIC_OPPORTUNITY")

    def test_source_category_conflict_is_preserved_but_not_rewarded(self) -> None:
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat("2026-08-31T16:42:00+08:00"),
        )
        card = next(item for item in payload["cards"] if item["opportunity_id"] == "verified_zybfy_2026_a_517")
        components = {item["code"]: item for item in card["priority"]["components"]}
        self.assertIn("SOURCE_CATEGORY_TITLE_CONFLICT", card["priority"]["warnings"])
        self.assertIn("SOURCE_CATEGORY_TITLE_CONFLICT", card["facts"]["quality_flags"])
        self.assertEqual(card["facts"]["product_categories"], ["医用磁共振设备"])
        self.assertEqual(components["PRODUCT_SPECIFICITY"]["points"], 5)

    def test_public_snapshot_has_no_demo_customer_relationship(self) -> None:
        payload = build_public_snapshot(copy.deepcopy(self.records), datetime.fromisoformat("2026-08-31T16:42:00+08:00"))
        for card in payload["cards"]:
            self.assertIsNone(card["customer_context"]["hospital_relationship"])
            self.assertEqual(card["customer_context"]["matching_product_capabilities"], [])

    def test_ranking_v2_public_score_contract(self) -> None:
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat("2026-08-31T16:42:00+08:00"),
        )
        expected_public_max = {
            "INTERVENTION_STAGE": 25,
            "DEADLINE_URGENCY": 10,
            "PROJECT_AMOUNT": 10,
            "PRODUCT_SPECIFICITY": 8,
            "PUBLICATION_FRESHNESS": 7,
        }
        expected_private_max = {
            "PRODUCT_EXECUTION_CAPABILITY": 25,
            "RELATIONSHIP": 10,
            "EXECUTION_FLEXIBILITY": 5,
        }
        for card in payload["cards"]:
            self.assertEqual(card["priority"]["score_type"], "ZERO_CONFIG_PUBLIC_FACTS_V2")
            components = {item["code"]: item for item in card["priority"]["components"]}
            for code, max_points in expected_public_max.items():
                self.assertEqual(components[code]["max_points"], max_points)
            for code, max_points in expected_private_max.items():
                self.assertEqual(components[code]["max_points"], max_points)
                self.assertEqual(components[code]["points"], 0)
            self.assertEqual(sum(expected_public_max.values()), 60)
            self.assertLessEqual(card["priority"]["score"], 60)
            self.assertEqual(
                card["priority"]["score"],
                sum(item["points"] for item in card["priority"]["components"]),
            )

    def test_ranking_v2_late_window_intervention_is_reduced(self) -> None:
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat("2026-09-04T00:00:00+08:00"),
        )
        card = next(item for item in payload["cards"] if item["opportunity_id"] == "verified_xks_2026_a_641")
        components = {item["code"]: item for item in card["priority"]["components"]}
        self.assertEqual(components["INTERVENTION_STAGE"]["max_points"], 25)
        self.assertEqual(components["INTERVENTION_STAGE"]["points"], 8)
        self.assertEqual(card["recommendation_mode"], "LATE_WINDOW")

    def test_product_specificity_uses_verified_specific_title_when_items_missing(self) -> None:
        facts = {
            "project_name": "天津市第五中心医院医疗设备更新项目-数字减影血管造影机采购项目",
            "product_items": [],
            "product_categories": [],
            "department": None,
            "procurement_method": "公开招标",
        }
        self.assertEqual(_product_specificity_points(facts), 5)

    def test_product_specificity_does_not_reward_conflicted_category(self) -> None:
        facts = {
            "project_name": "天津市职业病防治院采购X线移动业务用车项目",
            "product_items": [{"raw_name": "X线移动业务用车"}],
            "product_categories": ["医用磁共振设备"],
            "department": None,
            "procurement_method": "公开招标",
        }
        self.assertEqual(
            _product_specificity_points(facts, ["SOURCE_CATEGORY_TITLE_CONFLICT"]),
            5,
        )
        self.assertEqual(_product_specificity_points(facts), 7)

    def test_product_specificity_does_not_reward_generic_equipment_title(self) -> None:
        facts = {
            "project_name": "医疗设备更新项目",
            "product_items": [],
            "product_categories": [],
            "department": None,
            "procurement_method": "公开招标",
        }
        self.assertEqual(_product_specificity_points(facts), 1)

    def test_today_actions_exposes_all_actionable_count_but_only_top_five_cards(self) -> None:
        records = copy.deepcopy(self.records)
        extra = copy.deepcopy(self.records[0])
        extra["opportunity_id"] = "verified_extra_top5_guard"
        extra["facts"]["project_number"] = "TOP5-GUARD-006"
        extra["facts"]["budget_cny"] = 0
        records.append(extra)

        payload = build_public_snapshot(
            records,
            datetime.fromisoformat("2026-08-28T12:00:00+08:00"),
        )
        self.assertEqual(payload["matched_count"], 6)
        self.assertEqual(payload["card_count"], 5)
        self.assertEqual(payload["opportunity_pool_count"], 6)
        self.assertEqual(len(payload["cards"]), 5)
        self.assertEqual(len(payload["opportunity_pool"]), 6)
        self.assertEqual([item["rank"] for item in payload["cards"]], [1, 2, 3, 4, 5])
        self.assertNotIn(
            "verified_extra_top5_guard",
            {item["opportunity_id"] for item in payload["cards"]},
        )
        self.assertIn(
            "verified_extra_top5_guard",
            {item["opportunity_id"] for item in payload["opportunity_pool"]},
        )


if __name__ == "__main__":
    unittest.main()
