from __future__ import annotations

import unittest

from tools.medical_pilot.product_classifier import classify_product_facts


def fact(fact_id: str, value: str, *, verified: bool = True, model_generated: bool = False) -> dict:
    return {
        "fact_id": fact_id,
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED" if verified else "UNVERIFIED",
        "model_generated": model_generated,
        "field_name": "project_name",
        "field_value": value,
    }


class ProductClassifierTests(unittest.TestCase):
    def test_spect_ct_suppresses_generic_ct_label(self) -> None:
        result = classify_product_facts([
            fact("fact_11111111-1111-1111-1111-111111111111", "天津医院单光子发射及X射线计算机断层成像系统（SPECT/CT）采购项目")
        ])
        self.assertIn("MEDICAL_IMAGING_SPECT_CT", result.labels)
        self.assertNotIn("MEDICAL_IMAGING_CT", result.labels)
        self.assertEqual(result.validation_status, "VALIDATED")

    def test_dr_is_deterministically_classified(self) -> None:
        result = classify_product_facts([
            fact("fact_22222222-2222-2222-2222-222222222222", "天津市泰达医院数字X光机（DR）采购项目")
        ])
        self.assertEqual(result.labels, ("MEDICAL_IMAGING_DR",))

    def test_qpcr_and_flow_cytometer_use_stable_ids(self) -> None:
        result = classify_product_facts([
            fact("fact_33333333-3333-3333-3333-333333333333", "实时荧光定量PCR仪及流式细胞仪采购")
        ])
        self.assertIn("LAB_PCR_QPCR", result.labels)
        self.assertIn("LAB_FLOW_CYTOMETER", result.labels)

    def test_specific_flow_reagent_suppresses_generic_reagent(self) -> None:
        result = classify_product_facts([
            fact("fact_44444444-4444-4444-4444-444444444444", "CD45检测试剂、CD3检测试剂等检验试剂")
        ])
        self.assertIn("LAB_REAGENT_FLOW_CYTOMETRY", result.labels)
        self.assertNotIn("LAB_REAGENT_GENERAL", result.labels)

    def test_ambiguous_device_text_stays_unverified_instead_of_guessing(self) -> None:
        result = classify_product_facts([
            fact("fact_55555555-5555-5555-5555-555555555555", "医疗设备采购项目")
        ])
        self.assertEqual(result.labels, ())
        self.assertEqual(result.validation_status, "UNVERIFIED")
        self.assertEqual(result.supporting_fact_ids, ())

    def test_unverified_and_model_generated_facts_are_ignored(self) -> None:
        result = classify_product_facts([
            fact("fact_66666666-6666-6666-6666-666666666666", "流式细胞仪", verified=False),
            fact("fact_77777777-7777-7777-7777-777777777777", "PCR仪", model_generated=True),
        ])
        self.assertEqual(result.labels, ())

    def test_each_label_keeps_supporting_fact_reference(self) -> None:
        fact_id = "fact_88888888-8888-8888-8888-888888888888"
        result = classify_product_facts([fact(fact_id, "全自动化学发光免疫分析仪")])
        self.assertEqual(result.labels, ("LAB_CHEMILUMINESCENCE_ANALYZER",))
        self.assertEqual(result.supporting_fact_ids, (fact_id,))
        self.assertIn("全自动化学发光免疫分析仪", result.matched_phrases["LAB_CHEMILUMINESCENCE_ANALYZER"])


if __name__ == "__main__":
    unittest.main()
