from contextlib import ExitStack, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import bootstrap_ccgp_backfill as target

CORPUS = ROOT / 'tests/fixtures/ccgp_template_audit_20261106'
CASES = json.loads((CORPUS / 'manifest.json').read_text())['cases']
SELECTED = [next(c for c in CASES if c['label'] == name) for name in ('ccgp_he_2a9ca892bf9d0b6a', 'ccgp_hl_b36866ded1fc3097')]


class BootstrapCompletenessTests(unittest.TestCase):
    def run_cli(self, mode, *, candidate_cap=200, watch_cap=100):
        candidates = [('公开招标', SimpleNamespace(detail_url=c['url'], title=c['label'], published_at='2026-09-08')) for c in SELECTED]
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            folder = Path(temp)

            def discover(**kwargs):
                if mode == 'all_discovery_failed' or (mode == 'one_discovery_failed' and kwargs['keyword'] == 'second'):
                    kwargs['failures'].append({'stage':'discovery_search','error':'OFFLINE_SEARCH_FAILED'})
                    return []
                return [] if mode == 'empty_success' else candidates

            def fetch(url):
                if mode == 'all_detail_failed' or (mode == 'one_detail_failed' and url == SELECTED[1]['url']):
                    raise RuntimeError('OFFLINE_DETAIL_FAILED')
                case = next(c for c in SELECTED if c['url'] == url)
                return (CORPUS / case['file']).read_bytes().decode(case['encoding'])

            def events(project_number, **kwargs):
                if mode == 'one_event_query_failed' and project_number == 'PROJECT-A':
                    kwargs['failures'].append({'stage':'event_search','project_number':project_number,'error':'OFFLINE_EVENT_SEARCH_FAILED'})
                return []

            watches = ['PROJECT-A','PROJECT-B'] if mode in ('watch_cap','one_event_query_failed','event_empty_success') else []
            stack.enter_context(patch.object(target, 'load_plan', return_value={'region':'天津','delay_seconds':0,'keywords':['first','second'],'notice_types':['公开招标']}))
            stack.enter_context(patch.object(target, 'load_array', return_value=[]))
            stack.enter_context(patch.object(target, 'discover_candidates', side_effect=discover))
            stack.enter_context(patch.object(target, 'fetch_ccgp_detail_html', side_effect=fetch))
            stack.enter_context(patch.object(target, 'active_ccgp_project_numbers', return_value=watches))
            event_mock = stack.enter_context(patch.object(target, 'scan_events', side_effect=events))
            stack.enter_context(patch.object(target.time, 'sleep', return_value=None))
            stack.enter_context(patch.object(sys,'argv',['bootstrap','--as-of','2026-11-06T11:05:33+00:00',
                '--lookback-days','1','--max-candidates',str(candidate_cap),'--max-event-watch-projects',str(watch_cap),
                '--records-output',str(folder/'records.json'),'--events-output',str(folder/'events.json'),'--report-output',str(folder/'report.json')]))
            with redirect_stdout(StringIO()):
                code = target.main()
            return code, json.loads((folder/'report.json').read_text()), json.loads((folder/'records.json').read_text()), event_mock.call_count

    def test_all_queries_and_details_verified_pass(self):
        code, report, records, _ = self.run_cli('all_success')
        self.assertEqual(code,0)
        self.assertTrue(report['acceptance_ready'])
        self.assertFalse(report['partial_candidate_output'])
        self.assertEqual(len(records),2)

    def test_complete_empty_discovery_is_accepted(self):
        code, report, records, _ = self.run_cli('empty_success')
        self.assertEqual(code,0)
        self.assertTrue(report['acceptance_ready'])
        self.assertEqual(report['discovery_success_count'], report['planned_discovery_query_count'])
        self.assertEqual(records,[])

    def test_one_failed_detail_cannot_be_hidden_by_verified_sibling(self):
        code, report, records, _ = self.run_cli('one_detail_failed')
        self.assertEqual(code,2)
        self.assertFalse(report['acceptance_ready'])
        self.assertTrue(report['partial_candidate_output'])
        self.assertEqual(len(records),1)

    def test_all_failed_details_are_rejected(self):
        code, report, records, _ = self.run_cli('all_detail_failed')
        self.assertEqual(code,2)
        self.assertFalse(report['acceptance_ready'])
        self.assertEqual(records,[])

    def test_one_failed_discovery_query_blocks_acceptance(self):
        code, report, records, _ = self.run_cli('one_discovery_failed')
        self.assertEqual(code,2)
        self.assertFalse(report['acceptance_ready'])
        self.assertEqual(len(records),2)

    def test_all_failed_discovery_queries_are_not_a_valid_empty_set(self):
        code, report, records, _ = self.run_cli('all_discovery_failed')
        self.assertEqual(code,2)
        self.assertFalse(report['acceptance_ready'])
        self.assertEqual(records,[])

    def test_candidate_cap_blocks_partial_selection(self):
        code, report, records, _ = self.run_cli('all_success',candidate_cap=1)
        self.assertEqual(code,2)
        self.assertTrue(report['candidate_cap_exceeded'])
        self.assertEqual(len(records),1)

    def test_watch_cap_blocks_partial_event_coverage(self):
        code, report, _, calls = self.run_cli('watch_cap',watch_cap=1)
        self.assertEqual(code,2)
        self.assertTrue(report['event_watch_cap_exceeded'])
        self.assertEqual(calls,1)

    def test_single_failed_event_query_blocks_acceptance(self):
        code, report, _, calls = self.run_cli('one_event_query_failed')
        self.assertEqual(code,2)
        self.assertFalse(report['acceptance_ready'])
        self.assertEqual(report['event_search_blocked_projects'],['PROJECT-A'])
        self.assertEqual(calls,2)

    def test_successful_nonempty_watch_with_no_new_events_is_valid(self):
        code, report, _, calls = self.run_cli('event_empty_success')
        self.assertEqual(code,0)
        self.assertTrue(report['acceptance_ready'])
        self.assertEqual(report['new_notice_event_count'],0)
        self.assertEqual(calls,2)
