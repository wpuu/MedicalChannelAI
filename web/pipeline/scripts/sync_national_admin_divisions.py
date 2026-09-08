#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import urllib.request
from pathlib import Path

SOURCE_META = Path(__file__).resolve().parents[1] / 'data' / 'admin_division_source.json'
EXPECTED_PROVINCES = {
    '11': '北京市',
    '12': '天津市',
    '13': '河北省',
    '21': '辽宁省',
    '22': '吉林省',
    '23': '黑龙江省',
}


def load_pinned_payload() -> tuple[dict, list[dict]]:
    meta = json.loads(SOURCE_META.read_text(encoding='utf-8'))
    mirror = meta['retrieval_mirror']
    blob_sha = str(mirror['git_blob_sha']).strip()
    url = f'https://api.github.com/repos/dataxiv/data-district/git/blobs/{blob_sha}'
    request = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'MedicalChannelAI-AdminDivisionSync/0.1',
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        envelope = json.loads(response.read().decode('utf-8'))
    if envelope.get('sha') != blob_sha or envelope.get('encoding') != 'base64':
        raise RuntimeError('ADMIN_DIVISION_PINNED_BLOB_MISMATCH')
    raw = base64.b64decode(str(envelope.get('content') or ''))
    payload = json.loads(raw.decode('utf-8'))
    if not isinstance(payload, list):
        raise RuntimeError('ADMIN_DIVISION_DATA_INVALID')
    return meta, payload


def validate_national_table(meta: dict, payload: list[dict]) -> None:
    # The pinned MCA 2025 dataset has 33 coded province-level rows. Taiwan is
    # intentionally published as a province placeholder with its code marked
    # "资料暂缺". Never invent or infer a numeric administrative code for it.
    coded_roots = [item for item in payload if item.get('level') == 1]
    taiwan_placeholders = [
        item for item in payload
        if item.get('name') == '台湾省' and item.get('type') == '省'
    ]
    if len(coded_roots) != 33:
        raise RuntimeError(f'ADMIN_DIVISION_CODED_PROVINCE_COUNT_INVALID:{len(coded_roots)}')
    if len(taiwan_placeholders) != 1:
        raise RuntimeError(f'ADMIN_DIVISION_TAIWAN_PLACEHOLDER_COUNT_INVALID:{len(taiwan_placeholders)}')
    taiwan = taiwan_placeholders[0]
    if str(taiwan.get('code') or '').strip() != '资料暂缺' or taiwan.get('level') != 0:
        raise RuntimeError('ADMIN_DIVISION_TAIWAN_PLACEHOLDER_INVALID')
    if len(coded_roots) + len(taiwan_placeholders) != 34:
        raise RuntimeError('ADMIN_DIVISION_TOP_LEVEL_NAME_COUNT_INVALID')

    by_code = {str(item.get('code') or ''): item for item in payload}
    for code, name in EXPECTED_PROVINCES.items():
        item = by_code.get(code)
        if not item or item.get('level') != 1 or item.get('name') != name:
            raise RuntimeError(f'ADMIN_DIVISION_ENABLED_MARKET_MISMATCH:{code}:{name}')
    enabled = {str(item['admin_code'])[:2]: item for item in meta.get('enabled_markets', [])}
    for code, name in EXPECTED_PROVINCES.items():
        market = enabled.get(code)
        if not market or str(market.get('ccgp_zone_id')) != code:
            raise RuntimeError(f'ADMIN_DIVISION_MARKET_CONFIG_MISMATCH:{code}:{name}')


def main() -> int:
    parser = argparse.ArgumentParser(description='Materialize the pinned nationwide MCA county-and-above table.')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    meta, payload = load_pinned_payload()
    validate_national_table(meta, payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output = {
        'schema_version': '0.1',
        'authority': meta['authority'],
        'official_product': meta['official_product'],
        'official_url': meta['official_url'],
        'version': meta['version'],
        'as_of': meta['as_of'],
        'record_count': len(payload),
        'coded_province_level_count': 33,
        'top_level_named_count': 34,
        'taiwan_code_status': '资料暂缺',
        'records': payload,
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(
        f'admin_divisions version={meta["version"]} records={len(payload)} '
        'coded_provinces=33 top_level_names=34 taiwan_code=资料暂缺'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
