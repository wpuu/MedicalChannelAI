#!/usr/bin/env python3
"""Offline whole-batch preflight, memory overlay and rollback. No runtime adapters."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile

from audit_ccgp_product_backfill import (
    ROOT, PRODUCT_FIELDS, build_dry_run, digest,
    object_hash, _unrelated_record,
)
from medical_channel_pipeline.validation import validate_record, validate_records


def _trusted(change_set: dict, *, manifest_path: Path, baseline_paths: list[Path],
             request_path: Path, expected_request_sha256: str, expected_scope: dict) -> tuple[dict, dict]:
    expected = build_dry_run(manifest_path, baseline_paths, request_path,
        expected_request_sha256=expected_request_sha256, expected_scope=expected_scope)
    # Regenerate from the independently locked request; recomputing only supplied hashes is insufficient.
    if change_set != expected:
        raise ValueError('SIM_CHANGE_SET_CONTENT_MISMATCH')
    originals = {}
    locks = {entry['path']: entry['sha256'] for entry in expected['baseline_files']}
    rows = []
    for path in baseline_paths:
        raw = path.read_bytes()
        if locks.get(path.name) != digest(raw):
            raise ValueError('SIM_BASELINE_CHANGED_DURING_PREFLIGHT')
        rows.extend(json.loads(raw))
    validate_records(rows)
    for row in rows:
        originals[row['opportunity_id']] = row
    for change in expected['changes']:
        old = originals[change['identity']['opportunity_id']]
        candidate = change['candidate_record']
        validate_record(candidate)
        if (object_hash(old) != change['before_record_sha256']
                or object_hash(candidate) != change['candidate_record_sha256']
                or _unrelated_record(old) != _unrelated_record(candidate)):
            raise ValueError('SIM_HASH_OR_WHITELIST_MISMATCH')
    return expected, originals


def _state(state: dict, expected_scope: dict, expected_state_sha256: str) -> tuple[str, dict]:
    if (state.get('schema_version') != '0.1' or state.get('input_kind') != 'FROZEN_MEMORY_STATE'
            or state.get('target_scope') != expected_scope):
        raise ValueError('SIM_STATE_SCOPE_OR_KIND_MISMATCH')
    current_hash = object_hash(state)
    if current_hash != expected_state_sha256:
        raise ValueError('SIM_STATE_VERSION_CONFLICT')
    validate_records(state['records'])
    return current_hash, {record['opportunity_id']: record for record in state['records']}


def _positions(changes: list[dict], current: dict) -> list[str]:
    positions = []
    for change in changes:
        record = current.get(change['identity']['opportunity_id'])
        version = object_hash(record) if record is not None else None
        if version == change['before_record_sha256']:
            positions.append('BEFORE')
        elif version == change['candidate_record_sha256']:
            positions.append('AFTER')
        else:
            raise ValueError('SIM_SELECTED_RECORD_VERSION_CONFLICT')
    if len(set(positions)) != 1:
        raise ValueError('SIM_MIXED_BATCH_STATE')
    return positions


def _unchanged(state: dict, version: str) -> None:
    if object_hash(state) != version:
        raise ValueError('SIM_STATE_CHANGED_AFTER_PREFLIGHT')


def _report(status: str, change_set: dict, before_hash: str, after_hash: str,
            changed: int, receipt: dict | None = None) -> dict:
    return {'schema_version': '0.1', 'mode': 'OFFLINE_MEMORY_SIMULATION', 'status': status,
            'change_set_id': change_set['change_set_id'], 'target_scope': change_set['target_scope'],
            'before_state_sha256': before_hash, 'after_state_sha256': after_hash,
            'changed_record_count': changed, 'receipt': receipt,
            'apply_allowed': False, 'runtime_cas_implemented': False,
            'runtime_canonical_exported': False, 'migration_complete': False,
            'database_transaction_executed': False, 'writes_runtime_state': False,
            'network_requests': 0, 'interpretation': 'Memory exercise only; no runtime commit or rollback.'}


def simulate_overlay(change_set: dict, state: dict, *, expected_state_sha256: str,
                     expected_scope: dict, **verification) -> tuple[dict, dict]:
    trusted, _ = _trusted(change_set, expected_scope=expected_scope, **verification)
    state_hash, current = _state(state, expected_scope, expected_state_sha256)
    positions = _positions(trusted['changes'], current)
    _unchanged(state, state_hash)
    if positions[0] == 'AFTER':
        return deepcopy(state), _report('ALREADY_SIMULATED', trusted, state_hash, state_hash, 0)
    # Nothing in the caller's state, or a working copy, is changed until all records pass preflight.
    candidates = {change['identity']['opportunity_id']: change['candidate_record'] for change in trusted['changes']}
    result = deepcopy(state)
    result['records'] = [deepcopy(candidates.get(row['opportunity_id'], row)) for row in state['records']]
    validate_records(result['records'])
    result_hash = object_hash(result)
    receipt_body = {'schema_version': '0.1', 'kind': 'MEMORY_OVERLAY_RECEIPT',
                    'change_set_id': trusted['change_set_id'], 'target_scope': expected_scope,
                    'before_state_sha256': state_hash, 'after_state_sha256': result_hash,
                    'selected_ids': sorted(candidates), 'apply_allowed': False}
    receipt = {**receipt_body, 'receipt_id': object_hash(receipt_body)}
    _unchanged(state, state_hash)
    return result, _report('SIMULATED_APPLIED', trusted, state_hash, result_hash, len(candidates), receipt)


def simulate_rollback(change_set: dict, state: dict, receipt: dict, *,
                      expected_receipt_sha256: str, expected_scope: dict, **verification) -> tuple[dict, dict]:
    trusted, originals = _trusted(change_set, expected_scope=expected_scope, **verification)
    if object_hash(receipt) != expected_receipt_sha256:
        raise ValueError('SIM_RECEIPT_VERSION_MISMATCH')
    body = {key: value for key, value in receipt.items() if key != 'receipt_id'}
    if (receipt.get('receipt_id') != object_hash(body)
            or receipt.get('kind') != 'MEMORY_OVERLAY_RECEIPT'
            or receipt.get('schema_version') != '0.1'
            or receipt.get('apply_allowed') is not False
            or receipt.get('target_scope') != expected_scope
            or receipt.get('change_set_id') != trusted['change_set_id']
            or receipt.get('selected_ids') != sorted(change['identity']['opportunity_id'] for change in trusted['changes'])):
        raise ValueError('SIM_RECEIPT_BINDING_MISMATCH')
    actual_hash = object_hash(state)
    if actual_hash not in {receipt['after_state_sha256'], receipt['before_state_sha256']}:
        raise ValueError('SIM_ROLLBACK_STATE_VERSION_CONFLICT')
    state_hash, current = _state(state, expected_scope, actual_hash)
    positions = _positions(trusted['changes'], current)
    _unchanged(state, state_hash)
    if actual_hash == receipt['before_state_sha256'] and positions[0] == 'BEFORE':
        return deepcopy(state), _report('ALREADY_RESTORED', trusted, state_hash, state_hash, 0)
    if actual_hash != receipt['after_state_sha256'] or positions[0] != 'AFTER':
        raise ValueError('SIM_ROLLBACK_RECORD_STATE_CONFLICT')
    restored = {}
    for change in trusted['changes']:
        key = change['identity']['opportunity_id']
        old = originals[key]
        row = deepcopy(current[key])
        for field in PRODUCT_FIELDS:
            row['facts'][field] = deepcopy(old['facts'][field])
        row['evidence'] = deepcopy(old['evidence'])
        if (_unrelated_record(row) != _unrelated_record(current[key])
                or object_hash(row) != change['before_record_sha256']):
            raise ValueError('SIM_ROLLBACK_WHITELIST_OR_HASH_MISMATCH')
        restored[key] = row
    result = deepcopy(state)
    result['records'] = [deepcopy(restored.get(row['opportunity_id'], row)) for row in state['records']]
    validate_records(result['records'])
    if object_hash(result) != receipt['before_state_sha256']:
        raise ValueError('SIM_ROLLBACK_WHOLE_STATE_MISMATCH')
    _unchanged(state, state_hash)
    return result, _report('SIMULATED_RESTORED', trusted, state_hash, object_hash(result), len(restored))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'request', 'change-set', 'state', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--baseline', type=Path, action='append', required=True)
    for name in ('expected-request-sha256', 'expected-state-sha256', 'expected-project-id', 'expected-preview-epoch', 'expected-database'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    inputs = [args.manifest, args.request, args.change_set, args.state, *args.baseline]
    inputs.extend(args.manifest.parent / case['file'] for case in json.loads(args.manifest.read_text())['cases'])
    if (args.output.resolve() in {p.resolve() for p in inputs}
            or any(args.output.resolve().is_relative_to((ROOT / folder).resolve())
                   for folder in ('data', 'tests/fixtures', 'medical_channel_pipeline', 'scripts'))
            or (args.output.exists() and any(args.output.samefile(p) for p in inputs))):
        raise ValueError('SIM_OUTPUT_OVERWRITES_PROTECTED_INPUT')
    destination = args.output.resolve()
    project = ROOT.parents[1].resolve()
    if destination.is_relative_to(project):
        if not destination.is_relative_to(project / 'docs/project/validation') or destination.exists():
            raise ValueError('SIM_OUTPUT_OUTSIDE_NEW_ARTIFACT_AREA')
    elif not destination.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError('SIM_OUTPUT_OUTSIDE_NEW_ARTIFACT_AREA')
    scope = {'project_id': args.expected_project_id, 'target': 'preview',
             'preview_epoch': args.expected_preview_epoch, 'database': args.expected_database}
    change_set = json.loads(args.change_set.read_text())
    state = json.loads(args.state.read_text())
    verification = {'manifest_path': args.manifest, 'baseline_paths': args.baseline,
                    'request_path': args.request, 'expected_request_sha256': args.expected_request_sha256,
                    'expected_scope': scope}
    after, applied = simulate_overlay(change_set, state, expected_state_sha256=args.expected_state_sha256, **verification)
    if applied['status'] != 'SIMULATED_APPLIED':
        raise ValueError('SIM_ROUNDTRIP_REQUIRES_BEFORE_STATE')
    _, replayed = simulate_overlay(change_set, after, expected_state_sha256=object_hash(after), **verification)
    restored, rolled_back = simulate_rollback(change_set, after, applied['receipt'],
        expected_receipt_sha256=object_hash(applied['receipt']), **verification)
    _, rollback_replayed = simulate_rollback(change_set, restored, applied['receipt'],
        expected_receipt_sha256=object_hash(applied['receipt']), **verification)
    if restored != state:
        raise ValueError('SIM_ROUNDTRIP_NOT_IDENTICAL')
    report = {'mode': 'OFFLINE_MEMORY_ROUNDTRIP', 'overlay': applied, 'overlay_replay': replayed,
              'rollback': rolled_back, 'rollback_replay': rollback_replayed,
              'whole_state_restored': True, 'record_count': len(state['records']),
              'apply_allowed': False, 'runtime_cas_implemented': False, 'network_requests': 0}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        os.replace(temporary, args.output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print('Memory roundtrip PASS; apply_allowed=False; runtime_cas_implemented=False')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
