from __future__ import annotations

import unittest

from tools.medical_pilot.customer_profile_gate import evaluate_customer_profile


def base_profile() -> dict:
    return {
        "schema_version": "0.1",
        "profile_id": "mprof_11111111-1111-1111-1111-111111111111",
        "tenant_id": "tenant-demo",
        "company_name": "天津测试医疗渠道公司",
        "business_role": "LOCAL_DISTRIBUTOR",
        "operating_regions": [
            {
                "province": "天津市",
                "city": "天津市",
                "scope_mode": "ENTIRE_CITY",
                "districts": [],
            }
        ],
        "customer_types": ["TERTIARY_HOSPITAL", "SECONDARY_HOSPITAL", "CDC"],
        "product_capabilities": [
            {
                "category": "体外诊断",
                "subcategory": "化学发光",
                "brands": ["测试品牌"],
                "capability_type": "DIRECT_AUTHORIZED",
                "notes": None,
            }
        ],
        "partnering_policy": {
            "can_seek_temporary_manufacturer": True,
            "can_cooperate_with_channel_partner": True,
            "can_do_rental_projects": False,
        },
        "opportunity_thresholds": {
            "minimum_project_amount_cny": "100000.00",
            "owner_attention_amount_cny": "3000000.00",
            "preferred_stages": ["MARKET_RESEARCH", "PROCUREMENT_INTENT", "TENDERING"],
        },
        "exclusion_rules": [],
        "hospital_relationships": [],
        "confirmation_flags": {
            "region_scope_confirmed": True,
            "customer_types_confirmed": True,
            "product_capabilities_confirmed": True,
            "partnering_policy_confirmed": True,
            "opportunity_preferences_confirmed": True,
            "exclusion_rules_confirmed": True,
        },
        "profile_status": "INCOMPLETE",
        "profile_completeness": 0,
        "missing_required_conditions": ["stale-front-end-value"],
        "updated_at": "2026-08-28T19:00:00+08:00",
    }


class CustomerProfileGateTests(unittest.TestCase):
    def test_sparse_tianjin_medical_device_profile_requires_interview_and_blocks_candidates(self) -> None:
        profile = {
            "company_name": "天津测试公司",
            "business_role": "LOCAL_DISTRIBUTOR",
            "operating_regions": [
                {"province": "天津市", "city": "天津市", "scope_mode": "ENTIRE_CITY", "districts": []}
            ],
            "customer_types": ["TERTIARY_HOSPITAL"],
            "product_capabilities": [
                {"category": "医疗器械", "subcategory": None, "brands": [], "capability_type": "UNKNOWN"}
            ],
        }
        result = evaluate_customer_profile(profile)
        codes = {item.code for item in result.missing_conditions}
        self.assertEqual(result.computed_status, "INCOMPLETE")
        self.assertEqual(result.recommendation_mode, "PROFILE_INTERVIEW_REQUIRED")
        self.assertFalse(result.candidate_opportunity_allowed)
        self.assertFalse(result.personalized_recommendation_allowed)
        self.assertIn("PRODUCT_SCOPE_TOO_BROAD", codes)
        self.assertIn("PRODUCT_CAPABILITY_TYPE_UNKNOWN", codes)
        self.assertIn("PARTNERING_POLICY_MISSING", codes)
        self.assertIn("OPPORTUNITY_THRESHOLDS_MISSING", codes)
        self.assertIsNotNone(result.next_question)

    def test_core_scope_is_valid_but_unconfirmed_profile_is_candidate_only(self) -> None:
        profile = base_profile()
        profile["confirmation_flags"] = {
            "region_scope_confirmed": False,
            "customer_types_confirmed": False,
            "product_capabilities_confirmed": False,
            "partnering_policy_confirmed": False,
            "opportunity_preferences_confirmed": False,
            "exclusion_rules_confirmed": False,
        }
        result = evaluate_customer_profile(profile)
        self.assertEqual(result.computed_status, "SUFFICIENT_FOR_CANDIDATES")
        self.assertEqual(result.recommendation_mode, "CANDIDATE_ONLY")
        self.assertTrue(result.candidate_opportunity_allowed)
        self.assertFalse(result.personalized_recommendation_allowed)
        self.assertGreaterEqual(len(result.missing_conditions), 6)
        self.assertIn("REGION_SCOPE_NOT_CONFIRMED", {item.code for item in result.missing_conditions})

    def test_fully_confirmed_profile_is_personalized_ready_and_frontend_status_is_ignored(self) -> None:
        profile = base_profile()
        result = evaluate_customer_profile(profile)
        self.assertEqual(result.computed_status, "SUFFICIENT_FOR_PERSONALIZED_RECOMMENDATION")
        self.assertEqual(result.recommendation_mode, "PERSONALIZED_RECOMMENDATION")
        self.assertTrue(result.candidate_opportunity_allowed)
        self.assertTrue(result.personalized_recommendation_allowed)
        self.assertEqual(result.profile_completeness, 100)
        self.assertEqual(result.missing_conditions, ())
        self.assertIsNone(result.next_question)
        self.assertIn("SUPPLIED_PROFILE_STATUS_IGNORED_AND_RECOMPUTED", result.warnings)
        self.assertIn("SUPPLIED_PROFILE_COMPLETENESS_IGNORED_AND_RECOMPUTED", result.warnings)
        self.assertIn("SUPPLIED_MISSING_CONDITIONS_IGNORED_AND_RECOMPUTED", result.warnings)

    def test_selected_districts_without_district_list_blocks_candidate_mode(self) -> None:
        profile = base_profile()
        profile["operating_regions"] = [
            {
                "province": "天津市",
                "city": "天津市",
                "scope_mode": "SELECTED_DISTRICTS",
                "districts": [],
            }
        ]
        result = evaluate_customer_profile(profile)
        self.assertFalse(result.candidate_opportunity_allowed)
        self.assertIn("REGION_DISTRICTS_MISSING", {item.code for item in result.missing_conditions})

    def test_direct_authorized_without_brand_scope_is_not_personalized_ready(self) -> None:
        profile = base_profile()
        profile["product_capabilities"][0]["brands"] = []
        result = evaluate_customer_profile(profile)
        self.assertFalse(result.personalized_recommendation_allowed)
        self.assertIn("AUTHORIZED_BRANDS_MISSING", {item.code for item in result.missing_conditions})

    def test_rental_policy_is_required_because_rental_opportunities_change_executability(self) -> None:
        profile = base_profile()
        profile["partnering_policy"]["can_do_rental_projects"] = None
        result = evaluate_customer_profile(profile)
        self.assertFalse(result.personalized_recommendation_allowed)
        self.assertIn("CAN_DO_RENTAL_PROJECTS_MISSING", {item.code for item in result.missing_conditions})

    def test_gate_output_includes_schema_version_and_structured_next_question(self) -> None:
        profile = base_profile()
        profile["confirmation_flags"]["exclusion_rules_confirmed"] = False
        payload = evaluate_customer_profile(profile).as_dict()
        self.assertEqual(payload["schema_version"], "0.1")
        self.assertEqual(payload["recommendation_mode"], "CANDIDATE_ONLY")
        self.assertIsInstance(payload["missing_required_conditions"], list)
        self.assertTrue(payload["next_question"])
        self.assertIn("question", payload["missing_required_conditions"][0])


if __name__ == "__main__":
    unittest.main()
