from __future__ import annotations

import unittest

from tools.medical_pilot.opportunity_match_gate import evaluate_opportunity_match


TAXONOMY_ID = "LAB_CHEMILUMINESCENCE_ANALYZER"


def complete_profile(*, confirmed: bool = True, rental: bool = False) -> dict:
    return {
        "schema_version": "0.1",
        "profile_id": "mprof_11111111-1111-1111-1111-111111111111",
        "tenant_id": "tenant-demo",
        "company_name": "天津演示渠道公司",
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
                "category": "IVD",
                "subcategory": "化学发光分析仪",
                "taxonomy_ids": [TAXONOMY_ID],
                "brands": [],
                "capability_type": "DIRECT_UNCONFIRMED",
                "notes": None,
            }
        ],
        "partnering_policy": {
            "can_seek_temporary_manufacturer": True,
            "can_cooperate_with_channel_partner": True,
            "can_do_rental_projects": rental,
        },
        "opportunity_thresholds": {
            "minimum_project_amount_cny": "100000.00",
            "owner_attention_amount_cny": "1000000.00",
            "preferred_stages": ["MARKET_RESEARCH", "PROCUREMENT_INTENT", "TENDERING", "AWARDED"],
        },
        "exclusion_rules": [],
        "hospital_relationships": [],
        "confirmation_flags": {
            "region_scope_confirmed": confirmed,
            "customer_types_confirmed": confirmed,
            "product_capabilities_confirmed": confirmed,
            "partnering_policy_confirmed": confirmed,
            "opportunity_preferences_confirmed": confirmed,
            "exclusion_rules_confirmed": confirmed,
        },
        "profile_status": "SUFFICIENT_FOR_PERSONALIZED_RECOMMENDATION" if confirmed else "SUFFICIENT_FOR_CANDIDATES",
        "profile_completeness": 100 if confirmed else 70,
        "missing_required_conditions": [],
        "updated_at": "2026-08-28T20:00:00+08:00",
    }


def opportunity() -> dict:
    return {
        "schema_version": "0.1",
        "opportunity_id": "opp_22222222-2222-2222-2222-222222222222",
        "buyer_name": "天津医科大学总医院",
        "hospital_name": "天津医科大学总医院",
        "project_name": "化学发光设备采购项目",
        "verification_status": "VERIFIED",
        "coverage_status": "PARTIAL",
        "region": {"province": "天津市", "city": "天津市", "district": "和平区"},
        "customer_type": "TERTIARY_HOSPITAL",
        "customer_type_provenance": "OFFICIAL_INSTITUTION_EVIDENCE",
        "customer_type_validation_status": "VALIDATED",
        "institution_evidence_id": "inst_tjmugh",
        "lifecycle_state": "TENDERING",
        "budget": {"amount": "5730000.00", "currency": "CNY"},
        "product_labels": [TAXONOMY_ID],
        "product_label_provenance": "HUMAN_CONFIRMED",
        "product_label_validation_status": "VALIDATED",
        "product_classifier_id": "human-confirmed-product-taxonomy-v0.1",
        "is_rental_project": False,
    }


class OpportunityMatchGateTests(unittest.TestCase):
    def test_full_verified_match_allows_personalized_explanation(self) -> None:
        result = evaluate_opportunity_match(complete_profile(), opportunity())
        self.assertEqual(result.status, "MATCHED_PERSONALIZED")
        self.assertTrue(result.personalized_recommendation_allowed)
        self.assertTrue(result.candidate_opportunity_allowed)
        self.assertTrue(result.model_explanation_allowed)
        self.assertEqual(result.required_next_facts, ())

    def test_unconfirmed_profile_can_only_produce_candidate(self) -> None:
        result = evaluate_opportunity_match(complete_profile(confirmed=False), opportunity())
        self.assertEqual(result.status, "MATCHED_CANDIDATE")
        self.assertFalse(result.personalized_recommendation_allowed)
        self.assertTrue(result.candidate_opportunity_allowed)
        self.assertTrue(result.model_explanation_allowed)
        self.assertEqual(result.recommendation_mode, "CANDIDATE_ONLY")

    def test_unverified_fact_blocks_model_and_match(self) -> None:
        item = opportunity()
        item["verification_status"] = "UNVERIFIED"
        result = evaluate_opportunity_match(complete_profile(), item)
        self.assertEqual(result.status, "FACT_BLOCKED")
        self.assertFalse(result.model_explanation_allowed)
        self.assertFalse(result.candidate_opportunity_allowed)

    def test_missing_product_classification_requires_fact_enrichment_not_guessing(self) -> None:
        item = opportunity()
        item["product_labels"] = []
        result = evaluate_opportunity_match(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertIn("opportunity.product_labels", result.required_next_facts)
        self.assertFalse(result.model_explanation_allowed)

    def test_selected_district_profile_needs_opportunity_district_fact(self) -> None:
        profile = complete_profile()
        profile["operating_regions"] = [
            {
                "province": "天津市",
                "city": "天津市",
                "scope_mode": "SELECTED_DISTRICTS",
                "districts": ["和平区"],
            }
        ]
        item = opportunity()
        item["region"]["district"] = None
        result = evaluate_opportunity_match(profile, item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertIn("opportunity.region.district", result.required_next_facts)

    def test_rental_project_rejected_when_customer_confirmed_no_rental(self) -> None:
        item = opportunity()
        item["is_rental_project"] = True
        result = evaluate_opportunity_match(complete_profile(rental=False), item)
        self.assertEqual(result.status, "REJECTED")
        self.assertTrue(any(reason.code == "RENTAL_PROJECT_NOT_SUPPORTED" for reason in result.reasons))

    def test_below_minimum_amount_is_rejected(self) -> None:
        item = opportunity()
        item["budget"] = {"amount": "99999.00", "currency": "CNY"}
        result = evaluate_opportunity_match(complete_profile(), item)
        self.assertEqual(result.status, "REJECTED")
        self.assertTrue(any(reason.code == "BELOW_MINIMUM_PROJECT_AMOUNT" for reason in result.reasons))

    def test_explicit_exclusion_wins_before_model(self) -> None:
        profile = complete_profile()
        profile["exclusion_rules"] = [
            {"kind": "PRODUCT_CATEGORY", "value": TAXONOMY_ID, "reason": "当前不做"}
        ]
        result = evaluate_opportunity_match(profile, opportunity())
        self.assertEqual(result.status, "REJECTED")
        self.assertFalse(result.model_explanation_allowed)
        self.assertTrue(any(reason.code == "EXPLICIT_EXCLUSION_MATCH" for reason in result.reasons))

    def test_unknown_customer_grade_does_not_guess_from_hospital_name(self) -> None:
        item = opportunity()
        item["customer_type"] = "UNKNOWN"
        item["customer_type_provenance"] = "UNRESOLVED"
        item["customer_type_validation_status"] = "UNVERIFIED"
        item["institution_evidence_id"] = None
        result = evaluate_opportunity_match(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertIn("opportunity.customer_type", result.required_next_facts)

    def test_outside_region_is_rejected(self) -> None:
        item = opportunity()
        item["region"] = {"province": "河北省", "city": "唐山市", "district": "路北区"}
        result = evaluate_opportunity_match(complete_profile(), item)
        self.assertEqual(result.status, "REJECTED")
        self.assertTrue(any(reason.code == "OUTSIDE_OPERATING_REGION" for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
