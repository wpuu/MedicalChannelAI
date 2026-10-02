#!/usr/bin/env python3
"""Export a bounded, offline-safe summary of a current TMUGH sync report."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from tjmugh_failure_diagnostics import (  # noqa: E402
    PUBLISH_GATE_REASONS,
    REFRESH_OUTCOMES,
    sanitize_failure,
    write_json_atomic,
)

MAX_REPORT_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 50 * 1024
GUIDANCE = (
    'Request the original authorized runner report and HTML, then make a repository fixture '
    'without secrets or private information. Never bypass 403 responses or trigger production.'
)
COUNT_FIELDS = (
    'discovered_supported_count', 'selected_candidate_count', 'new_verified_record_count',
    'existing_record_count', 'merged_record_count', 'missing_selected_count', 'failure_count',
)


def aware_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except ValueError:
        return None


def safe_counts(report: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in COUNT_FIELDS:
        value = report.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1_000_000:
            counts[name] = value
    return counts


def diagnostic_base(status: str, expected_as_of: str, commit: str | None, run_id: str | None) -> dict:
    result = {
        'schema_version': '1',
        'status': status,
        'workflow_result': 'failure',
        'expected_as_of': expected_as_of,
        'guidance': GUIDANCE,
    }
    if commit and re.fullmatch(r'[0-9a-fA-F]{7,40}', commit):
        result['commit'] = commit.lower()
    if run_id and re.fullmatch(r'\d{1,20}', run_id):
        result['run_id'] = run_id
    return result


def build_diagnostic(report_path: Path, expected_as_of: str, commit: str | None = None,
                     run_id: str | None = None) -> dict:
    expected = aware_datetime(expected_as_of)
    if expected is None:
        raise ValueError('--expected-as-of must be an ISO-8601 timestamp with timezone')
    expected_as_of = expected.isoformat()
    if not report_path.is_file():
        return diagnostic_base('REPORT_MISSING', expected_as_of, commit, run_id)
    try:
        with report_path.open('rb') as source:
            raw = source.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError('too large')
        report = json.loads(raw)
        if not isinstance(report, dict):
            raise ValueError('wrong shape')
        if report.get('schema_version') != '0.1' or report.get('source') != 'TJMUGH_PROCUREMENT_INDEX':
            raise ValueError('unsupported report')
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        return diagnostic_base('REPORT_INVALID', expected_as_of, commit, run_id)

    observed = aware_datetime(report.get('observed_at'))
    if observed is None or observed != expected:
        return diagnostic_base('REPORT_NOT_CURRENT', expected_as_of, commit, run_id)

    result = diagnostic_base('REPORT_CURRENT', expected_as_of, commit, run_id)
    result['observed_at'] = observed.isoformat()
    result['counts'] = safe_counts(report)
    gate = report.get('publish_gate_reason')
    outcome = report.get('refresh_outcome')
    if isinstance(gate, str) and gate in PUBLISH_GATE_REASONS:
        result['reported_publish_gate_reason'] = gate
    if isinstance(outcome, str) and outcome in REFRESH_OUTCOMES:
        result['reported_refresh_outcome'] = outcome
    allowed = report.get('publish_allowed')
    if isinstance(allowed, bool):
        result['reported_publish_allowed'] = allowed
    failures = report.get('failures')
    if isinstance(failures, list):
        result['failures'] = [sanitize_failure(item) for item in failures[:50]]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-input', required=True, type=Path)
    parser.add_argument('--expected-as-of', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--commit')
    parser.add_argument('--run-id')
    args = parser.parse_args()
    try:
        diagnostic = build_diagnostic(args.report_input, args.expected_as_of, args.commit, args.run_id)
        write_json_atomic(args.output, diagnostic, max_bytes=MAX_OUTPUT_BYTES)
    except (OSError, ValueError) as exc:
        print(f'TJMUGH_DIAGNOSTIC_EXPORT_FAILED: {type(exc).__name__}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
