#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL = ROOT / 'pipeline/medical_channel_pipeline/ccgp_detail.py'
TEST = ROOT / 'pipeline/tests/test_ccgp_detail.py'
REGIONAL = ROOT / 'pipeline/data/regional_live_ccgp_records.json'

source = DETAIL.read_text(encoding='utf-8')
anchor = '''def _extract_contact(text: str) -> dict[str, str | None] | None:\n'''
helper = '''def _normalize_public_phone(value: str) -> str | None:\n    normalized = _normalize_space(value)\n    # Contact facts must fail closed. A non-empty label value that has no\n    # plausible telephone digit content (for example a repeated contact name)\n    # is not a phone number and must never become a dial target.\n    if len(re.findall(r"\\d", normalized)) < 5:\n        return None\n    return normalized\n\n\n'''
if helper.strip() not in source:
    if anchor not in source:
        raise SystemExit('CONTACT_HELPER_ANCHOR_NOT_FOUND')
    source = source.replace(anchor, helper + anchor, 1)
old = '''        "phone": _normalize_space(match.group(2)),\n'''
new = '''        "phone": _normalize_public_phone(match.group(2)),\n'''
if new not in source:
    if old not in source:
        raise SystemExit('CONTACT_PHONE_ASSIGNMENT_NOT_FOUND')
    source = source.replace(old, new, 1)
DETAIL.write_text(source, encoding='utf-8')

test_source = TEST.read_text(encoding='utf-8')
test_anchor = '''    def test_competitive_consultation_uses_response_submission_deadline_not_opening_time(self) -> None:\n'''
new_test = '''    def test_non_phone_contact_value_is_preserved_as_name_but_not_dial_target(self) -> None:\n        text = FIXTURE.replace(\n            "项目联系人：李宁 电 话：022-23717450-8019",\n            "项目联系人：董艳 项目联系电话：董艳",\n        )\n        record = parse_ccgp_public_tender_text(\n            text,\n            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260907_27278298.htm",\n            observed_at="2026-09-09T09:30:00+08:00",\n            opportunity_id="ccgp_jl_invalid_phone_fixture",\n        )\n        contact = record["facts"]["public_contact"]\n        self.assertEqual(contact["name"], "董艳")\n        self.assertIsNone(contact["phone"])\n\n'''
if 'test_non_phone_contact_value_is_preserved_as_name_but_not_dial_target' not in test_source:
    if test_anchor not in test_source:
        raise SystemExit('CONTACT_TEST_ANCHOR_NOT_FOUND')
    test_source = test_source.replace(test_anchor, new_test + test_anchor, 1)
TEST.write_text(test_source, encoding='utf-8')

records = json.loads(REGIONAL.read_text(encoding='utf-8'))
changed = []
for record in records:
    facts = record.get('facts') or {}
    contact = facts.get('public_contact') or {}
    if not isinstance(contact, dict):
        continue
    raw = contact.get('phone')
    value = str(raw or '').strip()
    if value and len(re.findall(r'\d', value)) < 5:
        changed.append({
            'opportunity_id': record.get('opportunity_id'),
            'project_name': facts.get('project_name'),
            'contact_name': contact.get('name'),
            'old_phone': raw,
            'source_url': (record.get('source') or {}).get('url'),
        })
        contact['phone'] = None

expected = [{
    'opportunity_id': 'ccgp_jl_7b4525920ec1cc52',
    'project_name': '通化市疾病预防控制中心（通化市卫生监督所）传染病实验室监测质量提升采购项目',
    'contact_name': '董艳',
    'old_phone': '董艳',
    'source_url': 'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260907_27278298.htm',
}]
if changed != expected:
    raise SystemExit(f'UNEXPECTED_INVALID_PHONE_SET:{changed!r}')
REGIONAL.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('public-contact phone fix applied', json.dumps(changed, ensure_ascii=False))
