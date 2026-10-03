from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from medical_channel_pipeline.ccgp_discovery import DiscoveryCandidate

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PIPELINE_ROOT / 'scripts'
sys.path.insert(0, str(SCRIPT_DIR))


def load_script(module_name: str):
    path = SCRIPT_DIR / f'{module_name}.py'
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'STANDALONE_SCRIPT_IMPORT_FAILED:{module_name}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPTS = {
    name: load_script(name)
    for name in (
        'sync_tianjin_plan',
        'sync_regional_ccgp',
        'sync_tjnothop_market_research',
        'sync_teda_market_research',
        'sync_tjzxfc_market_research',
        'sync_tjzyefy_market_research',
        'sync_tjzyefy_procurement_intent',
        'sync_tjfch_procurement',
        'sync_tjfch_test_recruitment',
        'sync_ccgp_query',
    )
}
NETWORK_BOUNDARIES = {
    'sync_tianjin_plan': ('discover_candidates',),
    'sync_regional_ccgp': ('fetch_candidates_page',),
    'sync_tjnothop_market_research': ('fetch_tjnothop_page',),
    'sync_teda_market_research': ('discover_candidates', 'fetch_teda_page'),
    'sync_tjzxfc_market_research': ('fetch_tjzxfc_page', 'fetch_page_with_retry'),
    'sync_tjzyefy_market_research': ('fetch_tjzyefy_page', 'fetch_page_with_retry'),
    'sync_tjzyefy_procurement_intent': ('fetch_tjzyefy_page', 'fetch_page_with_retry'),
    'sync_tjfch_procurement': ('fetch_tjfch_page',),
    'sync_tjfch_test_recruitment': ('fetch_tjfch_page',),
    'sync_ccgp_query': ('fetch_search_page',),
}


class IndependentScriptPublicationTests(unittest.TestCase):
    def candidate(self, detail_url='https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/offline-test.htm'):
        return SimpleNamespace(
            title='天津医院医疗设备采购项目公开招标公告',
            detail_url=detail_url,
            published_at='2026-10-02',
            index_url='https://example.invalid/index',
        )

    def historical_record_bytes(self, *, opportunity_id: str | None = None, count: int = 1) -> bytes:
        seeds = json.loads((PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json').read_text(encoding='utf-8'))
        records = deepcopy(seeds[:count])
        if opportunity_id is not None:
            records[0]['opportunity_id'] = opportunity_id
        return (' \n' + json.dumps(records, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')

    def run_failure(
        self,
        module_name: str,
        patches: list[tuple[str, dict]],
        *,
        events: bool = False,
        existing_records: bool = True,
        existing_events: bool = True,
        records_before: bytes | None = None,
        expected_gate_reason: str | None = None,
    ):
        module = SCRIPTS[module_name]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = root / 'records.json'
            report = root / 'report.json'
            records_before = records_before if records_before is not None else self.historical_record_bytes()
            if existing_records:
                records.write_bytes(records_before)
            events_path = root / 'events.json'
            events_before = b'[ ]\n'
            if events and existing_events:
                events_path.write_bytes(events_before)
            args = [
                str(SCRIPT_DIR / f'{module_name}.py'),
                '--as-of', '2026-10-03T00:00:00Z',
                '--records-output', str(records),
                '--report-output', str(report),
            ]
            if existing_records:
                args.extend(['--existing-records-input', str(records)])
            if events:
                if existing_events:
                    args.extend(['--existing-events-input', str(events_path)])
                args.extend(['--events-output', str(events_path)])
            if module_name == 'sync_ccgp_query':
                args.extend(['--keyword', '医院', '--start-date', '2026-10-01', '--end-date', '2026-10-03'])
            stderr = io.StringIO()
            with ExitStack() as stack:
                stack.enter_context(patch.object(module.sys, 'argv', args))
                stack.enter_context(patch.object(module.time, 'sleep'))
                for attribute, settings in patches:
                    stack.enter_context(patch.object(module, attribute, **settings))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                stack.enter_context(contextlib.redirect_stderr(stderr))
                result = module.main()
            report_payload = json.loads(report.read_text(encoding='utf-8'))
            if existing_records:
                self.assertEqual(records.read_bytes(), records_before)
            else:
                self.assertFalse(records.exists())
            if events:
                if existing_events:
                    self.assertEqual(events_path.read_bytes(), events_before)
                else:
                    self.assertFalse(events_path.exists())
            self.assertFalse(report_payload['publish_allowed'])
            self.assertNotEqual(report_payload['publish_gate_reason'], 'PASS')
            if expected_gate_reason is not None:
                self.assertEqual(report_payload['publish_gate_reason'], expected_gate_reason)
            self.assertTrue(report_payload['failures'])
            self.assertFalse(report_payload['records_output_written'])
            self.assertEqual(report_payload['records_output_status'], 'PRESERVED_UNCHANGED')
            self.assertEqual(report_payload['merged_record_count'], report_payload['existing_record_count'])
            if events:
                self.assertFalse(report_payload['events_output_written'])
                self.assertEqual(report_payload['events_output_status'], 'PRESERVED_UNCHANGED')
            self.assertEqual(result, 2)
            return report_payload, stderr.getvalue()

    def test_tianjin_plan_detail_failure_preserves_records_and_events(self):
        item = self.candidate()
        original_load_plan = SCRIPTS['sync_tianjin_plan'].load_plan

        def one_project_watch_plan(path):
            plan = original_load_plan(path)
            plan['max_event_watch_projects'] = 1
            return plan

        self.run_failure('sync_tianjin_plan', [
            ('load_plan', {'side_effect': one_project_watch_plan}),
            ('discover_candidates', {'return_value': [('公开招标', item)]}),
            ('fetch_ccgp_detail_html', {'side_effect': RuntimeError('OFFLINE_DETAIL_FAILURE')}),
            ('scan_events', {'return_value': []}),
            ('active_ccgp_project_numbers', {'return_value': ['PROJECT-ONE', 'PROJECT-TWO']}),
        ], events=True, records_before=self.historical_record_bytes(count=2), expected_gate_reason='ALL_SELECTED_DETAILS_FAILED_VERIFICATION')

    def test_tianjin_plan_blocked_refresh_does_not_create_missing_outputs(self):
        item = self.candidate()
        report, _stderr = self.run_failure('sync_tianjin_plan', [
            ('discover_candidates', {'return_value': [('公开招标', item)]}),
            ('fetch_ccgp_detail_html', {'side_effect': RuntimeError('OFFLINE_DETAIL_FAILURE')}),
            ('scan_events', {'return_value': []}),
        ], events=True, existing_records=False, existing_events=False)
        self.assertEqual(report['existing_record_count'], 0)

    def test_tjnothop_detail_failure_preserves_records(self):
        item = self.candidate()
        self.run_failure('sync_tjnothop_market_research', [
            ('fetch_tjnothop_page', {'side_effect': ['offline-index', RuntimeError('OFFLINE_DETAIL_FAILURE')]}),
            ('parse_tjnothop_index_html', {'return_value': [item]}),
            ('select_candidates_since', {'return_value': [item]}),
        ])

    def test_teda_detail_failure_preserves_records(self):
        item = self.candidate()
        self.run_failure('sync_teda_market_research', [
            ('discover_candidates', {'return_value': [item]}),
            ('fetch_page_with_retry', {'side_effect': RuntimeError('OFFLINE_DETAIL_FAILURE')}),
        ])

    def test_tjzxfc_detail_failure_preserves_records(self):
        item = self.candidate('https://www.tjzxfc.cn/system/2026/10/02/123456.shtml')
        opportunity_id = SCRIPTS['sync_tjzxfc_market_research'].stable_opportunity_id(item.detail_url)
        self.run_failure('sync_tjzxfc_market_research', [
            ('fetch_page_with_retry', {'side_effect': ['offline-index', RuntimeError('OFFLINE_DETAIL_FAILURE')]}),
            ('parse_tjzxfc_index_html', {'return_value': [item]}),
            ('select_candidates_since', {'return_value': [item]}),
        ], records_before=self.historical_record_bytes(opportunity_id=opportunity_id), expected_gate_reason='NO_SELECTED_DETAIL_VERIFIED')

    def test_tjzyefy_market_research_detail_failure_preserves_records(self):
        item = self.candidate('https://www.tjzyefy.com/system/2026/10/02/123456.shtml')
        opportunity_id = SCRIPTS['sync_tjzyefy_market_research'].stable_opportunity_id(item.detail_url)
        self.run_failure('sync_tjzyefy_market_research', [
            ('fetch_page_with_retry', {'side_effect': ['offline-index', RuntimeError('OFFLINE_DETAIL_FAILURE')]}),
            ('parse_tjzyefy_index_html', {'return_value': [item]}),
            ('select_candidates_since', {'return_value': [item]}),
        ], records_before=self.historical_record_bytes(opportunity_id=opportunity_id), expected_gate_reason='NO_SELECTED_DETAIL_VERIFIED')

    def test_tjzyefy_procurement_intent_detail_failure_preserves_records(self):
        item = self.candidate('https://www.tjzyefy.com/system/2026/10/02/123456.shtml')
        opportunity_id = SCRIPTS['sync_tjzyefy_procurement_intent'].stable_intent_opportunity_id(item.detail_url)
        self.run_failure('sync_tjzyefy_procurement_intent', [
            ('fetch_page_with_retry', {'side_effect': ['offline-index', RuntimeError('OFFLINE_DETAIL_FAILURE')]}),
            ('parse_tjzyefy_intent_index_html', {'return_value': [item]}),
            ('select_intent_candidates_since', {'return_value': [item]}),
        ], records_before=self.historical_record_bytes(opportunity_id=opportunity_id), expected_gate_reason='NO_SELECTED_DETAIL_VERIFIED')

    def test_tjfch_procurement_detail_failure_preserves_records(self):
        item = self.candidate()
        self.run_failure('sync_tjfch_procurement', [
            ('fetch_tjfch_page', {'side_effect': ['offline-index', RuntimeError('OFFLINE_DETAIL_FAILURE')]}),
            ('parse_tjfch_index_html', {'return_value': [item]}),
            ('select_candidates_since', {'return_value': [item]}),
        ])

    def test_tjfch_test_recruitment_detail_failure_preserves_records(self):
        item = self.candidate()
        self.run_failure('sync_tjfch_test_recruitment', [
            ('fetch_tjfch_page', {'side_effect': ['offline-index', RuntimeError('OFFLINE_DETAIL_FAILURE')]}),
            ('parse_tjfch_test_index_html', {'return_value': [item]}),
        ])

    def run_ccgp_query(self, *, records, events, report, extra_patches):
        module = SCRIPTS['sync_ccgp_query']
        argv = [
            str(SCRIPT_DIR / 'sync_ccgp_query.py'), '--keyword', '医院',
            '--start-date', '2026-10-01', '--end-date', '2026-10-03',
            '--existing-records-input', str(records), '--records-output', str(records),
            '--existing-events-input', str(events), '--events-output', str(events),
            '--report-output', str(report),
        ]
        with ExitStack() as stack:
            stack.enter_context(patch.object(module.sys, 'argv', argv))
            stack.enter_context(patch.object(module.time, 'sleep'))
            for attribute, settings in extra_patches:
                stack.enter_context(patch.object(module, attribute, **settings))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            return module.main()

    def test_ccgp_all_discovery_failure_preserves_records_and_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, events, report = root / 'records.json', root / 'events.json', root / 'report.json'
            records_before = self.historical_record_bytes()
            events_before = b'[ ]\n'
            records.write_bytes(records_before)
            events.write_bytes(events_before)

            def failed_discovery(**kwargs):
                kwargs['failures'].extend([
                    {'stage': 'discovery_search', 'notice_type': notice_type, 'error': 'RuntimeError', 'message': 'OFFLINE_QUERY_FAILURE'}
                    for notice_type in kwargs['notice_types']
                ])
                return []

            result = self.run_ccgp_query(
                records=records, events=events, report=report,
                extra_patches=[
                    ('discover_candidates', {'side_effect': failed_discovery}),
                    ('scan_events', {'side_effect': AssertionError('BLOCKED_RUN_MUST_NOT_REFRESH_EVENTS')}),
                ],
            )
            payload = json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(result, 2)
            self.assertEqual(records.read_bytes(), records_before)
            self.assertEqual(events.read_bytes(), events_before)
            self.assertFalse(payload['publish_allowed'])
            self.assertEqual(payload['publish_gate_reason'], 'ALL_DISCOVERY_QUERIES_FAILED')
            self.assertEqual(payload['discovery_success_count'], 0)
            self.assertFalse(payload['records_output_written'])
            self.assertFalse(payload['events_output_written'])
            self.assertEqual(payload['failures'][0]['message'], 'OFFLINE_QUERY_FAILURE')

    def test_ccgp_successful_empty_and_filtered_empty_searches_remain_publishable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filtered in (False, True):
                with self.subTest(filtered=filtered):
                    records, events, report = root / f'records-{filtered}.json', root / f'events-{filtered}.json', root / f'report-{filtered}.json'
                    records.write_bytes(self.historical_record_bytes())
                    events.write_bytes(b'[ ]\n')
                    patches = [('active_ccgp_project_numbers', {'return_value': []})]
                    if filtered:
                        excluded = DiscoveryCandidate(
                            title='某医院中标公告',
                            detail_url='https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202610/excluded.htm',
                            published_at='2026-10-02', buyer_name='某医院', region='天津市',
                            notice_type='中标公告', search_keyword='医院',
                        )
                        patches.extend([
                            ('fetch_search_page', {'return_value': 'offline-index'}),
                            ('parse_search_html', {'return_value': [excluded]}),
                        ])
                    else:
                        patches.append(('discover_candidates', {'return_value': []}))
                    result = self.run_ccgp_query(records=records, events=events, report=report, extra_patches=patches)
                    payload = json.loads(report.read_text(encoding='utf-8'))
                    self.assertEqual(result, 0)
                    self.assertTrue(payload['publish_allowed'])
                    self.assertEqual(payload['publish_gate_reason'], 'PASS')
                    self.assertTrue(payload['records_output_written'])
                    self.assertTrue(payload['events_output_written'])
                    self.assertEqual(payload['candidate_count'], 0)

    def test_ccgp_partial_detail_success_remains_publishable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, events, report = root / 'records.json', root / 'events.json', root / 'report.json'
            records.write_bytes(self.historical_record_bytes())
            events.write_bytes(b'[ ]\n')
            urls = [
                'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/good.htm',
                'https://www.ccgp.gov.cn/cggg/dfgg/jzxcs/202610/fail.htm',
            ]
            candidates = [
                ('公开招标', DiscoveryCandidate('医院医疗设备采购项目公开招标公告', urls[0], '2026-10-02', '天津医院', '天津市', '公开招标', '医院')),
                ('竞争性磋商', DiscoveryCandidate('医院检验设备采购项目竞争性磋商公告', urls[1], '2026-10-02', '天津医院', '天津市', '竞争性磋商', '医院')),
            ]
            template = json.loads((PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json').read_text(encoding='utf-8'))[0]

            def adapter(_html, *, source_url, observed_at, opportunity_id):
                record = deepcopy(template)
                record['opportunity_id'] = opportunity_id
                record['source']['source_id'] = f'ccgp:offline:{opportunity_id}'
                record['source']['url'] = source_url
                record['source']['observed_at'] = observed_at
                for evidence in record['evidence']:
                    evidence['source_url'] = source_url
                return record

            result = self.run_ccgp_query(
                records=records, events=events, report=report,
                extra_patches=[
                    ('discover_candidates', {'return_value': candidates}),
                    ('fetch_ccgp_detail_html', {'side_effect': ['offline-valid-fixture', RuntimeError('OFFLINE_SECOND_DETAIL_FAILURE')]}),
                    ('active_ccgp_project_numbers', {'return_value': []}),
                    ('VERIFIED_NOTICE_ADAPTERS', {'new': {'公开招标': adapter, '竞争性磋商': adapter}}),
                ],
            )
            payload = json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(result, 0)
            self.assertTrue(payload['publish_allowed'])
            self.assertEqual(payload['publish_gate_reason'], 'PASS')
            self.assertEqual(payload['candidate_count'], 2)
            self.assertEqual(payload['new_verified_record_count'], 1)
            self.assertEqual(payload['failure_count'], 1)
            self.assertTrue(payload['records_output_written'])

    def test_every_script_rejects_report_alias_before_fetching(self):
        for module_name, module in SCRIPTS.items():
            with self.subTest(script=module_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                records = root / 'records.json'
                before = self.historical_record_bytes()
                records.write_bytes(before)
                args = [
                    str(SCRIPT_DIR / f'{module_name}.py'),
                    '--existing-records-input', str(records),
                    '--records-output', str(records),
                    '--report-output', str(records),
                ]
                if module_name != 'sync_ccgp_query':
                    args.extend(['--as-of', '2026-10-03T00:00:00Z'])
                if module_name in {'sync_tianjin_plan', 'sync_ccgp_query'}:
                    if module_name in {'sync_tianjin_plan', 'sync_ccgp_query'}:
                        events = root / 'events.json'
                        events.write_bytes(b'[]\n')
                        args.extend(['--existing-events-input', str(events), '--events-output', str(events)])
                if module_name == 'sync_ccgp_query':
                    args.extend(['--keyword', '医院', '--start-date', '2026-10-01', '--end-date', '2026-10-03'])
                with ExitStack() as stack:
                    stack.enter_context(patch.object(module.sys, 'argv', args))
                    for boundary in NETWORK_BOUNDARIES[module_name]:
                        if hasattr(module, boundary):
                            stack.enter_context(patch.object(module, boundary, side_effect=AssertionError('NETWORK_BOUNDARY_REACHED')))
                    with self.assertRaisesRegex(ValueError, 'alias'):
                        module.main()
                self.assertEqual(records.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
