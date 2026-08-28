from __future__ import annotations

import unittest

from tools.medical_pilot.institution_enrichment import (
    enrich_opportunity_customer_type,
    resolve_institution_evidence,
)


class InstitutionEnrichmentTests(unittest.TestCase):
    def test_tjmugh_resolves_to_verified_tertiary_hospital(self) -> None:
        evidence = resolve_institution_evidence("天津医科大学总医院")
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.hospital_grade, "TERTIARY_A")
        self.assertEqual(evidence.match_customer_type, "TERTIARY_HOSPITAL")

    def test_chest_hospital_official_campus_alias_resolves_exactly(self) -> None:
        evidence = resolve_institution_evidence("天津市胸科医院（和平院区）")
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.institution_id, "inst_tianjin_chest_hospital")

    def test_cdc_resolves_to_cdc_not_hospital(self) -> None:
        evidence = resolve_institution_evidence("天津市疾病预防控制中心")
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.institution_type, "CDC")
        self.assertEqual(evidence.match_customer_type, "CDC")
        self.assertIsNone(evidence.hospital_grade)

    def test_new_tertiary_hospital_evidence_resolves_exact_names(self) -> None:
        expected = {
            "天津市第三中心医院": "inst_tianjin_third_central_hospital",
            "天津市第五中心医院": "inst_tianjin_fifth_central_hospital",
            "天津市中西医结合医院（天津市南开医院）": "inst_tianjin_nankai_hospital",
            "天津市中医药研究院附属医院": "inst_tianjin_tcm_research_affiliated_hospital",
            "天津市肿瘤医院": "inst_tianjin_cancer_hospital",
            "中国医学科学院血液病医院（中国医学科学院血液学研究所）": "inst_cams_blood_hospital",
            "天津市天津医院": "inst_tianjin_hospital",
        }
        for name, institution_id in expected.items():
            with self.subTest(name=name):
                evidence = resolve_institution_evidence(name)
                self.assertIsNotNone(evidence)
                assert evidence is not None
                self.assertEqual(evidence.institution_id, institution_id)
                self.assertEqual(evidence.hospital_grade, "TERTIARY_A")
                self.assertEqual(evidence.match_customer_type, "TERTIARY_HOSPITAL")

    def test_procurement_name_aliases_resolve_without_fuzzy_matching(self) -> None:
        aliases = {
            "天津市南开医院": "inst_tianjin_nankai_hospital",
            "天津医科大学肿瘤医院": "inst_tianjin_cancer_hospital",
            "中国医学科学院血液病医院(中国医学科学院血液学研究所）": "inst_cams_blood_hospital",
            "天津医院": "inst_tianjin_hospital",
            "天津大学中心医院": "inst_tianjin_third_central_hospital",
        }
        for alias, institution_id in aliases.items():
            with self.subTest(alias=alias):
                evidence = resolve_institution_evidence(alias)
                self.assertIsNotNone(evidence)
                assert evidence is not None
                self.assertEqual(evidence.institution_id, institution_id)

    def test_universities_resolve_as_university_not_hospital(self) -> None:
        for name in ("天津大学", "天津医科大学", "天津科技大学"):
            with self.subTest(name=name):
                evidence = resolve_institution_evidence(name)
                self.assertIsNotNone(evidence)
                assert evidence is not None
                self.assertEqual(evidence.institution_type, "UNIVERSITY")
                self.assertEqual(evidence.match_customer_type, "UNIVERSITY")
                self.assertIsNone(evidence.hospital_grade)

    def test_similar_but_unregistered_name_does_not_fuzzy_match(self) -> None:
        self.assertIsNone(resolve_institution_evidence("天津市第一中心医院分院"))
        self.assertIsNone(resolve_institution_evidence("天津市第五中心医院新区"))
        self.assertIsNone(resolve_institution_evidence("天津科技大学医院"))

    def test_xiqing_hospital_stays_unresolved_until_current_grade_evidence_is_added(self) -> None:
        self.assertIsNone(resolve_institution_evidence("天津市西青医院"))

    def test_enrichment_fills_validated_match_fields_only_from_registry(self) -> None:
        opportunity = {
            "hospital_name": "天津市胸科医院",
            "customer_type": "UNKNOWN",
            "customer_type_provenance": "UNRESOLVED",
            "customer_type_validation_status": "UNVERIFIED",
            "institution_evidence_id": None,
        }
        enriched = enrich_opportunity_customer_type(opportunity)
        self.assertEqual(enriched["customer_type"], "TERTIARY_HOSPITAL")
        self.assertEqual(enriched["customer_type_provenance"], "OFFICIAL_INSTITUTION_EVIDENCE")
        self.assertEqual(enriched["customer_type_validation_status"], "VALIDATED")
        self.assertEqual(enriched["institution_evidence_id"], "inst_tianjin_chest_hospital")

    def test_university_buyer_can_be_enriched_from_buyer_name(self) -> None:
        opportunity = {
            "buyer_name": "天津科技大学",
            "customer_type": "UNKNOWN",
            "customer_type_provenance": "UNRESOLVED",
            "customer_type_validation_status": "UNVERIFIED",
            "institution_evidence_id": None,
        }
        enriched = enrich_opportunity_customer_type(opportunity)
        self.assertEqual(enriched["customer_type"], "UNIVERSITY")
        self.assertEqual(enriched["institution_evidence_id"], "inst_tianjin_university_of_science_and_technology")

    def test_unknown_institution_stays_unresolved(self) -> None:
        enriched = enrich_opportunity_customer_type({"hospital_name": "天津未登记医院"})
        self.assertEqual(enriched["customer_type"], "UNKNOWN")
        self.assertEqual(enriched["customer_type_provenance"], "UNRESOLVED")
        self.assertEqual(enriched["customer_type_validation_status"], "UNVERIFIED")
        self.assertIsNone(enriched["institution_evidence_id"])

    def test_existing_validated_human_customer_type_is_not_overwritten(self) -> None:
        opportunity = {
            "hospital_name": "天津未登记医院",
            "customer_type": "PRIVATE_HOSPITAL",
            "customer_type_provenance": "HUMAN_CONFIRMED",
            "customer_type_validation_status": "VALIDATED",
            "institution_evidence_id": None,
        }
        enriched = enrich_opportunity_customer_type(opportunity)
        self.assertEqual(enriched["customer_type"], "PRIVATE_HOSPITAL")
        self.assertEqual(enriched["customer_type_provenance"], "HUMAN_CONFIRMED")


if __name__ == "__main__":
    unittest.main()
