#!/usr/bin/env python3
"""Offline product-fixture gate and historical patch proposal. Never applies patches."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medical_channel_pipeline.ccgp_detail import parse_ccgp_public_tender_html
from medical_channel_pipeline.channel_scope import is_medical_channel_relevant_record


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_hash(value: object) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def audit(manifest_path: Path, baseline_paths: list[Path]) -> dict:
    manifest = json.loads(manifest_path.read_text())
    baseline = {}
    sources = []
    for path in baseline_paths:
        raw = path.read_bytes()
        sources.append({'path': path.name, 'sha256': digest(raw)})
        records = json.loads(raw)
        if not isinstance(records, list):
            raise ValueError('BASELINE_ARRAY_REQUIRED')
        for record in records:
            key = record['opportunity_id']
            if key in baseline:
                raise ValueError('BASELINE_DUPLICATE_ID')
            baseline[key] = record
    results, proposals = [], []
    seen = set()
    for case in manifest['cases']:
        if case['label'] in seen:
            raise ValueError('DUPLICATE_CASE_LABEL')
        seen.add(case['label'])
        source = urlparse(case['url'])
        if source.scheme != 'https' or source.netloc != 'www.ccgp.gov.cn':
            raise ValueError('OFFICIAL_SOURCE_REQUIRED')
        path = (manifest_path.parent / case['file']).resolve()
        if path.parent != manifest_path.parent.resolve():
            raise ValueError('FIXTURE_PATH_OUTSIDE_CORPUS')
        raw = path.read_bytes()
        if digest(raw) != case['sha256'] or len(raw) != case['raw_bytes']:
            raise ValueError('FIXTURE_HASH_OR_SIZE_MISMATCH')
        record = parse_ccgp_public_tender_html(
            raw.decode(case['encoding'], errors='strict'), source_url=case['url'],
            observed_at=case['fetched_at'], opportunity_id=case['label'],
        )
        actual = [[item['raw_name'], item.get('quantity')] for item in record['facts']['product_items']]
        relevant = is_medical_channel_relevant_record(record)
        passed = actual == case['expected_pairs'] and relevant == case['expected_medical_relevant']
        results.append({'label': case['label'], 'kind': case['kind'], 'family': case['family'],
                        'expected_pairs': case['expected_pairs'], 'actual_pairs': actual,
                        'expected_medical_relevant': case['expected_medical_relevant'],
                        'actual_medical_relevant': relevant, 'pass': passed})
        key = case.get('baseline_id')
        if not (passed and case['kind'] == 'OFFICIAL_ORIGINAL' and key in baseline):
            continue
        old = baseline[key]
        if old['source']['url'] != case['url'] or old['facts']['project_number'] != record['facts']['project_number']:
            raise ValueError('BASELINE_OFFICIAL_IDENTITY_MISMATCH')
        before = {field: old['facts'][field] for field in ('product_items', 'product_categories')}
        after = {field: record['facts'][field] for field in before}
        if before == after:
            continue
        candidate = deepcopy(old)
        candidate['facts'].update(after)
        proposals.append({'opportunity_id': key, 'source_url': case['url'],
                          'baseline_record_sha256': object_hash(old), 'official_html_sha256': case['sha256'],
                          'candidate_record_sha256': object_hash(candidate),
                          'allowed_fact_fields': list(before), 'before': before, 'after': after,
                          'evidence_updates_required_before_apply': True,
                          'source_identity_and_scan_clocks_preserved': True,
                          'apply_allowed': False})
    failures = sum(not row['pass'] for row in results)
    return {'schema_version': '0.1', 'mode': 'OFFLINE_AUDIT_AND_PATCH_PROPOSAL_ONLY',
            'fixture_baseline_application_commit': manifest['frozen_against_application_commit'],
            'evaluated_parser_sha256': digest((ROOT / 'medical_channel_pipeline/ccgp_detail.py').read_bytes()),
            'baseline_files': sources, 'baseline_record_count': len(baseline),
            'official_cases': sum(row['kind'] == 'OFFICIAL_ORIGINAL' for row in results),
            'derived_cases': sum(row['kind'] == 'SYNTHETIC_DERIVED_NEGATIVE' for row in results),
            'case_count': len(results), 'passed': len(results) - failures, 'failed': failures,
            'fixture_gate_pass': failures == 0, 'results': results, 'patch_proposals': proposals,
            'apply_allowed': False, 'publishes_snapshot': False, 'writes_runtime_state': False,
            'network_requests': 0, 'interpretation': 'All proposals require separate gate, identity, event and concurrency review; a passing fixture gate alone never authorizes a backfill.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path, action='append')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    inputs = [args.manifest, *args.baseline]
    manifest = json.loads(args.manifest.read_text())
    inputs.extend(args.manifest.parent / case['file'] for case in manifest['cases'])
    if args.output.resolve() in {path.resolve() for path in inputs}:
        raise ValueError('OUTPUT_MUST_NOT_OVERWRITE_INPUT')
    report = audit(args.manifest, args.baseline)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f"cases={report['case_count']} passed={report['passed']} failed={report['failed']} apply_allowed=False")
    return 0 if report['fixture_gate_pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
