from __future__ import annotations

import copy
import unittest

from tools.medical_pilot.subscription_prefilter import (
    build_profile_subscription_index,
    prefilter_profiles_for_opportunity,
)
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


CHEM = "LAB_CHEMILUMINESCENCE_ANALYZER"
DR = "MEDICAL_IMAGING_DR"


def profile_variant(
    n: int,
    *,
    taxonomy: str = CHEM,
    customer_types: list[str] | None = None,
    scope_mode: str = "ENTIRE_CITY",
    districts: list[str] | None = None,
) -> dict:
    profile = complete_profile()
    profile["profile_id"] = f"mprof_{n:08x}-1111-1111-1111-111111111111"
    profile["customer_types"] = customer_types or ["TERTIARY_HOSPITAL"]
    profile["product_capabilities"][0]["taxonomy_ids"] = [taxonomy]
    profile["operating_regions"] = [
        {
            "province": "天津市",
            "city": "天津市",
            "scope_mode": scope_mode,
            "districts": districts or [],
        }
    ]
    return profile


class SubscriptionPrefilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.citywide = profile_variant(1)
        self.heping = profile_variant(2, scope_mode="SELECTED_DISTRICTS", districts=["和平区"])
        self.hexi = profile_variant(3, scope_mode="SELECTED_DISTRICTS", districts=["河西区"])
        self.dr_profile = profile_variant(4, taxonomy=DR)
        self.cdc_profile = profile_variant(5, customer_types=["CDC"])
        self.index = build_profile_subscription_index(
            [self.citywide, self.heping, self.hexi, self.dr_profile, self.cdc_profile]
        )

    def test_exact_region_taxonomy_and_customer_type_reduce_candidate_profiles(self) -> None:
        item = opportunity()
        result = prefilter_profiles_for_opportunity(self.index, item)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(
            set(result["candidate_profile_ids"]),
            {self.citywide["profile_id"], self.heping["profile_id"]},
        )

    def test_unknown_district_remains_conservative_and_does_not_false_negative_selected_district_profiles(self) -> None:
        item = opportunity()
        item["region"]["district"] = None
        result = prefilter_profiles_for_opportunity(self.index, item)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(
            set(result["candidate_profile_ids"]),
            {self.citywide["profile_id"], self.heping["profile_id"], self.hexi["profile_id"]},
        )

    def test_different_product_taxonomy_is_excluded_before_full_match(self) -> None:
        item = opportunity()
        item["product_labels"] = [DR]
        result = prefilter_profiles_for_opportunity(self.index, item)
        self.assertEqual(result["candidate_profile_ids"], [self.dr_profile["profile_id"]])

    def test_different_customer_type_is_excluded_before_full_match(self) -> None:
        item = opportunity()
        item["customer_type"] = "CDC"
        item["institution_evidence_id"] = "inst_tianjin_cdc"
        result = prefilter_profiles_for_opportunity(self.index, item)
        self.assertEqual(result["candidate_profile_ids"], [self.cdc_profile["profile_id"]])

    def test_missing_taxonomy_requires_enrichment_instead_of_scanning_all_profiles(self) -> None:
        item = opportunity()
        item["product_labels"] = []
        result = prefilter_profiles_for_opportunity(self.index, item)
        self.assertEqual(result["status"], "NEEDS_MORE_FACTS")
        self.assertEqual(result["candidate_profile_ids"], [])
        self.assertIn("opportunity.product_labels", result["required_next_facts"])

    def test_unvalidated_customer_type_requires_enrichment(self) -> None:
        item = opportunity()
        item["customer_type_validation_status"] = "UNVERIFIED"
        result = prefilter_profiles_for_opportunity(self.index, item)
        self.assertEqual(result["status"], "NEEDS_MORE_FACTS")
        self.assertIn("opportunity.customer_type_validation_status", result["required_next_facts"])

    def test_profile_not_ready_for_candidate_matching_is_not_indexed(self) -> None:
        broken = copy.deepcopy(self.citywide)
        broken["profile_id"] = "mprof_ffffffff-1111-1111-1111-111111111111"
        broken["product_capabilities"][0]["taxonomy_ids"] = []
        index = build_profile_subscription_index([self.citywide, broken])
        self.assertEqual(index.indexed_profile_ids, (self.citywide["profile_id"],))


if __name__ == "__main__":
    unittest.main()
