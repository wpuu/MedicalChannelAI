#!/usr/bin/env python3
"""Offline product-fixture gate and historical patch proposal. Never applies patches."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medical_channel_pipeline.ccgp_detail import parse_ccgp_public_tender_html
from medical_channel_pipeline.channel_scope import is_medical_channel_relevant_record
from medical_channel_pipeline.validation import validate_record, validate_records

PARSER_PATH = ROOT / 'medical_channel_pipeline/ccgp_detail.py'
PRODUCT_FIELDS = ('product_items', 'product_categories')
PRODUCT_EVIDENCE_PATHS = {f'facts.{field}' for field in PRODUCT_FIELDS}
MAX_DRY_RUN_RECORDS = 5


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_hash(value: object) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def _audit_inputs(manifest_path: Path, baseline_paths: list[Path]) -> tuple[dict, dict]:
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
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
    results, proposals, parsed = [], [], {}
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
        parsed[case['label']] = record
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
    report = {'schema_version': '0.1', 'mode': 'OFFLINE_AUDIT_AND_PATCH_PROPOSAL_ONLY',
            'fixture_baseline_application_commit': manifest['frozen_against_application_commit'],
            'evaluated_parser_sha256': digest((ROOT / 'medical_channel_pipeline/ccgp_detail.py').read_bytes()),
            'baseline_files': sources, 'baseline_record_count': len(baseline),
            'official_cases': sum(row['kind'] == 'OFFICIAL_ORIGINAL' for row in results),
            'derived_cases': sum(row['kind'] == 'SYNTHETIC_DERIVED_NEGATIVE' for row in results),
            'case_count': len(results), 'passed': len(results) - failures, 'failed': failures,
            'fixture_gate_pass': failures == 0, 'results': results, 'patch_proposals': proposals,
            'apply_allowed': False, 'publishes_snapshot': False, 'writes_runtime_state': False,
            'network_requests': 0, 'interpretation': 'All proposals require separate gate, identity, event and concurrency review; a passing fixture gate alone never authorizes a backfill.'}
    return report, {'baseline': baseline, 'cases': manifest['cases'], 'parsed': parsed,
                    'manifest_sha256': digest(manifest_raw)}


def audit(manifest_path: Path, baseline_paths: list[Path]) -> dict:
    return _audit_inputs(manifest_path, baseline_paths)[0]


def _product_evidence(record: dict) -> list[dict]:
    return [deepcopy(item) for item in record['evidence'] if item['field_path'] in PRODUCT_EVIDENCE_PATHS]


def _unrelated_record(record: dict) -> dict:
    result = deepcopy(record)
    for field in PRODUCT_FIELDS:
        result['facts'].pop(field, None)
    result['evidence'] = [item for item in result['evidence'] if item['field_path'] not in PRODUCT_EVIDENCE_PATHS]
    return result


def build_dry_run(manifest_path: Path, baseline_paths: list[Path], request_path: Path,
                  *, expected_request_sha256: str, expected_scope: dict) -> dict:
    """Build an evidence-complete candidate only, pinned to a separately reviewed request."""
    raw = request_path.read_bytes()
    if digest(raw) != expected_request_sha256:
        raise ValueError('DRY_RUN_REQUEST_HASH_MISMATCH')
    request = json.loads(raw)
    if request.get('schema_version') != '0.1' or request.get('input_kind') != 'FROZEN_REPOSITORY_CANONICAL':
        raise ValueError('DRY_RUN_FROZEN_INPUT_REQUIRED')
    scope = request.get('target_scope')
    if (not isinstance(scope, dict) or scope != expected_scope
            or scope.get('target') != 'preview'
            or not str(scope.get('project_id', '')).startswith('prj_')
            or not str(scope.get('preview_epoch', '')).startswith('mcai-p0-')
            or not str(scope.get('database', '')).startswith('mcai_p0_epoch_')):
        raise ValueError('DRY_RUN_ENVIRONMENT_MISMATCH')
    selected = request.get('selected_records')
    if not isinstance(selected, list) or not 1 <= len(selected) <= MAX_DRY_RUN_RECORDS:
        raise ValueError('DRY_RUN_EXPLICIT_SELECTION_1_TO_5_REQUIRED')
    if any(not isinstance(item, dict) for item in selected):
        raise ValueError('DRY_RUN_DUPLICATE_OR_INVALID_SELECTION')
    ids = [item.get('opportunity_id') for item in selected]
    if any(not isinstance(key, str) or not key for key in ids) or len(ids) != len(set(ids)):
        raise ValueError('DRY_RUN_DUPLICATE_OR_INVALID_SELECTION')
    parser_sha = digest(PARSER_PATH.read_bytes())
    generator_sha = digest(Path(__file__).read_bytes())
    if request.get('parser_sha256') != parser_sha:
        raise ValueError('DRY_RUN_PARSER_VERSION_MISMATCH')
    report, inputs = _audit_inputs(manifest_path, baseline_paths)
    if not report['case_count'] or not report['fixture_gate_pass']:
        raise ValueError('DRY_RUN_FIXTURE_GATE_FAILED')
    if request.get('fixture_manifest_sha256') != inputs['manifest_sha256']:
        raise ValueError('DRY_RUN_MANIFEST_VERSION_MISMATCH')
    source_files = sorted(report['baseline_files'], key=lambda item: item['path'])
    if (len({item['path'] for item in source_files}) != len(source_files)
            or request.get('baseline_files') != source_files):
        raise ValueError('DRY_RUN_BASELINE_VERSION_MISMATCH')
    eligible = {item['opportunity_id']: item for item in report['patch_proposals']}
    changes = []
    for selection in sorted(selected, key=lambda item: item['opportunity_id']):
        key = selection['opportunity_id']
        if key not in eligible:
            raise ValueError('DRY_RUN_SELECTED_ID_NOT_PROPOSED')
        cases = [case for case in inputs['cases'] if case.get('baseline_id') == key and case['kind'] == 'OFFICIAL_ORIGINAL']
        if len(cases) != 1:
            raise ValueError('DRY_RUN_OFFICIAL_IDENTITY_AMBIGUOUS')
        case = cases[0]
        old = inputs['baseline'][key]
        validate_record(old)
        identity = {'opportunity_id': key, 'market_code': old['facts'].get('market_code'),
                    'project_number': old['facts'].get('project_number'),
                    'source_id': old['source']['source_id'], 'source_url': old['source']['url']}
        if selection.get('identity') != identity or not identity['market_code']:
            raise ValueError('DRY_RUN_RECORD_IDENTITY_MISMATCH')
        if selection.get('before_record_sha256') != object_hash(old):
            raise ValueError('DRY_RUN_RECORD_VERSION_MISMATCH')
        if selection.get('official_html_sha256') != case['sha256']:
            raise ValueError('DRY_RUN_OFFICIAL_VERSION_MISMATCH')
        parsed = inputs['parsed'][case['label']]
        candidate = deepcopy(old)
        for field in PRODUCT_FIELDS:
            candidate['facts'][field] = deepcopy(parsed['facts'][field])
        after_evidence = _product_evidence(parsed)
        for field in PRODUCT_FIELDS:
            if candidate['facts'][field] and not any(e['field_path'] == f'facts.{field}' for e in after_evidence):
                raise ValueError('DRY_RUN_PRODUCT_EVIDENCE_REQUIRED')
        candidate['evidence'] = [item for item in candidate['evidence'] if item['field_path'] not in PRODUCT_EVIDENCE_PATHS] + after_evidence
        validate_record(candidate)
        if _unrelated_record(candidate) != _unrelated_record(old):
            raise ValueError('DRY_RUN_NON_WHITELIST_CHANGE')
        before_hash, after_hash = object_hash(old), object_hash(candidate)
        change_identity = {'target_scope': scope, 'identity': identity, 'before_record_sha256': before_hash,
                           'candidate_record_sha256': after_hash, 'official_html_sha256': case['sha256'],
                           'parser_sha256': parser_sha, 'generator_sha256': generator_sha}
        changes.append({**change_identity, 'change_id': object_hash(change_identity),
                        'allowed_fact_fields': list(PRODUCT_FIELDS),
                        'allowed_evidence_paths': sorted(PRODUCT_EVIDENCE_PATHS),
                        'before': {**{field: old['facts'][field] for field in PRODUCT_FIELDS}, 'evidence': _product_evidence(old)},
                        'after': {**{field: candidate['facts'][field] for field in PRODUCT_FIELDS}, 'evidence': after_evidence},
                        'official_provenance': {'fixture_file': case['file'], 'sha256': case['sha256'],
                            'fetched_at': case['fetched_at'], 'locator': case['evidence_locator']},
                        'candidate_record': candidate, 'non_whitelist_content_preserved': True,
                        'source_and_observation_clocks_preserved': True, 'apply_allowed': False})
    # Same source/project under multiple IDs must never become multiple silent corrections.
    validate_records([change['candidate_record'] for change in changes])
    notice_keys = [(change['identity']['market_code'], change['identity']['source_url']) for change in changes]
    if len(notice_keys) != len(set(notice_keys)):
        raise ValueError('DRY_RUN_DUPLICATE_NOTICE_IDENTITY')
    batch_identity = {'request_sha256': expected_request_sha256, 'target_scope': scope,
                      'change_ids': [change['change_id'] for change in changes]}
    return {'schema_version': '0.1', 'mode': 'OFFLINE_PRODUCT_CORRECTION_DRY_RUN',
            'input_kind': 'FROZEN_REPOSITORY_CANONICAL', 'target_scope': scope,
            'scope_binding': 'Reference only; no runtime state accessed',
            'reviewed_request_sha256': expected_request_sha256,
            'fixture_manifest_sha256': inputs['manifest_sha256'], 'parser_sha256': parser_sha,
            'generator_sha256': generator_sha,
            'baseline_files': source_files, 'baseline_record_count': report['baseline_record_count'],
            'fixture_gate': {'passed': report['passed'], 'failed': report['failed']},
            'selection_limit': MAX_DRY_RUN_RECORDS, 'selected_count': len(changes),
            'change_set_id': object_hash(batch_identity), 'changes': changes,
            'apply_allowed': False, 'runtime_canonical_exported': False, 'migration_complete': False,
            'publishes_snapshot': False, 'writes_runtime_state': False, 'network_requests': 0,
            'interpretation': 'Evidence-complete frozen-input proposal only; no runtime CAS, migration, rollback execution or permission to apply.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path, action='append')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--dry-run-request', type=Path)
    parser.add_argument('--expected-request-sha256')
    parser.add_argument('--expected-project-id')
    parser.add_argument('--expected-preview-epoch')
    parser.add_argument('--expected-database')
    args = parser.parse_args()
    if not args.dry_run_request and any([args.expected_request_sha256, args.expected_project_id, args.expected_preview_epoch, args.expected_database]):
        raise ValueError('DRY_RUN_REQUEST_REQUIRED')
    inputs = [args.manifest, *args.baseline]
    manifest = json.loads(args.manifest.read_text())
    inputs.extend(args.manifest.parent / case['file'] for case in manifest['cases'])
    if args.dry_run_request:
        inputs.append(args.dry_run_request)
    if (args.output.resolve() in {path.resolve() for path in inputs}
            or (args.output.exists() and any(path.exists() and args.output.samefile(path) for path in inputs))):
        raise ValueError('OUTPUT_MUST_NOT_OVERWRITE_INPUT')
    if args.dry_run_request:
        if any(not value for value in [args.expected_request_sha256, args.expected_project_id, args.expected_preview_epoch, args.expected_database]):
            raise ValueError('DRY_RUN_INDEPENDENT_SCOPE_AND_REQUEST_LOCK_REQUIRED')
        if any(args.output.resolve().is_relative_to((ROOT / folder).resolve()) for folder in ('data', 'tests/fixtures', 'medical_channel_pipeline', 'scripts')):
            raise ValueError('DRY_RUN_OUTPUT_IN_PROTECTED_INPUT_TREE')
        report = build_dry_run(args.manifest, args.baseline, args.dry_run_request,
            expected_request_sha256=args.expected_request_sha256,
            expected_scope={'project_id': args.expected_project_id, 'target': 'preview',
                            'preview_epoch': args.expected_preview_epoch, 'database': args.expected_database})
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent, delete=False) as artifact:
                temporary = Path(artifact.name)
                artifact.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            os.replace(temporary, args.output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(f"selected={report['selected_count']} mode={report['mode']} apply_allowed=False")
        return 0
    report = audit(args.manifest, args.baseline)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f"cases={report['case_count']} passed={report['passed']} failed={report['failed']} apply_allowed=False")
    return 0 if report['fixture_gate_pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
