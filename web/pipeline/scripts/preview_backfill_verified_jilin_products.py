#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline.validation import validate_records  # noqa: E402

RECORDS_PATH = PIPELINE_ROOT / 'data' / 'regional_live_ccgp_records.json'
REPORT_PATH = PIPELINE_ROOT / 'data' / 'preview_jilin_live_verification.json'


def main() -> int:
    records = json.loads(RECORDS_PATH.read_text(encoding='utf-8'))
    report = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    if report.get('verified_count') != 8:
        raise RuntimeError('JILIN_LIVE_VERIFICATION_INCOMPLETE')

    by_id = {record['opportunity_id']: record for record in records}
    changed: list[str] = []
    verified_ids = {case['opportunity_id'] for case in report['cases']}
    if len(verified_ids) != 8:
        raise RuntimeError('JILIN_LIVE_VERIFICATION_IDS_INVALID')

    for case in report['cases']:
        opportunity_id = case['opportunity_id']
        record = by_id.get(opportunity_id)
        if record is None:
            raise RuntimeError(f'JILIN_RECORD_NOT_FOUND:{opportunity_id}')
        facts = record.get('facts') or {}
        if facts.get('market_code') != 'JL':
            raise RuntimeError(f'JILIN_MARKET_MISMATCH:{opportunity_id}:{facts.get("market_code")}')
        if facts.get('project_name') != case.get('project_name'):
            raise RuntimeError(f'JILIN_PROJECT_MISMATCH:{opportunity_id}')

        items = case.get('product_items') or []
        if any(item.get('raw_name') == '数量' for item in items):
            raise RuntimeError(f'JILIN_INVALID_QUANTITY_LABEL:{opportunity_id}')
        if not items:
            continue

        facts['product_items'] = items
        facts['product_categories'] = case.get('product_categories') or []
        record['facts'] = facts
        record['evidence'] = [
            item
            for item in (record.get('evidence') or [])
            if item.get('field_path') not in {'facts.product_items', 'facts.product_categories'}
        ]
        record['evidence'].append({
            'field_path': 'facts.product_items',
            'source_url': record['source']['url'],
            'locator': '采购需求/正文结构化产品明细',
        })
        changed.append(opportunity_id)

    expected_changed = {
        'ccgp_jl_3edf4a29f776eebf',
        'ccgp_jl_92d8a706047d0a62',
        'ccgp_jl_40d5ac0960328c51',
        'ccgp_jl_37172df35abece06',
        'ccgp_jl_25eb3b5947b52eaa',
    }
    if set(changed) != expected_changed:
        raise RuntimeError(f'JILIN_CHANGED_SET_MISMATCH:{changed}')

    validate_records(records)
    RECORDS_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'backfilled {len(changed)} verified Jilin records')
    for opportunity_id in changed:
        print(opportunity_id)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
