from __future__ import annotations

import copy
import unittest

from test_ccgp_award import _parse, TJ_MULTI_URL, TJ_MISDECLARED_URL
from test_public_snapshot_awards import AS_OF
from test_legal_windows import ccgp_record
from medical_channel_pipeline.ccgp_award import (
    _parse_amount_cny, awarded_project_keys, is_awarded_project,
    exclude_awarded_projects, public_award_ledger_entry,
)
from medical_channel_pipeline.award_price_reference import award_price_reference_rows
from medical_channel_pipeline.public_snapshot import build_public_snapshot
from medical_channel_pipeline.legal_windows import legal_windows_for_facts, refresh_legal_windows


class EvidenceBoundaryRegressionTests(unittest.TestCase):
    def award(self):
        return _parse('ccgp_award_tianjin_multi_package.html', TJ_MULTI_URL, market_code='TJ')

    def test_unitless_large_amount_is_unknown(self):
        self.assertIsNone(_parse_amount_cny('5733000'))

    def test_conflicting_units_are_unknown(self):
        self.assertIsNone(_parse_amount_cny('10元', header_hint='单价(万元)'))

    def test_explicit_units_still_parse(self):
        self.assertEqual(_parse_amount_cny('237.5', header_hint='金额(万元)'), 2375000)
        self.assertEqual(_parse_amount_cny('10,727,000.00元'), 10727000)

    def test_explicit_prices_and_raw_source_remain_available(self):
        award = self.award()
        rows = award_price_reference_rows([award], AS_OF)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['unit_price_cny'], 2375000)
        self.assertEqual(rows[0]['source_url'], TJ_MULTI_URL)
        ledger = public_award_ledger_entry(award, AS_OF)
        self.assertEqual(ledger['packages'][0]['amount_cny'], 2375000)
        self.assertEqual(ledger['total_amount_cny'], 9320000)

    def test_full_project_completion_requires_its_own_official_evidence(self):
        award = self.award()
        number = award['facts']['project_number']
        award['facts']['project_completion_confirmed'] = True
        self.assertFalse(is_awarded_project(awarded_project_keys([award], AS_OF), number, 'TJ'))
        evidence = {'field_path': 'facts.project_completion_confirmed', 'source_url': TJ_MULTI_URL, 'locator': 'Synthetic whole-project completion evidence'}
        award['evidence'].append(evidence)
        self.assertTrue(is_awarded_project(awarded_project_keys([award], AS_OF), number, 'TJ'))
        self.assertFalse(is_awarded_project(awarded_project_keys([award], AS_OF), number, 'HE'))
        evidence['source_url'] = TJ_MISDECLARED_URL
        self.assertFalse(is_awarded_project(awarded_project_keys([award], AS_OF), number, 'TJ'))

    def test_partial_result_cannot_close_project_even_with_completion_flag(self):
        award = self.award()
        award['facts']['project_completion_confirmed'] = True
        award['evidence'].append({'field_path': 'facts.project_completion_confirmed', 'source_url': TJ_MULTI_URL, 'locator': 'Synthetic conflicting scope'})
        for status in ('PARTIALLY_FAILED', 'ALL_PACKAGES_FAILED'):
            award['facts']['award_status'] = status
            self.assertEqual(awarded_project_keys([award], AS_OF), set())

    def test_misdeclared_price_not_repaired_or_published(self):
        record = _parse('ccgp_award_tianjin_unit_price_misdeclared.html', TJ_MISDECLARED_URL, market_code='TJ')
        item = record['facts']['items'][0]
        self.assertIsNone(item['unit_price_cny'])
        self.assertEqual(item['unit_price_raw'], '312000')
        self.assertEqual(record['source']['url'], TJ_MISDECLARED_URL)
        self.assertEqual(award_price_reference_rows([record], AS_OF), [])

    def test_legacy_price_without_unit_evidence_not_published(self):
        record = self.award()
        for item in record['facts']['items']:
            item.pop('unit_price_raw', None)
            item.pop('unit_price_header', None)
        self.assertEqual(award_price_reference_rows([record], AS_OF), [])
        self.assertTrue(all(item['unit_price_cny'] is None for item in public_award_ledger_entry(record, AS_OF)['items']))

    def test_partial_or_unproven_result_keeps_whole_project(self):
        award = self.award()
        candidate = ccgp_record()
        award['facts']['project_number'] = candidate['facts']['project_number']
        without = build_public_snapshot([candidate], AS_OF, [], [])
        self.assertEqual(len(without['opportunity_pool']), 1)
        for status in ('AWARDED', 'PARTIALLY_FAILED', 'ALL_PACKAGES_FAILED'):
            with self.subTest(status=status):
                award['facts']['award_status'] = status
                snapshot = build_public_snapshot([candidate], AS_OF, [], [award])
                self.assertEqual(snapshot['awarded_project_count'], 0)
                self.assertEqual(snapshot['opportunity_pool'], without['opportunity_pool'])

    def test_award_never_stops_correction_watch(self):
        award = self.award()
        numbers = [award['facts']['project_number']]
        self.assertEqual(exclude_awarded_projects(numbers, [award], AS_OF), (numbers, []))

    def test_missing_market_is_never_wildcard(self):
        award = self.award()
        award['facts'].pop('market_code')
        key = award['facts']['project_number']
        self.assertFalse(is_awarded_project(awarded_project_keys([award], AS_OF), key, 'HE'))
        self.assertFalse(is_awarded_project({(None, key.lower())}, key, 'TJ'))

    def test_unverified_regime_or_anchor_has_unknown_window(self):
        for facts in (
            {'registration_deadline': '2026-09-22', 'notice_type': '院内比选'},
            {'registration_deadline': '2026-09-22', 'notice_type': '公开招标公告'},
            {'lifecycle_state': 'AWARDED', 'published_at': '2026-09-28'},
            {'lifecycle_state': 'BIDDING'},
        ):
            with self.subTest(facts=facts):
                windows = legal_windows_for_facts(facts, AS_OF)
                self.assertIsNotNone(windows)
                window = windows[0]
                self.assertEqual(window['status'], 'UNKNOWN')
                self.assertIsNone(window['deadline_date'])

    def test_old_derived_deadline_not_promoted_by_refresh(self):
        old = [{'code': 'DOCUMENT_CHALLENGE', 'deadline_date': '2026-10-09', 'status': 'OPEN', 'remaining_working_days': 4}]
        before = copy.deepcopy(old)
        self.assertEqual(refresh_legal_windows(old, AS_OF)[0]['status'], 'UNKNOWN')
        self.assertEqual(old, before)
