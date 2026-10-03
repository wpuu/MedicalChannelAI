from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from medical_channel_pipeline.ccgp_discovery import DiscoveryCandidate

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / 'scripts' / 'sync_regional_ccgp.py'

spec = importlib.util.spec_from_file_location('sync_regional_ccgp', SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError('SYNC_REGIONAL_CCGP_IMPORT_FAILED')
sync_regional = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_regional)


class RegionalCcgpSyncTests(unittest.TestCase):
    def historical_record(self):
        return json.loads((PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json').read_text(encoding='utf-8'))[0]

    def canonical_existing_bytes(self):
        return (' \n' + json.dumps([self.historical_record()], ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')

    def candidate(self, code: str) -> DiscoveryCandidate:
        market = {'BJ': ('北京', '北京市'), 'HE': ('河北', '河北省')}[code]
        name, region = market
        return DiscoveryCandidate(
            title=f'{name}医院医疗设备采购项目公开招标公告',
            detail_url=f'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/{code.lower()}.htm',
            published_at='2026-10-03',
            buyer_name=f'{name}医院',
            region=region,
            notice_type='公开招标',
            search_keyword='医疗',
        )

    def run_sync(self, scoped_candidates, detail_results, *, existing_bytes=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / 'plan.json'
            records_path = root / 'records.json'
            report_path = root / 'report.json'
            plan_path.write_text(json.dumps({
                'schema_version': '0.1',
                'markets': [
                    {'market_code': 'BJ', 'name': '北京', 'admin_code': '110000', 'ccgp_zone_id': '11'},
                    {'market_code': 'HE', 'name': '河北', 'admin_code': '130000', 'ccgp_zone_id': '13'},
                ],
                'keywords': ['医疗'],
                'notice_types': ['公开招标'],
                'lookback_days': 3,
                'max_candidates_per_market': 10,
                'delay_seconds': 3.0,
            }, ensure_ascii=False), encoding='utf-8')
            records_path.write_bytes(existing_bytes if existing_bytes is not None else self.canonical_existing_bytes())
            argv = [
                str(SCRIPT_PATH), '--plan', str(plan_path), '--as-of', '2026-10-03T00:00:00Z',
                '--records-output', str(records_path), '--existing-records-input', str(records_path),
                '--report-output', str(report_path),
            ]

            def fetch_candidates(_session, *, region, **_kwargs):
                if region is None:
                    return []
                return [("公开招标", item) for item in scoped_candidates.get(region, [])]

            def fetch_detail(url):
                result = detail_results[url]
                if isinstance(result, Exception):
                    raise result
                return '<offline-detail>'

            template_record = self.historical_record()

            def adapter(_html, **kwargs):
                record = deepcopy(template_record)
                record['opportunity_id'] = kwargs['opportunity_id']
                record['source']['source_id'] = f"ccgp:offline:{kwargs['opportunity_id']}"
                record['source']['url'] = kwargs['source_url']
                for evidence in record['evidence']:
                    evidence['source_url'] = kwargs['source_url']
                return record
            stderr = io.StringIO()
            with (
                patch.object(sync_regional.sys, 'argv', argv),
                patch.object(sync_regional, 'fetch_candidates_page', side_effect=fetch_candidates),
                patch.object(sync_regional, 'fetch_ccgp_detail_html', side_effect=fetch_detail),
                patch.dict(sync_regional.VERIFIED_NOTICE_ADAPTERS, {'公开招标': adapter}),
                patch.object(sync_regional.time, 'sleep'),
                redirect_stdout(io.StringIO()), redirect_stderr(stderr),
            ):
                result = sync_regional.main()

            output = records_path.read_bytes()
            report = json.loads(report_path.read_text(encoding='utf-8'))
            return result, output, report, stderr.getvalue()

    def test_any_market_all_detail_failures_block_and_preserve_records_even_if_other_market_succeeds(self):
        bj, he = self.candidate('BJ'), self.candidate('HE')
        before = self.canonical_existing_bytes()
        result, output, report, stderr = self.run_sync(
            {'北京': [bj], '河北': [he]},
            {bj.detail_url: RuntimeError('SIMULATED_BJ_DETAIL_FAILURE'), he.detail_url: 'ok'},
            existing_bytes=before,
        )
        self.assertEqual(result, 2)
        self.assertEqual(output, before)
        self.assertEqual(report['refresh_outcome'], 'BLOCKED')
        self.assertFalse(report['publish_allowed'])
        self.assertFalse(report['records_output_written'])
        self.assertEqual(report['records_output_status'], 'PRESERVED_UNCHANGED')
        self.assertIsNone(report['merged_record_count'])
        self.assertEqual(report['publish_gate_reason'], 'REGIONAL_ALL_SELECTED_DETAILS_FAILED_VERIFICATION')
        self.assertEqual(report['blocked_markets'][0]['market_code'], 'BJ')
        self.assertEqual(report['blocked_markets'][0]['reason'], 'REGIONAL_ALL_SELECTED_DETAILS_FAILED_VERIFICATION:BJ')
        self.assertEqual(report['blocked_markets'][0]['failures'][0]['message'], 'SIMULATED_BJ_DETAIL_FAILURE')
        self.assertIn('REGIONAL_ALL_SELECTED_DETAILS_FAILED_VERIFICATION:BJ', stderr)
        self.assertEqual(report['markets'][1]['new_verified_record_count'], 1)

    def test_failed_market_is_reported_before_invalid_historical_data_can_break_merge(self):
        before = b'[{"legacy_record_missing_canonical_fields": true}]\n'
        bj = self.candidate('BJ')
        result, output, report, _stderr = self.run_sync(
            {'北京': [bj]}, {bj.detail_url: RuntimeError('SIMULATED_TOTAL_FAILURE')},
            existing_bytes=before,
        )
        self.assertEqual(result, 2)
        self.assertEqual(output, before)
        self.assertEqual(report['existing_record_count'], 1)
        self.assertEqual(report['blocked_markets'][0]['market_code'], 'BJ')
        self.assertEqual(report['records_output_status'], 'PRESERVED_UNCHANGED')
        self.assertIsNone(report['merged_record_count'])

    def test_one_market_discovery_failure_is_not_hidden_by_another_successful_empty_market(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / 'plan.json'
            records_path = root / 'records.json'
            report_path = root / 'report.json'
            plan_path.write_text(json.dumps({
                'schema_version': '0.1',
                'markets': [
                    {'market_code': 'BJ', 'name': '北京', 'admin_code': '110000', 'ccgp_zone_id': '11'},
                    {'market_code': 'HE', 'name': '河北', 'admin_code': '130000', 'ccgp_zone_id': '13'},
                ],
                'keywords': ['医疗'], 'notice_types': ['公开招标'], 'lookback_days': 3,
                'max_candidates_per_market': 2, 'delay_seconds': 3.0,
            }), encoding='utf-8')
            before = self.canonical_existing_bytes()
            records_path.write_bytes(before)
            argv = [
                str(SCRIPT_PATH), '--plan', str(plan_path), '--as-of', '2026-10-03T00:00:00Z',
                '--records-output', str(records_path), '--existing-records-input', str(records_path),
                '--report-output', str(report_path),
            ]

            def discovery(_session, *, region, **_kwargs):
                if region == '北京':
                    raise RuntimeError('SIMULATED_BJ_SCOPED_FAILURE')
                if region == '河北':
                    return []
                raise RuntimeError('SIMULATED_NATIONAL_FALLBACK_FAILURE')

            stderr = io.StringIO()
            with (
                patch.object(sync_regional.sys, 'argv', argv),
                patch.object(sync_regional, 'fetch_candidates_page', side_effect=discovery),
                patch.object(sync_regional.time, 'sleep'),
                patch.object(sync_regional, 'fetch_ccgp_detail_html', side_effect=AssertionError('NO_CANDIDATES_SELECTED')),
                redirect_stdout(io.StringIO()), redirect_stderr(stderr),
            ):
                result = sync_regional.main()
            report = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertEqual(result, 2)
            self.assertEqual(records_path.read_bytes(), before)
            self.assertFalse(report['publish_allowed'])
            self.assertEqual(report['publish_gate_reason'], 'REGIONAL_MARKET_DISCOVERY_FAILED')
            self.assertEqual([item['market_code'] for item in report['blocked_markets']], ['BJ'])
            self.assertEqual(report['blocked_markets'][0]['reason'], 'REGIONAL_ALL_DISCOVERY_QUERIES_FAILED:BJ')
            self.assertIn('SIMULATED_BJ_SCOPED_FAILURE', str(report['blocked_markets'][0]['failures']))
            self.assertIn('SIMULATED_NATIONAL_FALLBACK_FAILURE', str(report['blocked_markets'][0]['failures']))
            he_report = next(item for item in report['markets'] if item['market_code'] == 'HE')
            self.assertTrue(he_report['discovery_successful'])
            self.assertEqual(he_report['selected_candidate_count'], 0)
            self.assertNotIn('HE', [item['market_code'] for item in report['blocked_markets']])
            self.assertIn('REGIONAL_ALL_DISCOVERY_QUERIES_FAILED:BJ', stderr.getvalue())

    def test_successful_search_with_zero_candidates_remains_publishable(self):
        result, _output, report, stderr = self.run_sync({}, {})
        self.assertEqual(result, 0)
        self.assertEqual(report['refresh_outcome'], 'NO_SELECTED_CANDIDATES')
        self.assertTrue(report['publish_allowed'])
        self.assertEqual(report['blocked_markets'], [])
        self.assertEqual(stderr, '')

    def test_filtering_all_candidates_to_zero_remains_publishable(self):
        bj = DiscoveryCandidate(
            title='北京某医院办公耗材采购项目公开招标公告',
            detail_url='https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/bj-office.htm',
            published_at='2026-10-03',
            buyer_name='北京某医院',
            region='北京市',
            notice_type='公开招标',
            search_keyword='医疗',
        )
        result, _output, report, stderr = self.run_sync(
            {'北京': [bj]}, {},
        )
        self.assertEqual(result, 0)
        self.assertEqual(report['refresh_outcome'], 'NO_SELECTED_CANDIDATES')
        bj_report = next(item for item in report['markets'] if item['market_code'] == 'BJ')
        self.assertEqual(bj_report['selected_candidate_count'], 0)
        self.assertEqual(bj_report['skipped_candidate_count'], 1)
        self.assertTrue(report['publish_allowed'])
        self.assertEqual(stderr, '')

    def test_partial_success_in_same_market_remains_publishable(self):
        good, bad = self.candidate('BJ'), self.candidate('BJ')
        bad = DiscoveryCandidate(**{**bad.__dict__, 'detail_url': 'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/bj-fail.htm'})
        result, _output, report, stderr = self.run_sync(
            {'北京': [good, bad]},
            {good.detail_url: 'ok', bad.detail_url: RuntimeError('SIMULATED_PARTIAL_FAILURE')},
        )
        self.assertEqual(result, 0)
        self.assertTrue(report['publish_allowed'])
        bj_report = next(item for item in report['markets'] if item['market_code'] == 'BJ')
        self.assertEqual(bj_report['selected_candidate_count'], 2)
        self.assertEqual(bj_report['new_verified_record_count'], 1)
        self.assertEqual(report['blocked_markets'], [])
        self.assertEqual(stderr, '')

    def test_all_selected_details_successful_remains_publishable(self):
        bj, he = self.candidate('BJ'), self.candidate('HE')
        result, _output, report, stderr = self.run_sync(
            {'北京': [bj], '河北': [he]}, {bj.detail_url: 'ok', he.detail_url: 'ok'},
        )
        self.assertEqual(result, 0)
        self.assertEqual(report['refresh_outcome'], 'VERIFIED')
        self.assertTrue(report['publish_allowed'])
        self.assertEqual(report['new_verified_record_count'], 2)
        self.assertEqual(report['blocked_markets'], [])
        self.assertEqual(stderr, '')

    def test_all_details_fail_with_historical_records_preserves_exact_bytes(self):
        existing_bytes = self.canonical_existing_bytes()
        bj = self.candidate('BJ')
        result, output, report, _stderr = self.run_sync(
            {'北京': [bj]}, {bj.detail_url: RuntimeError('SIMULATED_TOTAL_FAILURE')},
            existing_bytes=existing_bytes,
        )
        self.assertEqual(result, 2)
        self.assertEqual(output, existing_bytes)
        self.assertEqual(report['existing_record_count'], 1)
        self.assertEqual(report['refresh_outcome'], 'BLOCKED')
        self.assertEqual(report['blocked_markets'][0]['market_code'], 'BJ')

    def test_report_output_cannot_alias_records_or_existing_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = root / 'records.json'
            report = root / 'report.json'
            records.write_bytes(b'[]\n')
            with self.assertRaisesRegex(ValueError, 'must not alias'):
                sync_regional.validate_report_output_paths(records, records, [records])

            report.symlink_to(records)
            with self.assertRaisesRegex(ValueError, 'must not alias'):
                sync_regional.validate_report_output_paths(report, root / 'other.json', [records])

            report.unlink()
            report.hardlink_to(records)
            with self.assertRaisesRegex(ValueError, 'must not alias'):
                sync_regional.validate_report_output_paths(report, root / 'other.json', [records])


if __name__ == '__main__':
    unittest.main()
