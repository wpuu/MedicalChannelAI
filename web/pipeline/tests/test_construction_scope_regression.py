from __future__ import annotations

import unittest

from medical_channel_pipeline.channel_scope import (
    is_medical_channel_relevant_record,
    is_medical_channel_relevant_text,
)


class ConstructionScopeRegressionTests(unittest.TestCase):
    def test_hospital_lab_construction_only_project_is_out_of_scope(self) -> None:
        title = (
            "中国中医科学院眼科医院国家中医药传承创新中心建设项目"
            "基建改造工程——眼功能实验室改造施工"
        )
        self.assertFalse(is_medical_channel_relevant_text(title))
        self.assertFalse(
            is_medical_channel_relevant_record(
                {
                    "facts": {
                        "project_name": title,
                        "buyer_name": "中国中医科学院眼科医院",
                        "hospital_name": None,
                        "department": None,
                        "product_categories": [],
                        "product_items": [],
                    }
                }
            )
        )

    def test_strong_medical_signal_still_keeps_medical_gas_upgrade(self) -> None:
        title = "朝阳县中心医院西梁院区医用气体改造工程"
        self.assertTrue(is_medical_channel_relevant_text(title))
        self.assertTrue(
            is_medical_channel_relevant_record(
                {
                    "facts": {
                        "project_name": title,
                        "buyer_name": "朝阳县中心医院",
                        "hospital_name": None,
                        "department": None,
                        "product_categories": [],
                        "product_items": [],
                    }
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
