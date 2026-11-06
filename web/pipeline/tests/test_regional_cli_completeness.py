from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import sync_regional_ccgp as target

CORPUS = ROOT / 'tests/fixtures/ccgp_template_audit_20261106'
CASES = json.loads((CORPUS / 'manifest.json').read_text())['cases']
SELECTED = [next(c for c in CASES if c['label'] == label) for label in (
    'ccgp_he_2a9ca892bf9d0b6a', 'ccgp_hl_b36866ded1fc3097')]


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, delay):
        self.sleeps.append(delay)
        self.value += delay


class RegionalCliCompletenessTests(unittest.TestCase):
    def setUp(self):
        for owner, name in ((socket, 'create_connection'), (socket, 'socket'), (target.urllib.request, 'build_opener')):
            blocker = patch.object(owner, name, side_effect=AssertionError('NETWORK_OR_REAL_CLIENT_FORBIDDEN'))
            blocker.start()
            self.addCleanup(blocker.stop)

    def run_cli(self, mode, *, separate_output=False, alias=None, absent_output=False,
                empty_input=False, records_alias_plan=False, injected_error=None,
                distinct_detail_hosts=False, both_notice_types=False, clock=None,
                expire_at=None, io_fault=None, records_symlink=False):
        """Actual argparse/main and official parsers; only I/O is replaced offline."""
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            folder = Path(temp)
            plan = json.loads(target.DEFAULT_PLAN.read_text())
            plan['markets'] = [m for m in plan['markets'] if m['market_code'] in ('HE', 'HL')]
            plan['keywords'] = ['first', 'second']
            if not both_notice_types:
                plan['notice_types'] = ['公开招标']
            plan_path = folder / 'plan.json'
            plan_path.write_text(json.dumps(plan, ensure_ascii=False))
            # Keep a real existing record distinct from the two selected fixtures.
            source_records = json.loads((ROOT / 'data/regional_live_ccgp_records.json').read_text())
            old = next(r for r in source_records if r['source']['url'] not in {c['url'] for c in SELECTED})
            input_path = folder / 'input.json'
            original = (json.dumps([] if empty_input else [old], ensure_ascii=False, indent=1) + '\n\n').encode()
            input_path.write_bytes(original)
            output_path = folder / 'records.json' if separate_output else input_path
            if separate_output and not absent_output:
                output_path.write_bytes(original)
            if records_alias_plan:
                output_path = plan_path
            if records_symlink:
                output_path = folder / 'records-link.json'
                output_path.symlink_to(input_path)
            report_path = folder / 'report.json'
            protected = {plan_path: plan_path.read_bytes(), input_path: original}
            if alias:
                destination = {'input': input_path, 'records': output_path, 'plan': plan_path}[alias.split('_')[0]]
                if alias.endswith('_symlink'):
                    report_path.symlink_to(destination)
                elif alias.endswith('_hardlink'):
                    report_path.hardlink_to(destination)
                else:
                    report_path = destination
            candidates = {
                name: ('公开招标', SimpleNamespace(detail_url=c['url'], title='医院医疗设备采购',
                    buyer_name='医院', notice_type='公开招标', published_at='2026-09-08', region=name))
                for name, c in zip(('河北', '黑龙江'), SELECTED)
            }
            if distinct_detail_hosts:
                candidates['黑龙江'][1].detail_url = SELECTED[1]['url'].replace('www.ccgp.gov.cn', 'ccgp.gov.cn')
            session_class = target.CcgpSearchSession

            def session_stub(**kwargs):
                if mode not in ('f1_warmup', 'f1_warmup_page', 'f1_search_page'):
                    return object()
                # Exercise real warmup code without constructing an opener/client.
                session = object.__new__(session_class)
                session.warmed = False
                session.on_access_blocked = kwargs['on_access_blocked']
                session.budget = kwargs.get('budget')

                def read(url, **unused):
                    if mode == 'f1_search_page':
                        return '<html>频繁访问</html>' if url.startswith(target.CCGP_SEARCH_URL) else '<html></html>'
                    if mode == 'f1_warmup_page':
                        return '<html>您的访问过于频繁</html>'
                    raise injected_error

                session._read = read
                return session

            def discover_impl(session, **kwargs):
                if mode == 'f1_search_page':
                    session.fetch(target.CCGP_SEARCH_URL + '?offline=1')
                if mode in ('f1_warmup', 'f1_warmup_page'):
                    session.warmup()
                region, keyword = kwargs['region'], kwargs['keyword']
                if mode == 'f1_scoped' and region == '河北' and keyword == 'second':
                    raise injected_error
                if mode == 'f1_fallback' and region == '黑龙江':
                    return []
                if mode == 'f1_fallback' and region is None and keyword == 'first':
                    raise injected_error
                if mode == 'all_discovery_failed':
                    raise RuntimeError('OFFLINE_SEARCH_FAILED')
                if mode in ('one_discovery_failed', 'rate_limited') and region == '黑龙江' and keyword == 'second':
                    raise RuntimeError('CCGP_RATE_LIMITED' if mode == 'rate_limited' else 'OFFLINE_SEARCH_FAILED')
                if mode == 'empty_success':
                    return []
                if mode in ('partial_fallback', 'fallback_success') and region == '黑龙江':
                    return []
                if region is None:
                    if mode == 'partial_fallback' and keyword == 'second':
                        raise RuntimeError('OFFLINE_FALLBACK_FAILED')
                    return [candidates['黑龙江']] if kwargs['page_index'] == 1 else []
                return [candidates[region]]

            def discover(session, **kwargs):
                result = discover_impl(session, **kwargs)
                if expire_at == 'search_return' or (expire_at == 'fallback_return' and kwargs['region'] is None):
                    clock.value = 840
                elif expire_at == 'sleep_admission':
                    clock.value = 836
                elif expire_at == 'detail_timeout' and kwargs['region'] == '黑龙江' and kwargs['keyword'] == 'second':
                    clock.value = 825
                return result

            def fetch(url, **kwargs):
                if mode in ('f1_detail', 'f1_detail_page') and url == SELECTED[0]['url']:
                    if mode == 'f1_detail_page':
                        return '<html>您的访问过于频繁</html>'
                    raise injected_error
                if mode == 'all_detail_failed' or (mode in ('one_detail_failed', 'detail_rate_limited') and url == SELECTED[1]['url']):
                    raise RuntimeError('CCGP_RATE_LIMITED' if mode == 'detail_rate_limited' else 'OFFLINE_DETAIL_FAILED')
                case = next(c for c in SELECTED if c['url'] == url.replace('https://ccgp.gov.cn/', 'https://www.ccgp.gov.cn/'))
                html = (CORPUS / case['file']).read_bytes().decode(case['encoding'])
                if expire_at == 'detail_return':
                    clock.value = 840
                return html

            real_write, real_replace = target.write_json, target.os.replace
            real_load, real_merge = target.load_json_arrays, target.merge_canonical_records

            def write(path, payload):
                is_stage = path.name.startswith('.regional-ccgp-')
                if io_fault == 'stage_error' and is_stage:
                    raise OSError('OFFLINE_STAGE_FAILURE')
                if io_fault == 'report_error' and path == report_path:
                    raise OSError('OFFLINE_REPORT_FAILURE')
                real_write(path, payload)
                if (io_fault == 'serialize_expire' and is_stage) or (io_fault == 'report_late' and path == report_path):
                    clock.value = 900

            def replace(src, dst):
                if io_fault == 'replace_error_before':
                    raise OSError('OFFLINE_REPLACE_FAILURE')
                real_replace(src, dst)
                if io_fault == 'replace_then_error':
                    raise OSError('OFFLINE_REPLACE_RESULT_UNKNOWN')
                if io_fault == 'replace_late':
                    clock.value = 900

            def load(*args, **kwargs):
                result = real_load(*args, **kwargs)
                if expire_at in ('input', 'input_near'):
                    clock.value = 839 if expire_at == 'input_near' else 840
                return result

            def merge(*args):
                if io_fault == 'merge_error':
                    raise ValueError('OFFLINE_MERGE_FAILURE')
                result = real_merge(*args)
                if io_fault == 'merge_expire':
                    clock.value = 900
                return result

            if expire_at == 'detail_parse':
                real_adapter = target.VERIFIED_NOTICE_ADAPTERS['公开招标']

                def adapter(*args, **kwargs):
                    result = real_adapter(*args, **kwargs)
                    clock.value = 840
                    return result

                stack.enter_context(patch.dict(target.VERIFIED_NOTICE_ADAPTERS, {'公开招标': adapter}))

            # Neither a search opener, a socket nor a real detail client may run.
            client = stack.enter_context(patch.object(target, 'CcgpSearchSession', side_effect=session_stub))
            network = stack.enter_context(patch.object(socket, 'create_connection', side_effect=AssertionError('NETWORK_FORBIDDEN')))
            sock = stack.enter_context(patch.object(socket, 'socket', side_effect=AssertionError('NETWORK_FORBIDDEN')))
            opener = stack.enter_context(patch.object(target.urllib.request, 'build_opener', side_effect=AssertionError('REAL_CLIENT_FORBIDDEN')))
            search = stack.enter_context(patch.object(target, 'fetch_candidates_page', side_effect=discover))
            detail = stack.enter_context(patch.object(target, 'fetch_ccgp_detail_html', side_effect=fetch))
            stack.enter_context(patch.object(target.time, 'sleep', return_value=None))
            writer = stack.enter_context(patch.object(target, 'write_json', side_effect=write))
            stack.enter_context(patch.object(target.os, 'replace', side_effect=replace))
            stack.enter_context(patch.object(target, 'load_json_arrays', side_effect=load))
            stack.enter_context(patch.object(target, 'merge_canonical_records', side_effect=merge))
            stack.enter_context(patch.object(sys, 'argv', ['sync_regional_ccgp', '--plan', str(plan_path),
                '--as-of', '2026-11-06T11:05:33+00:00', '--existing-records-input', str(input_path),
                '--records-output', str(output_path), '--report-output', str(report_path)]))
            try:
                stderr = StringIO()
                with redirect_stdout(StringIO()), redirect_stderr(stderr):
                    kwargs = {'detail_transport': target.fetch_ccgp_detail_html}
                    if clock:
                        kwargs.update(monotonic=clock, sleep=clock.sleep)
                    code = target.main(**kwargs)
            except SystemExit as exc:
                code = exc.code
            except (ValueError, RuntimeError) as exc:
                code = 'exception:' + str(exc)
            result = {
                'code': code, 'original': original,
                'input_bytes': input_path.read_bytes(),
                'output_bytes': output_path.read_bytes() if output_path.exists() else None,
                'inputs_unchanged': all(p.read_bytes() == b for p, b in protected.items()),
                'report': json.loads(report_path.read_text()) if report_path.exists() and not alias else None,
                'client_calls': client.call_count, 'search_calls': search.call_count, 'detail_calls': detail.call_count,
                'detail_timeouts': [c.kwargs.get('timeout_seconds') for c in detail.call_args_list],
                'stderr': stderr.getvalue(), 'temporary_files': list(folder.glob('.regional-ccgp-*')),
                'output_is_symlink': output_path.is_symlink(),
                'report_write_calls': sum(c.args[0] == report_path for c in writer.call_args_list),
            }
            network.assert_not_called()
            sock.assert_not_called()
            opener.assert_not_called()
            return result

    def test_complete_success_writes_verified_records(self):
        r = self.run_cli('all_success', separate_output=True)
        self.assertEqual(r['code'], 0)
        self.assertTrue(r['report']['acceptance_ready'])
        self.assertTrue(r['report']['records_written'])
        self.assertEqual(len(json.loads(r['output_bytes'])), 3)
        self.assertIn(json.loads(r['original'])[0], json.loads(r['output_bytes']))
        self.assertTrue(r['inputs_unchanged'])

    def test_complete_empty_keeps_existing_facts_and_succeeds(self):
        r = self.run_cli('empty_success', separate_output=True)
        self.assertEqual(r['code'], 0)
        self.assertTrue(r['report']['acceptance_ready'])
        self.assertEqual(r['report']['new_verified_record_count'], 0)
        self.assertEqual(json.loads(r['output_bytes']), json.loads(r['original']))
        self.assertTrue(r['inputs_unchanged'])

    def assert_blocked(self, mode, **kwargs):
        r = self.run_cli(mode, **kwargs)
        self.assertEqual(r['code'], 2)
        self.assertFalse(r['report']['acceptance_ready'])
        self.assertFalse(r['report']['records_written'])
        self.assertTrue(r['report']['acceptance_blockers'])
        self.assertEqual(r['output_bytes'], None if kwargs.get('absent_output') else r['original'])
        self.assertTrue(r['inputs_unchanged'])
        return r

    def test_one_failed_scoped_query_preserves_in_place_records(self):
        self.assert_blocked('one_discovery_failed')

    def test_one_failed_detail_preserves_in_place_records(self):
        r = self.assert_blocked('one_detail_failed')
        self.assertEqual(r['report']['new_verified_record_count'], 1)

    def test_all_failed_details_preserve_records(self):
        self.assert_blocked('all_detail_failed')

    def test_valid_empty_input_and_scan_do_not_backfill(self):
        r = self.run_cli('empty_success', separate_output=True, empty_input=True)
        self.assertEqual(r['code'], 0)
        self.assertTrue(r['report']['acceptance_ready'])
        self.assertEqual(json.loads(r['output_bytes']), [])
        self.assertTrue(r['inputs_unchanged'])

    def test_explicit_search_rate_limit_blocks_batch(self):
        self.assert_blocked('rate_limited')

    def test_explicit_detail_rate_limit_blocks_batch(self):
        self.assert_blocked('detail_rate_limited')

    def test_all_discovery_failures_report_and_reject(self):
        r = self.assert_blocked('all_discovery_failed')
        self.assertIn('ALL_MULTI_REGION_DISCOVERY_QUERIES_FAILED', r['report']['acceptance_blockers'])

    def test_partial_fallback_cannot_be_hidden_by_success(self):
        r = self.assert_blocked('partial_fallback')
        self.assertGreater(r['report']['national_fallback_query_success_count'], 0)
        self.assertGreater(r['report']['national_fallback_failure_count'], 0)

    def test_complete_fallback_is_accepted(self):
        r = self.run_cli('fallback_success', separate_output=True)
        self.assertEqual(r['code'], 0)
        self.assertTrue(r['report']['acceptance_ready'])
        self.assertEqual(r['report']['new_verified_record_count'], 2)

    def test_failure_preserves_distinct_existing_output(self):
        self.assert_blocked('one_detail_failed', separate_output=True)

    def test_failure_does_not_create_absent_output(self):
        self.assert_blocked('one_detail_failed', separate_output=True, absent_output=True)

    def test_report_aliases_are_rejected_before_client_or_fetch(self):
        for alias in ('input', 'records', 'plan', 'input_symlink', 'records_symlink', 'plan_symlink',
                      'input_hardlink', 'records_hardlink', 'plan_hardlink'):
            with self.subTest(alias=alias):
                r = self.run_cli('all_success', separate_output=True, alias=alias)
                self.assertNotEqual(r['code'], 0)
                self.assertEqual(r['output_bytes'], r['original'])
                self.assertTrue(r['inputs_unchanged'])
                self.assertEqual((r['client_calls'], r['search_calls'], r['detail_calls']), (0, 0, 0))

    def test_records_output_cannot_overwrite_plan(self):
        r = self.run_cli('all_success', separate_output=True, records_alias_plan=True)
        self.assertEqual(r['code'], 2)
        self.assertTrue(r['inputs_unchanged'])
        self.assertEqual((r['client_calls'], r['search_calls'], r['detail_calls']), (0, 0, 0))

    def test_scoped_explicit_denials_stop_search_but_not_detail_host(self):
        for error in (RuntimeError('CCGP_RATE_LIMITED'), *(HTTPError(target.CCGP_SEARCH_URL, c, 'offline', {}, None) for c in (401, 403, 429))):
            with self.subTest(error=str(error)):
                r = self.run_cli('f1_scoped', injected_error=error)
                self.assertEqual(r['search_calls'], 2)
                self.assertEqual(r['detail_calls'], 1)
                self.assertEqual(r['code'], 2)
                self.assertEqual(r['output_bytes'], r['original'])
                self.assertFalse(r['report']['acceptance_ready'])
                self.assertEqual(r['report']['scoped_queries_skipped_due_to_access'], 2)
                self.assertIn('search.ccgp.gov.cn', r['report']['access_blocked_hosts'])
                self.assertTrue(r['inputs_unchanged'])

    def test_fallback_denial_stops_later_keywords(self):
        r = self.run_cli('f1_fallback', injected_error=HTTPError(target.CCGP_SEARCH_URL, 429, 'offline', {}, None))
        self.assertEqual(r['search_calls'], 5)
        self.assertEqual(r['code'], 2)
        self.assertEqual(r['output_bytes'], r['original'])

    def test_detail_denials_stop_later_same_host_details(self):
        for error in (RuntimeError('CCGP_RATE_LIMITED'), *(HTTPError(SELECTED[0]['url'], c, 'offline', {}, None) for c in (401, 403, 429))):
            with self.subTest(error=str(error)):
                r = self.run_cli('f1_detail', injected_error=error)
                self.assertEqual(r['detail_calls'], 1)
                self.assertEqual(r['search_calls'], 4)
                self.assertEqual(r['code'], 2)
                self.assertEqual(r['output_bytes'], r['original'])
                self.assertFalse(r['report']['acceptance_ready'])
                self.assertEqual(r['report']['details_skipped_due_to_access'], 1)

    def test_official_detail_rate_limit_page_stops_later_details(self):
        r = self.run_cli('f1_detail_page')
        self.assertEqual(r['detail_calls'], 1)
        self.assertEqual(r['code'], 2)
        self.assertEqual(r['output_bytes'], r['original'])

    def test_transient_errors_do_not_trip_host_stop(self):
        for mode, error in (('f1_scoped', TimeoutError('offline')),
                            ('f1_scoped', URLError('offline')),
                            ('f1_detail', RuntimeError('CCGP_DETAIL_NETWORK_ERROR')),
                            ('f1_detail', HTTPError(SELECTED[0]['url'], 503, 'offline', {}, None))):
            with self.subTest(mode=mode, error=str(error)):
                r = self.run_cli(mode, injected_error=error)
                self.assertEqual(r['search_calls'], 4)
                self.assertEqual(r['detail_calls'], 2)
                self.assertEqual(r['code'], 2)
                self.assertEqual(r['output_bytes'], r['original'])

    def test_wrapped_detail_http_denial_is_recognized(self):
        for message in ('CCGP_DETAIL_HTTP_403', 'offline wrapper'):
            with self.subTest(message=message):
                error = RuntimeError(message)
                error.__cause__ = HTTPError(SELECTED[0]['url'], 403, 'offline', {}, None)
                r = self.run_cli('f1_detail', injected_error=error)
                self.assertEqual(r['detail_calls'], 1)
                self.assertEqual(r['code'], 2)

    def test_actual_search_session_limit_page_stops_cli(self):
        r = self.run_cli('f1_search_page')
        self.assertEqual((r['search_calls'], r['detail_calls']), (1, 0))
        self.assertEqual(r['code'], 2)
        self.assertEqual(r['output_bytes'], r['original'])

    def test_detail_host_stop_does_not_block_other_official_host(self):
        r = self.run_cli('f1_detail', injected_error=HTTPError(SELECTED[0]['url'], 403, 'offline', {}, None),
                         distinct_detail_hosts=True)
        self.assertEqual(r['detail_calls'], 2)
        self.assertEqual(r['code'], 2)
        self.assertEqual(r['report']['details_skipped_due_to_access'], 0)
        self.assertEqual(set(r['report']['access_blocked_hosts']), {'www.ccgp.gov.cn'})

    def test_homepage_denial_stops_details_but_not_search(self):
        r = self.run_cli('f1_warmup', injected_error=HTTPError('https://www.ccgp.gov.cn/', 403, 'offline', {}, None))
        self.assertEqual((r['search_calls'], r['detail_calls']), (4, 0))
        self.assertEqual(r['code'], 2)
        self.assertEqual(r['report']['details_skipped_due_to_access'], 2)
        self.assertEqual(r['output_bytes'], r['original'])

    def test_homepage_limit_page_stops_details(self):
        r = self.run_cli('f1_warmup_page')
        self.assertEqual((r['search_calls'], r['detail_calls']), (4, 0))
        self.assertEqual(r['code'], 2)

    def test_transient_homepage_failure_remains_best_effort(self):
        r = self.run_cli('f1_warmup', injected_error=TimeoutError('offline'))
        self.assertEqual((r['search_calls'], r['detail_calls']), (4, 2))
        self.assertEqual(r['code'], 0)
        self.assertEqual(r['report']['access_blocked_hosts'], {})

    def test_host_stop_is_not_carried_into_next_cli_call(self):
        self.run_cli('f1_detail', injected_error=RuntimeError('CCGP_RATE_LIMITED'))
        r = self.run_cli('all_success')
        self.assertEqual(r['code'], 0)
        self.assertEqual(r['report']['access_blocked_hosts'], {})

    def test_denials_stop_default_two_notice_type_fanout(self):
        for mode, expected in (('f1_scoped', 3), ('f1_fallback', 9)):
            with self.subTest(mode=mode):
                r = self.run_cli(mode, injected_error=RuntimeError('CCGP_RATE_LIMITED'), both_notice_types=True)
                self.assertEqual(r['search_calls'], expected)
                self.assertEqual(r['code'], 2)
                self.assertEqual(r['output_bytes'], r['original'])

    def assert_budget_rejected(self, result):
        self.assertEqual(result['code'], 2)
        self.assertEqual(result['output_bytes'], result['original'])
        self.assertTrue(result['inputs_unchanged'])
        self.assertFalse(result['report']['acceptance_ready'])
        self.assertFalse(result['report']['records_written'])
        self.assertIn('BUDGET_EXCEEDED', result['report']['acceptance_blockers'])
        self.assertEqual(result['report']['commit_state'], 'NOT_COMMITTED')
        self.assertEqual(result['temporary_files'], [])

    def test_input_exhaustion_and_one_second_margin_reject_before_client(self):
        for phase in ('input', 'input_near'):
            with self.subTest(phase=phase):
                r = self.run_cli('all_success', clock=FakeClock(), expire_at=phase)
                self.assert_budget_rejected(r)
                self.assertEqual((r['client_calls'], r['search_calls'], r['detail_calls']), (0, 0, 0))

    def test_work_and_total_exact_deadlines_are_expired(self):
        clock = FakeClock()
        budget = target.CliBudget(clock, clock.sleep)
        clock.value = 840
        with self.assertRaises(target.CliBudgetExceeded):
            budget.check('WORK')
        budget.check('FINALIZE', finalize=True)
        clock.value = 900
        with self.assertRaises(target.CliBudgetExceeded):
            budget.check('FINALIZE', finalize=True)

    def test_parameterized_runtime_budget_retains_preflight_origin(self):
        clock = FakeClock()
        clock.value = 100
        budget = target.CliBudget(clock, clock.sleep, total_seconds=270, work_seconds=210, started_at=0)
        self.assertEqual(budget.started, 0)
        self.assertEqual(budget.request_timeout(90, 'READ'), 90)
        clock.value = 205
        self.assertEqual(budget.request_timeout(90, 'READ'), 4)
        self.assertEqual(budget.snapshot()['finalize_reserve_seconds'], 60)
        clock.value = 210
        with self.assertRaises(target.CliBudgetExceeded):
            budget.check('READ')
        budget.check('FINALIZE', finalize=True)

    def test_budget_configuration_rejects_invalid_or_future_origins(self):
        clock = FakeClock()
        for options in ({'work_seconds': 900}, {'total_seconds': -1}, {'work_seconds': 0},
                        {'started_at': 1}, {'started_at': float('nan')}, {'total_seconds': float('inf')}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                target.CliBudget(clock, clock.sleep, **options)

    def test_cli_default_budget_numbers_stay_900_840_60(self):
        clock = FakeClock()
        snapshot = target.CliBudget(clock, clock.sleep).snapshot()
        self.assertEqual([snapshot[k] for k in ('total_seconds', 'work_seconds', 'finalize_reserve_seconds')], [900, 840, 60])

    def test_request_timeout_caps_and_remaining_budget(self):
        clock = FakeClock()
        budget = target.CliBudget(clock, clock.sleep)
        self.assertEqual([budget.request_timeout(c, 'READ') for c in (30, 90, 30)], [30, 90, 30])
        clock.value = 831
        self.assertEqual(budget.request_timeout(90, 'READ'), 8)
        clock.value = 839
        with self.assertRaises(target.CliBudgetExceeded):
            budget.request_timeout(90, 'READ')

    def offline_session(self, clock=None):
        session = object.__new__(target.CcgpSearchSession)
        session.budget = target.CliBudget(clock, clock.sleep) if clock else None
        session.warmed, session.on_access_blocked = False, None
        response = SimpleNamespace(read=Mock(return_value=b'<html></html>'),
                                   headers=SimpleNamespace(get_content_charset=lambda: 'utf-8'))
        session.opener = SimpleNamespace(open=Mock(return_value=nullcontext(response)))
        return session, response

    def test_real_session_recalculates_search_timeout_after_warmup(self):
        clock = FakeClock()
        session, response = self.offline_session(clock)
        calls = []

        def read():
            calls.append(1)
            if len(calls) == 1:
                clock.value = 830
            return b'<html></html>'

        response.read.side_effect = read
        session.fetch(target.CCGP_SEARCH_URL)
        self.assertEqual([c.kwargs['timeout'] for c in session.opener.open.call_args_list], [30, 8])
        self.assertEqual(clock.sleeps, [1])

    def test_warmup_expiry_is_not_swallowed_and_search_never_starts(self):
        clock = FakeClock()
        session, response = self.offline_session(clock)

        def late():
            clock.value = 840
            return b'<html></html>'

        response.read.side_effect = late
        with self.assertRaises(target.CliBudgetExceeded):
            session.fetch(target.CCGP_SEARCH_URL)
        self.assertEqual(session.opener.open.call_count, 1)
        self.assertEqual(clock.sleeps, [])

    def test_open_return_expiry_prevents_response_read(self):
        clock = FakeClock()
        session, response = self.offline_session(clock)

        def late_open(*args, **kwargs):
            clock.value = 840
            return nullcontext(response)

        session.opener.open.side_effect = late_open
        with self.assertRaises(target.CliBudgetExceeded):
            session._read(target.CCGP_SEARCH_URL, timeout=90)
        response.read.assert_not_called()

    def test_decode_expiry_is_rejected(self):
        clock = FakeClock()
        session, response = self.offline_session(clock)

        class LateBytes(bytes):
            def decode(self, *args, **kwargs):
                clock.value = 840
                return '<html></html>'

        response.read.return_value = LateBytes(b'html')
        with self.assertRaises(target.CliBudgetExceeded):
            session._read(target.CCGP_SEARCH_URL, timeout=90)

    def test_unbudgeted_runtime_session_retains_original_timeouts(self):
        session, _ = self.offline_session()
        with patch.object(target.time, 'sleep') as sleeper:
            session.fetch(target.CCGP_SEARCH_URL)
        sleeper.assert_called_once_with(1)
        self.assertEqual([c.kwargs['timeout'] for c in session.opener.open.call_args_list], [30, 90])

    def test_insufficient_sleep_does_not_shorten_delay_or_send_next_request(self):
        clock = FakeClock()
        r = self.run_cli('all_success', clock=clock, expire_at='sleep_admission')
        self.assert_budget_rejected(r)
        self.assertEqual(clock.sleeps, [])
        self.assertEqual(r['search_calls'], 1)
        self.assertEqual(r['detail_calls'], 0)

    def test_sleep_overrun_globally_stops_work(self):
        clock = FakeClock()

        def oversleep(delay):
            clock.sleeps.append(delay)
            clock.value = 840

        clock.sleep = oversleep
        r = self.run_cli('all_success', clock=clock)
        self.assert_budget_rejected(r)
        self.assertEqual((r['search_calls'], r['detail_calls']), (1, 0))
        self.assertEqual(clock.sleeps, [4])

    def test_search_and_fallback_late_returns_do_not_allow_details(self):
        for mode, phase in (('all_success', 'search_return'), ('fallback_success', 'fallback_return'), ('empty_success', 'search_return')):
            with self.subTest(phase=phase, mode=mode):
                r = self.run_cli(mode, clock=FakeClock(), expire_at=phase)
                self.assert_budget_rejected(r)
                self.assertEqual(r['detail_calls'], 0)
                self.assertEqual(r['report']['new_verified_record_count'], 0)

    def test_detail_return_or_parse_expiry_cannot_add_new_facts(self):
        for phase in ('detail_return', 'detail_parse'):
            with self.subTest(phase=phase):
                r = self.run_cli('all_success', clock=FakeClock(), expire_at=phase)
                self.assert_budget_rejected(r)
                self.assertEqual(r['detail_calls'], 1)
                self.assertEqual(r['report']['new_verified_record_count'], 0)

    def test_complete_fake_clock_scan_and_empty_scan_still_succeed(self):
        for mode in ('all_success', 'empty_success'):
            with self.subTest(mode=mode):
                r = self.run_cli(mode, clock=FakeClock(), separate_output=True)
                self.assertEqual(r['code'], 0)
                self.assertEqual(r['report']['commit_state'], 'COMMITTED')
                self.assertTrue(r['inputs_unchanged'])
                self.assertFalse(r['report']['post_commit_overrun'])
                self.assertTrue(all(t is not None and 0 < t <= 30 for t in r['detail_timeouts']))
                self.assertEqual(r['temporary_files'], [])

    def test_detail_timeout_uses_actual_remaining_budget(self):
        r = self.run_cli('all_success', clock=FakeClock(), expire_at='detail_timeout')
        self.assertEqual(r['code'], 0)
        self.assertEqual(r['detail_timeouts'], [6, 2])

    def test_finalize_and_serialization_expiry_keep_original_records(self):
        for fault in ('merge_expire', 'serialize_expire'):
            with self.subTest(fault=fault):
                r = self.run_cli('all_success', clock=FakeClock(), io_fault=fault)
                self.assert_budget_rejected(r)

    def test_prepare_and_merge_failure_keep_original_and_clean_stage(self):
        for fault in ('stage_error', 'merge_error'):
            with self.subTest(fault=fault):
                r = self.run_cli('all_success', clock=FakeClock(), io_fault=fault)
                self.assertEqual(r['code'], 2)
                self.assertEqual(r['output_bytes'], r['original'])
                self.assertEqual(r['temporary_files'], [])
                self.assertFalse(r['report']['records_written'])

    def test_replace_exception_is_unknown_without_claiming_zero_write(self):
        for fault, changed in (('replace_error_before', False), ('replace_then_error', True)):
            with self.subTest(fault=fault):
                r = self.run_cli('all_success', clock=FakeClock(), io_fault=fault)
                self.assertEqual(r['code'], 3)
                self.assertEqual(r['report']['commit_state'], 'COMMIT_UNKNOWN')
                self.assertIsNone(r['report']['records_written'])
                self.assertEqual(r['output_bytes'] != r['original'], changed)
                self.assertEqual(r['temporary_files'], [])

    def test_post_commit_lateness_reports_commit_and_never_rolls_back(self):
        for fault in ('replace_late', 'report_late'):
            with self.subTest(fault=fault):
                r = self.run_cli('all_success', clock=FakeClock(), io_fault=fault)
                self.assertEqual(r['code'], 3)
                self.assertEqual(r['report']['commit_state'], 'COMMITTED')
                self.assertTrue(r['report']['records_written'])
                self.assertTrue(r['report']['post_commit_overrun'])
                self.assertNotEqual(r['output_bytes'], r['original'])
                self.assertLessEqual(r['report_write_calls'], 2)

    def test_report_failure_after_commit_has_structured_stderr_receipt(self):
        r = self.run_cli('all_success', clock=FakeClock(), io_fault='report_error')
        self.assertEqual(r['code'], 3)
        receipt = json.loads(r['stderr'])
        self.assertEqual(receipt['commit_state'], 'COMMITTED_REPORTING_INCOMPLETE')
        self.assertTrue(receipt['records_written'])
        self.assertNotEqual(r['output_bytes'], r['original'])

    def test_records_symlink_targets_remain_links_and_failures_preserve_target(self):
        for phase in (None, 'detail_return'):
            with self.subTest(phase=phase):
                r = self.run_cli('all_success', clock=FakeClock(), expire_at=phase, records_symlink=True)
                self.assertTrue(r['output_is_symlink'])
                if phase:
                    self.assert_budget_rejected(r)
                else:
                    self.assertEqual(r['code'], 0)
                    self.assertEqual(len(json.loads(r['output_bytes'])), 3)
