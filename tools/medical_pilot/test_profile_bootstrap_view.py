from __future__ import annotations

import unittest

from tools.medical_pilot.profile_http import BOOTSTRAP_PLACEHOLDER_NOTE, _public_profile


class ProfileBootstrapViewTests(unittest.TestCase):
    def test_unconfirmed_bootstrap_sentinels_are_not_presented_as_customer_facts(self) -> None:
        stored = {
            "schema_version": "0.1",
            "tenant_id": "tenant-test",
            "profile_id": "mprof_11111111-1111-1111-1111-111111111111",
            "company_name": "天津试用客户",
            "business_role": "OTHER",
            "operating_regions": [
                {"province": "天津市", "city": "天津市", "scope_mode": "ENTIRE_CITY", "districts": []}
            ],
            "customer_types": ["OTHER"],
            "product_capabilities": [
                {
                    "category": "待客户填写",
                    "subcategory": None,
                    "taxonomy_ids": ["MEDICAL_CONSUMABLE_GENERAL"],
                    "brands": [],
                    "capability_type": "UNKNOWN",
                    "notes": BOOTSTRAP_PLACEHOLDER_NOTE,
                }
            ],
            "partnering_policy": {
                "can_seek_temporary_manufacturer": False,
                "can_cooperate_with_channel_partner": False,
                "can_do_rental_projects": False,
            },
            "opportunity_thresholds": {
                "minimum_project_amount_cny": "0",
                "preferred_stages": ["PROCUREMENT_INTENT"],
            },
            "exclusion_rules": [],
            "hospital_relationships": [],
            "confirmation_flags": {
                "region_scope_confirmed": False,
                "customer_types_confirmed": False,
                "product_capabilities_confirmed": False,
                "partnering_policy_confirmed": False,
                "opportunity_preferences_confirmed": False,
                "exclusion_rules_confirmed": False,
            },
            "profile_status": "INCOMPLETE",
            "profile_completeness": 0,
            "missing_required_conditions": ["CUSTOMER_PROFILE_NOT_CONFIRMED"],
            "updated_at": "2026-08-31T00:00:00+00:00",
        }

        public = _public_profile(stored)

        self.assertEqual(public["customer_types"], [])
        self.assertEqual(public["product_capabilities"], [])
        self.assertNotIn("tenant_id", public)
        self.assertNotIn("profile_id", public)
        self.assertNotIn(BOOTSTRAP_PLACEHOLDER_NOTE, str(public))

    def test_customer_confirmed_other_type_is_preserved(self) -> None:
        stored = {
            "customer_types": ["OTHER"],
            "product_capabilities": [],
            "confirmation_flags": {"customer_types_confirmed": True},
        }
        public = _public_profile(stored)
        self.assertEqual(public["customer_types"], ["OTHER"])


if __name__ == "__main__":
    unittest.main()
