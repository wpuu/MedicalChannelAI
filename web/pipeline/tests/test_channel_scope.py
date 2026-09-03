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
            "天津市第三中心医院数字彩色超声诊断系统采购项目",
            "天津市滨海新区海滨人民医院采购人工智能GPU（8卡）算力服务器项目",
            "天津市第一中心医院甲型肝炎病毒IgM抗体质控品等采购项目院内比选公告",
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
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(is_medical_channel_relevant_text(title))

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
