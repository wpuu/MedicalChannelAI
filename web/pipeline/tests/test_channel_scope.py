from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot
from medical_channel_pipeline.channel_scope import (
    is_medical_channel_relevant_record,
    is_medical_channel_relevant_text,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "tianjin_verified_seed.json"


class MedicalChannelScopeTests(unittest.TestCase):
    def test_core_and_adjacent_medical_technology_titles_are_in_scope(self) -> None:
        titles = [
            "天津市第五中心医院医疗设备更新项目-数字减影血管造影机采购项目",
            "天津市滨海新区大港医院CT影像设备维保项目",
            "天津市胸科医院检验科设备租赁服务项目",
            "天津市滨海新区海滨人民医院采购人工智能GPU（8卡）算力服务器项目",
            "天津市第一中心医院甲型肝炎病毒IgM抗体质控品等采购项目院内比选公告",
            "天津中医药大学第二附属医院高分辨液质联用系统三年期维保项目",
            "空气压力治疗仪（淋巴水肿专用）采购项目",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertTrue(is_medical_channel_relevant_text(title))

    def test_generic_hospital_administration_is_not_in_scope(self) -> None:
        titles = [
            "天津中医药大学第二附属医院安保服务项目",
            "天津市海河医院战略型复合人才培养项目",
            "西青区卫生健康基层医疗卫生机构财务信息化管理项目",
            "天津市第一中心医院科教处工服采购项目院内比选公告",
            "中医外治疗室装修改造工程项目",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(is_medical_channel_relevant_text(title))

    def test_hard_business_exclusion_overrides_medical_wording(self) -> None:
        title = "丹东市中心医院2026-2029年度医用织物洗涤消毒招标采购"
        self.assertFalse(is_medical_channel_relevant_text(title))
        record = {
            "facts": {
                "project_name": title,
                "buyer_name": "丹东市中心医院",
                "hospital_name": None,
                "department": None,
                "product_categories": [],
                "product_items": [],
            }
        }
        self.assertFalse(is_medical_channel_relevant_record(record))

    def test_hospital_buyer_name_alone_does_not_make_record_relevant(self) -> None:
        record = {
            "facts": {
                "project_name": "安保服务项目",
                "buyer_name": "天津市某医院",
                "hospital_name": "天津市某医院",
                "department": None,
                "product_categories": [],
                "product_items": [],
            }
        }
        self.assertFalse(is_medical_channel_relevant_record(record))

    def test_generic_inspection_keywords_require_medical_context(self) -> None:
        non_medical_records = [
            {
                "facts": {
                    "project_name": "计量专业检验检测设备更新项目",
                    "buyer_name": "北京市计量检测科学研究院",
                    "hospital_name": None,
                    "department": None,
                    "product_categories": [],
                    "product_items": [],
                }
            },
            {
                "facts": {
                    "project_name": "2026-2027年度拟外委托检验检测项目",
                    "buyer_name": "自然资源部大连海洋中心（自然资源部大连海洋预报台）",
                    "hospital_name": None,
                    "department": None,
                    "product_categories": [],
                    "product_items": [],
                }
            },
        ]
        for record in non_medical_records:
            with self.subTest(project=record["facts"]["project_name"]):
                self.assertFalse(is_medical_channel_relevant_record(record))

    def test_contextual_lab_terms_are_kept_for_medical_buyers(self) -> None:
        records = [
            {
                "facts": {
                    "project_name": "检验检测仪器设备更新项目-2",
                    "buyer_name": "黑龙江省药品检验研究院",
                    "hospital_name": None,
                    "department": None,
                    "product_categories": [],
                    "product_items": [],
                }
            },
            {
                "facts": {
                    "project_name": "实验室仪器设备采购项目",
                    "buyer_name": "某市中心医院",
                    "hospital_name": "某市中心医院",
                    "department": None,
                    "product_categories": [],
                    "product_items": [],
                }
            },
        ]
        for record in records:
            with self.subTest(project=record["facts"]["project_name"]):
                self.assertTrue(is_medical_channel_relevant_record(record))

    def test_adjacent_ai_compute_requires_medical_context_in_procurement_facts(self) -> None:
        self.assertFalse(is_medical_channel_relevant_text("人工智能GPU算力服务器项目"))
        self.assertTrue(is_medical_channel_relevant_text("某市中心医院人工智能GPU算力服务器项目"))

        hospital_buyer_only = {
            "facts": {
                "project_name": "人工智能GPU算力服务器项目",
                "buyer_name": "某市中心医院",
                "hospital_name": "某市中心医院",
                "department": None,
                "product_categories": [],
                "product_items": [],
            }
        }
        self.assertFalse(is_medical_channel_relevant_record(hospital_buyer_only))

        medical_title = copy.deepcopy(hospital_buyer_only)
        medical_title["facts"]["project_name"] = "某市中心医院人工智能GPU算力服务器项目"
        self.assertTrue(is_medical_channel_relevant_record(medical_title))

        non_medical = copy.deepcopy(hospital_buyer_only)
        non_medical["facts"]["buyer_name"] = "某市大数据中心"
        non_medical["facts"]["hospital_name"] = None
        self.assertFalse(is_medical_channel_relevant_record(non_medical))

    def test_office_consumables_remain_out_even_for_hospital_buyer(self) -> None:
        record = {
            "facts": {
                "project_name": "办公耗材",
                "buyer_name": "北京中医药大学东方医院秦皇岛医院（秦皇岛市中医医院）",
                "hospital_name": None,
                "department": None,
                "product_categories": [],
                "product_items": [],
            }
        }
        self.assertFalse(is_medical_channel_relevant_record(record))

    def test_public_snapshot_filters_generic_hospital_procurement_but_keeps_gpu_ai(self) -> None:
        records = json.loads(SEED.read_text(encoding="utf-8"))
        generic = copy.deepcopy(records[0])
        generic["opportunity_id"] = "generic_hospital_security"
        generic["facts"]["project_number"] = "GENERIC-SECURITY-001"
        generic["facts"]["project_name"] = "天津市胸科医院安保服务项目"
        generic["facts"]["department"] = None
        generic["facts"]["product_categories"] = []
        generic["facts"]["product_items"] = []
        records.append(generic)

        payload = build_public_snapshot(
            records,
            datetime.fromisoformat("2026-08-28T12:00:00+08:00"),
        )
        ids = {item["opportunity_id"] for item in payload["opportunity_pool"]}
        self.assertNotIn("generic_hospital_security", ids)
        self.assertIn("verified_hbrmyy_gpu_0052", ids)


if __name__ == "__main__":
    unittest.main()
