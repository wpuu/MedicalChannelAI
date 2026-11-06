from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from medical_channel_pipeline.ccgp_detail import (
    _extract_grounded_text_product_items,
    _extract_package_products,
    html_to_text,
    parse_ccgp_competitive_consultation_text,
    parse_ccgp_public_tender_html,
    parse_ccgp_public_tender_text,
)
from test_ccgp_detail import FIXTURE, CONSULTATION_FIXTURE

FIXTURES = Path(__file__).parent / 'fixtures'
HTML = FIXTURES / 'ccgp_tianjin_dakoutun_20261105.html'
META = json.loads(HTML.with_suffix('.manifest.json').read_text())
EXPECTED = [
    ('彩色多普勒超声系统', '1台'), ('便携式彩色多普勒超声诊断仪', '1台'),
    ('数字化摄像X射线机', '1台'), ('X射线计算机体层摄影设备', '1台'),
    ('生物安全柜', '1台'), ('医用离心机', '1台'), ('空气消毒器', '2台'),
    ('颈腰椎治疗多功能牵引床', '1台'), ('红外偏振光治疗仪', '1台'), ('红外光悬空疗仪', '1台'),
]


class CcgpProductRequirementBoundaryTests(unittest.TestCase):
    def parse_official(self, html=None):
        return parse_ccgp_public_tender_html(
            HTML.read_text() if html is None else html, source_url=META['url'],
            observed_at=META['fetched_at'], opportunity_id=META['opportunity_id'],
        )

    def test_official_original_bytes_and_old_failure_are_frozen(self):
        self.assertEqual(hashlib.sha256(HTML.read_bytes()).hexdigest(), META['sha256'])
        self.assertEqual(len(META['before_product_names']), 4)
        self.assertIn('中小企业声明函', META['before_product_names'][1])

    def test_official_ten_products_keep_exact_names_and_quantities(self):
        items = self.parse_official()['facts']['product_items']
        self.assertEqual([(i['raw_name'], i['quantity']) for i in items], EXPECTED)
        self.assertTrue(all(i['category'] is None and i['specification'] is None for i in items))

    def test_official_identity_budget_and_windows_stay_grounded(self):
        facts = self.parse_official()['facts']
        self.assertEqual(facts['project_number'], 'ZLZH26ZB074')
        self.assertEqual(facts['buyer_name'], '天津市宝坻区大口屯医院')
        self.assertEqual(facts['budget_cny'], 2175000)
        self.assertEqual(facts['registration_deadline'], '2026-11-12T17:30:00+08:00')
        self.assertEqual(facts['bid_deadline'], '2026-11-26T09:30:00+08:00')

    def test_text_package_extractor_never_reads_the_official_qualification_chapter(self):
        self.assertEqual(_extract_package_products(html_to_text(HTML.read_text())), [])

    def test_valid_package_products_survive_later_repeated_package_labels(self):
        original = _extract_package_products(FIXTURE)
        text = FIXTURE.replace('二、申请人的资格要求：略',
            '二、申请人的资格要求：第1包：须提供营业执照。第2包：本包价格扣除20%。')
        self.assertEqual(_extract_package_products(text), original)
        self.assertEqual(len(original), 2)

    def test_requirement_only_package_labels_cannot_create_products(self):
        for heading in ['二、申请人的资格要求：', '二.申请人资格要求:', '二、供应商资格要求：', '二、投标人的资格要求：']:
            with self.subTest(heading=heading):
                text = '采购需求：详见附件。' + heading + '第1包：医疗器械经营许可证。第2包：中小企业声明函。'
                self.assertEqual(_extract_package_products(text), [])
                self.assertEqual(_extract_grounded_text_product_items(text), [])

    def test_quantified_qualification_equipment_does_not_leak_into_grounded_products(self):
        text = '采购需求：详见附件。二、申请人的资格要求：需购置生物显微镜3台、超声设备2套。'
        self.assertEqual(_extract_grounded_text_product_items(text), [])

    def test_contract_and_acquisition_sections_are_not_product_demand(self):
        for boundary in ['合同履行期限：', '合同履约期限：', '三、获取招标文件', '三、获取采购文件']:
            with self.subTest(boundary=boundary):
                self.assertEqual(_extract_package_products('采购需求：详见附件。' + boundary + '第1包：营业执照。'), [])

    def test_missing_demand_anchor_does_not_use_qualification_as_a_fallback(self):
        self.assertEqual(_extract_package_products('二、申请人的资格要求：第1包：营业执照。'), [])

    def test_competitive_consultation_uses_the_same_package_boundary(self):
        text = CONSULTATION_FIXTURE.replace('二、申请人的资格要求：略',
            '二、申请人的资格要求：第1包：医疗器械经营许可证。')
        record = parse_ccgp_competitive_consultation_text(text,
            source_url='https://www.ccgp.gov.cn/cggg/dfgg/jzxcs/202605/t20260515_00000001.htm',
            observed_at='2026-05-15T18:00:00+08:00', opportunity_id='ccgp_consultation_boundary')
        self.assertEqual(record['facts']['product_items'], [])

    def test_qualification_changes_do_not_change_extracted_products(self):
        html = HTML.read_text().replace('本包非专门面向中小企业采购', '第99包：需购置核磁共振99台，营业执照99份')
        self.assertEqual(self.parse_official(html)['facts']['product_items'], self.parse_official()['facts']['product_items'])
