#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE_PATH = ROOT / 'pipeline/data/medical_channel_scope.json'
PY_TEST_PATH = ROOT / 'pipeline/tests/test_channel_scope.py'
JS_CHECK_PATH = ROOT / 'scripts/check-medical-channel-scope.mjs'

scope = json.loads(SCOPE_PATH.read_text(encoding='utf-8'))
scope['schema_version'] = '0.5'

for term in ['乳腺机', '眼底照相机', '疾病预防控制专用设备', '疾控专用设备']:
    if term not in scope['terms']:
        scope['terms'].append(term)
for term in ['信息互通共享', '应用支撑平台']:
    if term not in scope['contextual_terms']:
        scope['contextual_terms'].append(term)
scope.setdefault('policy', {})['verified_specific_medical_devices_may_be_strong_signals'] = True
scope['policy']['medical_it_contextual_terms_require_medical_context'] = True
SCOPE_PATH.write_text(json.dumps(scope, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

py_text = PY_TEST_PATH.read_text(encoding='utf-8')
anchor = '''    def test_office_consumables_remain_out_even_for_hospital_buyer(self) -> None:\n'''
if anchor not in py_text:
    raise SystemExit('PY_TEST_ANCHOR_NOT_FOUND')
new_test = '''    def test_verified_specific_device_and_medical_it_false_negatives_are_in_scope(self) -> None:\n        strong_titles = [\n            "中国医学科学院北京协和医院放射科乳腺机采购项目",\n            "中日友好医院免散瞳眼底照相机系统采购项目",\n            "中国疾病预防控制中心疾病预防控制专用设备购置项目",\n        ]\n        for title in strong_titles:\n            with self.subTest(title=title):\n                self.assertTrue(is_medical_channel_relevant_text(title))\n\n        health_it = {\n            "facts": {\n                "project_name": "2026年应用支撑平台、信息互通共享功能升级项目",\n                "buyer_name": "国家卫生健康委统计信息中心",\n                "hospital_name": None,\n                "department": None,\n                "product_categories": [],\n                "product_items": [],\n            }\n        }\n        generic_it = copy.deepcopy(health_it)\n        generic_it["facts"]["buyer_name"] = "某市大数据中心"\n        self.assertTrue(is_medical_channel_relevant_record(health_it))\n        self.assertFalse(is_medical_channel_relevant_record(generic_it))\n        self.assertFalse(is_medical_channel_relevant_text("2026年应用支撑平台、信息互通共享功能升级项目"))\n\n'''
if 'test_verified_specific_device_and_medical_it_false_negatives_are_in_scope' not in py_text:
    py_text = py_text.replace(anchor, new_test + anchor, 1)
PY_TEST_PATH.write_text(py_text, encoding='utf-8')

js_text = JS_CHECK_PATH.read_text(encoding='utf-8')
js_anchor = '''assert.equal(isMedicalChannelRelevantCard({\n  facts: {\n    project_name: '办公耗材',\n'''
if js_anchor not in js_text:
    raise SystemExit('JS_CHECK_ANCHOR_NOT_FOUND')
js_block = '''for (const title of [\n  '中国医学科学院北京协和医院放射科乳腺机采购项目',\n  '中日友好医院免散瞳眼底照相机系统采购项目',\n  '中国疾病预防控制中心疾病预防控制专用设备购置项目',\n]) {\n  assert.equal(isMedicalChannelRelevantText(title), true, `specific medical scope should include: ${title}`)\n}\n\nassert.equal(isMedicalChannelRelevantCard({\n  facts: {\n    project_name: '2026年应用支撑平台、信息互通共享功能升级项目',\n    buyer_name: '国家卫生健康委统计信息中心',\n    product_categories: [],\n    product_items: [],\n  },\n}), true)\n\nassert.equal(isMedicalChannelRelevantCard({\n  facts: {\n    project_name: '2026年应用支撑平台、信息互通共享功能升级项目',\n    buyer_name: '某市大数据中心',\n    product_categories: [],\n    product_items: [],\n  },\n}), false)\n\n'''
if 'specific medical scope should include' not in js_text:
    js_text = js_text.replace(js_anchor, js_block + js_anchor, 1)
JS_CHECK_PATH.write_text(js_text, encoding='utf-8')

print('final medical scope recall patch applied')
