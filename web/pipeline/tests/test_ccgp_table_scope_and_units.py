import hashlib
import json
from pathlib import Path
import unittest

from medical_channel_pipeline.ccgp_detail import (
    CcgpDetailParseError, _extract_general_product_table_items,
    _extract_standard_product_table_items, _procurement_html_scope,
    parse_ccgp_public_tender_html, parse_ccgp_competitive_consultation_html,
)
from medical_channel_pipeline.channel_scope import is_medical_channel_relevant_record
from test_ccgp_detail import CONSULTATION_FIXTURE
from test_ccgp_product_table_variants import page

CORPUS = Path(__file__).parent / 'fixtures/ccgp_template_audit_20261106'
GENERAL = '<table><tr><th>设备名称</th><th>数量（套）</th></tr><tr><td>乳腺机</td><td>1</td></tr></table>'
STANDARD = '<table><tr><th>品目名称</th><th>采购标的</th><th>数量（套）</th></tr><tr><td>放射设备</td><td>乳腺机</td><td>1</td></tr></table>'


class CcgpTableScopeAndUnitTests(unittest.TestCase):
    def parse(self, html):
        return parse_ccgp_public_tender_html(html,
            source_url='https://www.ccgp.gov.cn/cggg/zygg/gkzb/202609/t20260908_27289494.htm',
            observed_at='2026-11-06T11:05:33+00:00', opportunity_id='ccgp_scope_units')

    def test_all_frozen_official_and_derived_cases_meet_independent_expectations(self):
        for case in json.loads((CORPUS / 'manifest.json').read_text())['cases']:
            with self.subTest(case=case['label']):
                raw = (CORPUS / case['file']).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), case['sha256'])
                record = parse_ccgp_public_tender_html(raw.decode(case['encoding']), source_url=case['url'],
                    observed_at=case['fetched_at'], opportunity_id=case['label'])
                self.assertEqual([[i['raw_name'], i['quantity']] for i in record['facts']['product_items']], case['expected_pairs'])
                self.assertEqual(is_medical_channel_relevant_record(record), case['expected_medical_relevant'])

    def test_table_after_qualification_or_document_heading_cannot_replace_demand(self):
        for table in (GENERAL, STANDARD):
            for heading in ('二、申请人的资格要求：', '三、获取招标文件', '四、提交投标文件'):
                with self.subTest(table=table, heading=heading):
                    scope = _procurement_html_scope('<p>采购需求：详见附件。</p><p>'+heading+'</p>'+table)
                    self.assertEqual(_extract_general_product_table_items(scope), [])
                    self.assertEqual(_extract_standard_product_table_items(scope), [])

    def test_contract_table_is_ignored_but_next_package_is_retained(self):
        html = '<p>采购需求：</p><p>合同包1(设备)：</p>'+GENERAL+'<p>合同履行期限：</p>'+STANDARD+'<p>合同包2(设备)：</p>'+GENERAL.replace('乳腺机','超声设备')+'<p>二、申请人的资格要求：</p>'+STANDARD
        scope = _procurement_html_scope(html)
        items = _extract_general_product_table_items(scope)
        self.assertEqual([i['raw_name'] for i in items], ['乳腺机', '超声设备'])

    def test_contract_prose_mentioning_another_package_cannot_reopen_scope(self):
        html = '<p>采购需求：</p>'+GENERAL+'<p>合同履行期限：30日，详见合同包2(其他服务)条款。</p>'+STANDARD
        items = _extract_general_product_table_items(_procurement_html_scope(html))
        self.assertEqual([(i['raw_name'], i['category']) for i in items], [('乳腺机',None)])

    def test_split_inline_anchor_and_encoded_colon_preserve_real_table(self):
        html = '<p><span>采购</span><span>需求</span>&#65306;</p>'+GENERAL+'<p>二、申请人的资格要求：</p>'+STANDARD
        items = _extract_general_product_table_items(_procurement_html_scope(html))
        self.assertEqual([(i['raw_name'], i['quantity']) for i in items], [('乳腺机','1套')])

    def test_missing_anchor_and_script_decoy_do_not_enable_tables(self):
        for html in (GENERAL, '<script>采购需求：</script>'+GENERAL):
            self.assertEqual(_procurement_html_scope(html), '')

    def test_unit_is_not_duplicated_when_already_in_quantity(self):
        for quantity in ('1套','1(套)'):
            table = GENERAL.replace('<td>1</td>', '<td>'+quantity+'</td>')
            self.assertEqual(self.parse(page(table))['facts']['product_items'][0]['quantity'], quantity)

    def test_cell_header_and_separate_unit_conflicts_fail_closed(self):
        samples = [GENERAL.replace('<td>1</td>', '<td>1台</td>'),
            GENERAL.replace('</tr><tr>', '<th>单位</th></tr><tr>').replace('<td>1</td>', '<td>1</td><td>台</td>'),
            STANDARD.replace('<td>1</td>', '<td>1台</td>')]
        for table in samples:
            with self.subTest(table=table):
                with self.assertRaisesRegex(CcgpDetailParseError, 'QUANTITY_UNIT_CONFLICT'):
                    self.parse(page(table))

    def test_ambiguous_header_can_preserve_or_narrow_to_explicit_cell_unit(self):
        table = GENERAL.replace('（套）', '（台/套）')
        self.assertEqual(self.parse(page(table))['facts']['product_items'][0]['quantity'], '1台/套')
        self.assertEqual(self.parse(page(table.replace('<td>1</td>','<td>1台</td>')))['facts']['product_items'][0]['quantity'], '1台')

    def test_standard_header_unit_is_used_when_cell_has_only_number(self):
        self.assertEqual(_extract_standard_product_table_items(STANDARD)[0]['quantity'], '1套')

    def test_unknown_header_unit_is_not_silently_dropped(self):
        with self.assertRaisesRegex(CcgpDetailParseError, 'UNIT_UNSUPPORTED'):
            self.parse(page(GENERAL.replace('（套）', '（未知单位）')))

    def test_unknown_separate_unit_does_not_fall_back_to_incomplete_text(self):
        table = GENERAL.replace('（套）','').replace('</tr><tr>','<th>单位</th></tr><tr>').replace('<td>1</td>','<td>1</td><td>未知单位</td>')
        with self.assertRaisesRegex(CcgpDetailParseError, 'UNIT_UNSUPPORTED'):
            self.parse(page(table))

    def test_consultation_html_uses_same_table_boundaries(self):
        before, after = CONSULTATION_FIXTURE.split('二、申请人的资格要求',1)
        html = '<pre>'+before+'</pre>'+GENERAL+'<pre>二、申请人的资格要求'+after+'</pre>'+STANDARD
        record = parse_ccgp_competitive_consultation_html(html,
            source_url='https://www.ccgp.gov.cn/cggg/dfgg/jzxcs/202605/t20260515_26577430.htm',
            observed_at='2026-11-06T11:05:33+00:00', opportunity_id='ccgp_consult_scope')
        self.assertEqual([(i['raw_name'], i['quantity']) for i in record['facts']['product_items']], [('乳腺机','1套')])
