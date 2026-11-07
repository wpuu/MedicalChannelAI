from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot
from medical_channel_pipeline.ccgp_events import parse_ccgp_event_text

ROOT = Path(__file__).resolve().parents[1]

CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：XCSD-2026-C-181
原公告的采购项目名称：病原微生物能力提升相关设备购置
首次公告日期：2026-08-24
二、更正信息
更正事项：采购文件
更正内容：原公告的投标文件提交截止时间：2026-09-14 09:30:00，更正为：2026-09-18 09:30:00。
原公告的开标时间：2026-09-14 09:30:00，更正为：2026-09-18 09:30:00。
其他内容不变
更正日期：2026-09-01
三、其他补充事宜 无
"""

RESPONSE_CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：TGPC-2026-A-0081
原公告的采购项目名称：天津市第一中心医院复康院区提升改造项目基础硬件及附属设施建设项目智能语音采集设备采购项目
首次公告日期：2026-05-15
二、更正信息
更正事项：采购公告
更正内容：原公告的响应文件提交截止时间：2026-05-26 08:30:00，更正为：2026-05-29 08:30:00。
原公告的开启时间：2026-05-26 09:30:00，更正为：2026-05-29 09:30:00。
其他内容不变
更正日期：2026-05-20
三、其他补充事宜 无
"""

MATERIAL_RESPONSE_CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：TGPC-2026-A-0081
原公告的采购项目名称：天津市第一中心医院复康院区提升改造项目基础硬件及附属设施建设项目智能语音采集设备采购项目
首次公告日期：2026-05-15
二、更正信息
更正事项：采购文件
更正内容：原公告的响应文件提交截止时间：2026-05-26 08:30:00，更正为：2026-05-29 08:30:00。
同时调整采购需求中的技术参数，具体详见更正后的竞争性磋商文件。
更正日期：2026-05-20
三、其他补充事宜 无
"""

INCOMPLETE_CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：XCSD-2026-C-181
原公告的采购项目名称：病原微生物能力提升相关设备购置
首次公告日期：2026-08-24
二、更正信息
更正事项：采购公告
更正内容：原公告的获取招标文件结束日期：2026-08-31，更正为：2026-09-04。
原公告的投标文件提交截止时间：2026-09-14 09:30:00，更正为：2026-09-20 09:30:00。
其他内容不变
更正日期：2026-09-01
三、其他补充事宜 无
"""

MATERIAL_CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：XCSD-2026-C-181
原公告的采购项目名称：病原微生物能力提升相关设备购置
首次公告日期：2026-08-24
二、更正信息
更正事项：采购文件和采购公告
更正内容：原公告的投标文件提交截止时间：2026-09-14 09:30:00，更正为：2026-09-18 09:30:00。
同时调整采购需求中的技术参数，具体详见更正后的招标文件。
更正日期：2026-09-01
三、其他补充事宜 无
"""

TERMINATION_FIXTURE = """
终止公告
发布日期：2026年08月25日
一、项目基本情况：
采购项目编号：XCSD-2026-C-181
采购项目名称：病原微生物能力提升相关设备购置
二、项目终止的原因：截至规定时间，无供应商投标
三、其他补充事宜：无
"""

CORRECTION_URL = 'https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260901_99999999.htm'
RESPONSE_CORRECTION_URL = 'https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202605/t20260520_99999997.htm'


class CcgpEventTests(unittest.TestCase):
    def event_budget_scan_case(self, mode="success", *, elapsed=0, use_budget=True, use_guard=False):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        sys.path.insert(0, str(ROOT / "scripts"))
        import sync_ccgp_query as query
        from sync_regional_ccgp import CliBudget, CliBudgetExceeded
        tick, calls, failures, sleeps = [float(elapsed)], [], [], []
        blocked_hosts = {} if use_guard else None
        def sleep(delay):
            sleeps.append(delay)
            tick[0] = 180 if mode == "sleep_late" else tick[0] + delay
        budget = CliBudget(lambda: tick[0], sleep, total_seconds=270, work_seconds=180, started_at=0)
        candidate = SimpleNamespace(title="XCSD-2026-C-181 更正公告", detail_url=CORRECTION_URL,
                                    published_at="2026-09-01")
        def search(url, **kwargs):
            calls.append(("search", kwargs.get("timeout_seconds")))
            if mode == "search_denied":
                from urllib.error import HTTPError
                raise HTTPError(url, 429, "token=secret", {}, None)
            if mode in ("search_late", "search_error_late", "search_none_late"): tick[0] = 180
            if mode == "search_error_late": raise TimeoutError("OFFLINE")
            return None if mode == "search_none_late" else "offline index"
        def discover(html, **kwargs):
            if mode == "search_parse_late": tick[0] = 180
            if mode == "sleep_admission": tick[0] = 177
            return [candidate] if sum(k == "search" for k, _ in calls) == 1 else []
        def detail(url, **kwargs):
            calls.append(("detail", kwargs.get("timeout_seconds")))
            if mode in ("detail_denied", "detail_wrapped"):
                from urllib.error import HTTPError
                error = HTTPError(url, 403, "token=secret", {}, None)
                if mode == "detail_wrapped": raise RuntimeError("secret") from error
                raise error
            if mode == "detail_marker": return "您的访问过于频繁"
            if mode in ("detail_late", "detail_error_late", "detail_none_late"): tick[0] = 180
            if mode == "detail_error_late": raise TimeoutError("OFFLINE")
            return None if mode == "detail_none_late" else CORRECTION_FIXTURE
        original = query.parse_ccgp_event_html
        def parse(*args, **kwargs):
            if mode == "ordinary_parse_error": raise ValueError("OFFLINE_PARSE")
            value = original(*args, **kwargs)
            if mode in ("parse_late", "parse_none_late"): tick[0] = 180
            return None if mode == "parse_none_late" else value
        events, error = None, None
        with patch.object(query, "fetch_search_page", side_effect=search), patch.object(
                query, "parse_search_html", side_effect=discover), patch.object(
                query, "fetch_ccgp_detail_html", side_effect=detail), patch.object(
                query, "parse_ccgp_event_html", side_effect=parse), patch.object(query.time, "sleep", side_effect=sleep):
            try:
                events = query.scan_events("XCSD-2026-C-181", region="天津", start_date="2026:09:01",
                    end_date="2026:09:02", delay_seconds=4, observed_at="2026-09-02T00:00:00+00:00",
                    failures=failures, **({"budget": budget} if use_budget else {}),
                    **({"blocked_hosts": blocked_hosts} if use_guard else {}))
            except (CliBudgetExceeded, RuntimeError) as exc:
                error = exc
        return {"events": events, "error": error, "calls": calls, "failures": failures, "sleeps": sleeps, "blocked_hosts": blocked_hosts}

    def test_event_budget_zero_request_at_deadline_or_margin(self):
        for elapsed in (179, 180):
            with self.subTest(elapsed=elapsed):
                c = self.event_budget_scan_case(elapsed=elapsed)
                self.assertIsNotNone(c["error"])
                self.assertEqual(c["calls"], [])

    def test_event_budget_search_return_parse_and_exception_lateness(self):
        for mode in ("search_late", "search_none_late", "search_error_late", "search_parse_late"):
            with self.subTest(mode=mode):
                c = self.event_budget_scan_case(mode)
                self.assertIsNotNone(c["error"])
                self.assertEqual([kind for kind, _ in c["calls"]], ["search"])
                self.assertEqual(c["failures"], [])
                self.assertIsNone(c["events"])

    def test_event_budget_late_detail_parse_or_none_never_falls_back(self):
        for mode in ("detail_late", "detail_none_late", "detail_error_late", "parse_late", "parse_none_late"):
            with self.subTest(mode=mode):
                c = self.event_budget_scan_case(mode)
                self.assertIsNotNone(c["error"])
                self.assertEqual([kind for kind, _ in c["calls"]], ["search", "detail"])
                self.assertEqual(c["failures"], [])
                self.assertIsNone(c["events"])

    def test_event_budget_sleep_admission_and_wake_stop_before_detail(self):
        for mode in ("sleep_admission", "sleep_late"):
            c = self.event_budget_scan_case(mode)
            self.assertIsNotNone(c["error"])
            self.assertEqual([kind for kind, _ in c["calls"]], ["search"])
            self.assertEqual(c["sleeps"], [] if mode == "sleep_admission" else [4])

    def test_event_budget_timeout_uses_cap_and_remaining_minus_one(self):
        c = self.event_budget_scan_case()
        self.assertIsNone(c["error"])
        self.assertTrue(all(0 < timeout <= 30 for _, timeout in c["calls"]))
        near = self.event_budget_scan_case(elapsed=166)
        self.assertEqual(near["calls"][0], ("search", 13))

    def test_event_budget_and_default_ordinary_fallback_remain_compatible(self):
        for use_budget in (True, False):
            c = self.event_budget_scan_case("ordinary_parse_error", use_budget=use_budget)
            self.assertIsNone(c["error"])
            self.assertEqual(len(c["events"]), 1)
            self.assertEqual(len(c["failures"]), 1)
            self.assertTrue(c["events"][0]["requires_reconciliation"])
            if not use_budget: self.assertTrue(all(timeout is None for _, timeout in c["calls"]))

    def test_event_budget_does_not_break_query_regional_import_orders(self):
        import subprocess, sys
        for order in ("sync_ccgp_query;import sync_regional_ccgp", "sync_regional_ccgp;import sync_ccgp_query"):
            command = ("import sys\nsys.dont_write_bytecode=True\n"
                       "def offline(event,args):\n"
                       " if event=='import' and (args[0]=='vercel' or args[0].startswith('vercel.')): raise ImportError('REAL_SDK_FORBIDDEN')\n"
                       " if event in ('socket.connect','socket.getaddrinfo'): raise RuntimeError('NETWORK_FORBIDDEN')\n"
                       "sys.addaudithook(offline)\nsys.path.insert(0," + repr(str(ROOT / "scripts")) +
                       ");sys.path.insert(0," + repr(str(ROOT)) + ");import " + order)
            command += ("\nfrom sync_ccgp_query import discover_candidates,scan_events\n"
                        "scope={'search.ccgp.gov.cn':'HTTP_403'}\n"
                        "for fn,kw in [(discover_candidates,dict(keyword='医院',notice_types=['公开招标'])),"
                        "(scan_events,dict(project_number='p',observed_at='2026-11-06T00:00:00+00:00'))]:\n"
                        " try:fn(region='天津',start_date='2026-11-05',end_date='2026-11-06',delay_seconds=4,failures=[],blocked_hosts=scope,**kw)\n"
                        " except RuntimeError as e:assert 'ACCESS_BLOCKED' in str(e)\n"
                        " else:raise AssertionError('guard did not reject')\n")
            result = subprocess.run([sys.executable, "-B", "-c", command], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_guarded_event_search_denial_stops_second_type_without_fallback(self):
        for use_budget in (True, False):
            c = self.event_budget_scan_case("search_denied", use_budget=use_budget, use_guard=True)
            self.assertEqual([kind for kind, _ in c["calls"]], ["search"])
            self.assertIsNotNone(c["error"])
            self.assertIsNone(c["events"])
            self.assertEqual(c["blocked_hosts"], {"search.ccgp.gov.cn": "HTTP_429"})

    def test_guarded_event_detail_denial_never_builds_discovery_fallback(self):
        for mode in ("detail_denied", "detail_wrapped", "detail_marker"):
            for use_budget in (True, False):
                with self.subTest(mode=mode, use_budget=use_budget):
                    c = self.event_budget_scan_case(mode, use_budget=use_budget, use_guard=True)
                    self.assertIsNone(c["error"])
                    self.assertEqual(c["events"], [])
                    self.assertEqual(len(c["failures"]), 1)
                    self.assertIn("www.ccgp.gov.cn", c["blocked_hosts"])
                    self.assertNotIn("search.ccgp.gov.cn", c["blocked_hosts"])
                    self.assertEqual([kind for kind, _ in c["calls"]], ["search", "detail", "search"])

    def test_guard_is_opt_in_and_preserves_ordinary_discovery_fallback(self):
        default = self.event_budget_scan_case("detail_denied")
        self.assertEqual(len(default["events"]), 1)
        for use_guard in (True, False):
            ordinary = self.event_budget_scan_case("ordinary_parse_error", use_guard=use_guard)
            self.assertEqual(len(ordinary["events"]), 1)
            self.assertEqual(ordinary["blocked_hosts"], {} if use_guard else None)

    @classmethod
    def setUpClass(cls) -> None:
        cls.records = json.loads((ROOT / 'data' / 'tianjin_verified_seed.json').read_text(encoding='utf-8'))

    def test_exact_deadline_correction_becomes_resolved_override(self) -> None:
        event = parse_ccgp_event_text(
            CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='correction_xcsd_2026_c_181',
        )
        self.assertEqual(event['event_type'], 'CORRECTION')
        self.assertEqual(event['project_number'], 'XCSD-2026-C-181')
        self.assertFalse(event['requires_reconciliation'])
        self.assertEqual(event['changed_fact_paths'], ['facts.bid_deadline'])
        self.assertEqual(
            event['fact_overrides']['facts.bid_deadline'],
            '2026-09-18T09:30:00+08:00',
        )
        self.assertEqual(event['unresolved_fact_paths'], [])
        self.assertFalse(event['terminal'])

    def test_exact_response_submission_correction_maps_to_canonical_bid_deadline(self) -> None:
        event = parse_ccgp_event_text(
            RESPONSE_CORRECTION_FIXTURE,
            source_url=RESPONSE_CORRECTION_URL,
            observed_at='2026-05-20T12:00:00+08:00',
            event_id='correction_tgpc_2026_a_0081',
        )
        self.assertFalse(event['requires_reconciliation'])
        self.assertEqual(event['changed_fact_paths'], ['facts.bid_deadline'])
        self.assertEqual(
            event['fact_overrides']['facts.bid_deadline'],
            '2026-05-29T08:30:00+08:00',
        )

    def test_material_response_correction_stays_suppressed_despite_exact_deadline(self) -> None:
        event = parse_ccgp_event_text(
            MATERIAL_RESPONSE_CORRECTION_FIXTURE,
            source_url=RESPONSE_CORRECTION_URL,
            observed_at='2026-05-20T12:00:00+08:00',
            event_id='material_correction_tgpc_2026_a_0081',
        )
        self.assertEqual(
            event['fact_overrides']['facts.bid_deadline'],
            '2026-05-29T08:30:00+08:00',
        )
        self.assertTrue(event['requires_reconciliation'])
        self.assertIn('__material_correction__', event['unresolved_fact_paths'])

    def test_exact_correction_rebuilds_today_card_and_adds_event_evidence(self) -> None:
        event = parse_ccgp_event_text(
            CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='correction_xcsd_2026_c_181',
        )
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat('2026-09-01T12:00:00+08:00'),
            [event],
        )
        card = next(
            card
            for card in payload['cards']
            if card['opportunity_id'] == 'verified_bhcdc_2026_c_181'
        )
        self.assertEqual(card['facts']['bid_deadline'], '2026-09-18T09:30:00+08:00')
        self.assertIn(CORRECTION_URL, card['evidence_source_urls'])
        self.assertIn('OFFICIAL_CORRECTION_APPLIED', card['priority']['warnings'])

    def test_date_only_registration_change_remains_suppressed(self) -> None:
        event = parse_ccgp_event_text(
            INCOMPLETE_CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='incomplete_correction_xcsd_2026_c_181',
        )
        self.assertTrue(event['requires_reconciliation'])
        self.assertIn('facts.registration_deadline', event['unresolved_fact_paths'])
        self.assertEqual(
            event['fact_overrides']['facts.bid_deadline'],
            '2026-09-20T09:30:00+08:00',
        )
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat('2026-09-01T12:00:00+08:00'),
            [event],
        )
        self.assertNotIn(
            'verified_bhcdc_2026_c_181',
            {card['opportunity_id'] for card in payload['cards']},
        )

    def test_material_correction_remains_suppressed_even_when_deadline_is_exact(self) -> None:
        event = parse_ccgp_event_text(
            MATERIAL_CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='material_correction_xcsd_2026_c_181',
        )
        self.assertTrue(event['requires_reconciliation'])
        self.assertIn('__material_correction__', event['unresolved_fact_paths'])
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat('2026-09-01T12:00:00+08:00'),
            [event],
        )
        self.assertNotIn(
            'verified_bhcdc_2026_c_181',
            {card['opportunity_id'] for card in payload['cards']},
        )

    def test_termination_event_is_terminal(self) -> None:
        event = parse_ccgp_event_text(
            TERMINATION_FIXTURE,
            source_url='https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202608/t20260825_99999998.htm',
            observed_at='2026-08-25T19:00:00+08:00',
            event_id='termination_xcsd_2026_c_181',
        )
        self.assertEqual(event['event_type'], 'TERMINATION')
        self.assertEqual(event['published_at'], '2026-08-25')
        self.assertTrue(event['terminal'])

    def test_future_correction_does_not_apply_before_publication(self) -> None:
        event = parse_ccgp_event_text(
            CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='correction_xcsd_2026_c_181',
        )
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat('2026-08-31T15:00:00+08:00'),
            [event],
        )
        card = next(
            card
            for card in payload['cards']
            if card['opportunity_id'] == 'verified_bhcdc_2026_c_181'
        )
        self.assertEqual(card['facts']['bid_deadline'], '2026-09-14T09:30:00+08:00')
        self.assertNotIn(CORRECTION_URL, card['evidence_source_urls'])


if __name__ == '__main__':
    unittest.main()
