"""Exercise the actual bootstrap CLI offline; every network result is replaced by frozen official bytes."""
from contextlib import ExitStack, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'web/pipeline'))
sys.path.insert(0, str(ROOT / 'web/pipeline/scripts'))
import bootstrap_ccgp_backfill as target

CORPUS = ROOT / 'web/pipeline/tests/fixtures/ccgp_template_audit_20261106'
cases = json.loads((CORPUS / 'manifest.json').read_text())['cases']
selected = [next(c for c in cases if c['label'] == label) for label in ('ccgp_he_2a9ca892bf9d0b6a', 'ccgp_hl_b36866ded1fc3097')]
pages = {c['url']: (CORPUS / c['file']).read_bytes().decode(c['encoding']) for c in selected}
candidates = [('公开招标', SimpleNamespace(detail_url=c['url'], title=c['label'], published_at='2026-09-08')) for c in selected]
results = []
for scenario in ('all_verified_control', 'one_detail_failed', 'one_discovery_query_failed'):
    with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
        folder = Path(temp)
        def discover(**kwargs):
            if scenario == 'one_discovery_query_failed' and kwargs['keyword'] == 'second':
                kwargs['failures'].append({'stage': 'discovery_search', 'error': 'OFFLINE_INJECTED_SEARCH_FAILURE'})
                return []
            return candidates
        def fetch(url):
            if scenario == 'one_detail_failed' and url == selected[1]['url']:
                raise RuntimeError('OFFLINE_INJECTED_DETAIL_FAILURE')
            return pages[url]
        stack.enter_context(patch.object(target, 'load_plan', return_value={'region': '天津', 'delay_seconds': 0, 'keywords': ['first', 'second'], 'notice_types': ['公开招标']}))
        stack.enter_context(patch.object(target, 'load_array', return_value=[]))
        stack.enter_context(patch.object(target, 'discover_candidates', side_effect=discover))
        stack.enter_context(patch.object(target, 'fetch_ccgp_detail_html', side_effect=fetch))
        # Isolate this CLI's candidate-completeness gate from the separate event-watch gate.
        stack.enter_context(patch.object(target, 'active_ccgp_project_numbers', return_value=[]))
        stack.enter_context(patch.object(target.time, 'sleep', return_value=None))
        argv = ['bootstrap', '--as-of', '2026-11-06T08:50:53+00:00', '--lookback-days', '1',
                '--records-output', str(folder / 'records.json'), '--events-output', str(folder / 'events.json'),
                '--report-output', str(folder / 'report.json')]
        stack.enter_context(patch.object(sys, 'argv', argv))
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = target.main()
        report = json.loads((folder / 'report.json').read_text())
        results.append({'scenario': scenario, 'exit_code': code,
                        'expected_acceptance_ready': scenario == 'all_verified_control',
                        'actual_acceptance_ready': report['acceptance_ready'],
                        'selected_count': report['selected_candidate_count'],
                        'verified_count': report['new_verified_record_count'],
                        'detail_failure_count': report['verified_detail_failure_count'],
                        'planned_discovery_count': report['planned_discovery_query_count'],
                        'successful_discovery_count': report['discovery_success_count'],
                        'stdout': stdout.getvalue().strip()})
assert results[0]['actual_acceptance_ready'] is True
for result in results:
    result['pass'] = result['actual_acceptance_ready'] == result['expected_acceptance_ready']
failures = sum(not result['pass'] for result in results)
print(json.dumps({'mode': 'ACTUAL_BOOTSTRAP_CLI_WITH_OFFLINE_BOUNDARY_STUBS',
                  'network_requests': 0, 'runtime_or_database_writes': False,
                  'candidate_files_written_only_to_temporary_directory': True,
                  'limitation': 'Event-watch list isolated to empty; proves candidate/discovery gates only, not end-to-end event semantics.',
                  'passed': len(results) - failures, 'failed': failures,
                  'gate_pass': failures == 0, 'results': results}, ensure_ascii=False, indent=2))
raise SystemExit(2 if failures else 0)
