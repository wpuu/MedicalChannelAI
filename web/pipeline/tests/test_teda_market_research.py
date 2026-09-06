from __future__ import annotations

import unittest

from medical_channel_pipeline.teda_market_research import (
    TedaParseError,
    parse_teda_market_research,
)

INDEX_URL = 'https://www.tedahospital.com.cn/article/plist/9/2'

DEMAND_FIXTURE = """
<html><body>
<h2>天津市泰达医院生物安全柜设备需求调研</h2>
<p>我院因工作需要，现计划开展医疗设备采购需求调研，欢迎符合资格要求的供应商报名。</p>
<p>一、拟采购设备项目：</p>
<p>1、生物安全柜 5台 预算15万；</p>
<p>二、报名资料及要求</p>
<p>需提供供应商及制造商资质、完整授权链、产品注册证、技术参数、配置清单、报价单和彩页。</p>
<p>三、调研文件提交</p>
<p>邮件发送至：tedamed@163.com</p>
<p>4、联系方式：何老师15822612462</p>
<p>四、报名截止时间：2026年7月29日</p>
<p>天津市泰达医院</p><p>2026年7月22日</p>
</body></html>
"""

ARGUMENT_FIXTURE = """
<html><body>
<h2>天津市泰达医院 高压氧舱介绍论证邀请公告</h2>
<p>我院拟进行医疗设备采购，近日将组织相关专家进行论证。</p>
<p>一、拟采购设备项目</p>
<p>1、高压氧舱 1套 预算250万元</p>
<p>二、报名资料及要求</p>
<p>三、报名方式及要求</p>
<p>1、报名截止时间：2026年9月4日下午4:00；</p>
<p>4、联系方式：耿老师19902103226</p>
<p>天津市泰达医院</p><p>2026年9月1日</p>
</body></html>
"""

NESTED_QUANTITY_FIXTURE = """
<html><body>
<h2>天津市泰达医院电子内窥镜系统等设备介绍论证邀请公告</h2>
<p>我院拟进行医疗设备采购，近日将组织相关专家进行论证。</p>
<p>一、拟采购设备项目：</p>
<p>1、设备明细： 1)电子内窥镜系统（高端2套、中端2套) 预算：920万元； 2)男性生理多参数检测仪 预算：42万元； 3)男性功能治疗仪 预算：42万元； 4）全自动化学发光免疫分析仪 预算：44万元；</p>
<p>2、其他需求：无</p>
<p>二、报名资料及要求</p>
<p>三、报名方式及要求</p>
<p>1、报名截止时间：2026年7月2日下午4:00；</p>
<p>4、联系方式：何老师15822612462</p>
<p>天津市泰达医院</p><p>2026年6月25日</p>
</body></html>
"""


def parse_fixture(
    html: str,
    *,
    source_url: str,
    expected_title: str,
    observed_at: str = '2026-09-01T18:00:00Z',
    opportunity_id: str,
    index_published_at: str | None,
):
    return parse_teda_market_research(
        html,
        source_url=source_url,
        index_url=INDEX_URL,
        index_published_at=index_published_at,
        expected_title=expected_title,
        observed_at=observed_at,
        opportunity_id=opportunity_id,
    )


class TedaMarketResearchTests(unittest.TestCase):
    def test_demand_research_becomes_verified_date_only_record(self) -> None:
        record = parse_fixture(
            DEMAND_FIXTURE,
            source_url='https://www.tedahospital.com.cn/article/show/9/901',
            expected_title='天津市泰达医院生物安全柜设备需求调研',
            opportunity_id='teda_901',
            index_published_at='2026-07-22',
        )
        facts = record['facts']
        self.assertEqual(facts['lifecycle_state'], 'MARKET_RESEARCH')
        self.assertEqual(facts['notice_type'], '设备需求调研')
        self.assertEqual(facts['published_at'], '2026-07-22')
        self.assertIsNone(facts['registration_deadline'])
        self.assertEqual(facts['registration_deadline_date'], '2026-07-29')
        self.assertEqual(facts['budget_cny'], 150000)
        self.assertEqual(facts['product_items'][0]['raw_name'], '生物安全柜')
        self.assertEqual(facts['product_items'][0]['quantity'], '5台')
        self.assertEqual(facts['public_contact']['name'], '何老师')
        self.assertEqual(facts['public_contact']['phone'], '15822612462')
        self.assertEqual(facts['public_contact']['email'], 'tedamed@163.com')
        self.assertIn('DEADLINE_TIME_NOT_PUBLISHED', record['quality_flags'])

    def test_argument_notice_preserves_exact_afternoon_deadline(self) -> None:
        record = parse_fixture(
            ARGUMENT_FIXTURE,
            source_url='https://tedahospital.com.cn/article/show/9/999',
            expected_title='天津市泰达医院 高压氧舱介绍论证邀请公告',
            opportunity_id='teda_999',
            index_published_at='2026-09-01',
        )
        facts = record['facts']
        self.assertEqual(facts['notice_type'], '医疗设备论证邀请')
        self.assertEqual(facts['registration_deadline'], '2026-09-04T16:00:00+08:00')
        self.assertIsNone(facts['registration_deadline_date'])
        self.assertEqual(facts['budget_cny'], 2500000)

    def test_nested_variant_quantities_do_not_truncate_product_name(self) -> None:
        record = parse_fixture(
            NESTED_QUANTITY_FIXTURE,
            source_url='https://www.tedahospital.com.cn/article/show/9/883',
            expected_title='天津市泰达医院电子内窥镜系统等设备介绍论证邀请公告',
            opportunity_id='teda_883',
            index_published_at='2026-06-25',
        )
        facts = record['facts']
        self.assertEqual(facts['budget_cny'], 10480000)
        self.assertEqual(
            [item['raw_name'] for item in facts['product_items']],
            ['电子内窥镜系统', '男性生理多参数检测仪', '男性功能治疗仪', '全自动化学发光免疫分析仪'],
        )
        first = facts['product_items'][0]
        self.assertIsNone(first['quantity'])
        self.assertEqual(first['specification'], '高端2套、中端2套')
        self.assertNotIn('设备明细', [item['raw_name'] for item in facts['product_items']])
        self.assertNotIn('其他需求', [item['raw_name'] for item in facts['product_items']])

    def test_nonmedical_early_signal_title_cannot_enter_fact_layer(self) -> None:
        html = DEMAND_FIXTURE.replace('医疗设备采购需求调研', '弱电设备采购需求调研')
        with self.assertRaisesRegex(TedaParseError, 'MEDICAL_EARLY_SIGNAL_NOT_VERIFIED'):
            parse_fixture(
                html,
                source_url='https://www.tedahospital.com.cn/article/show/9/901',
                expected_title='天津市泰达医院生物安全柜设备需求调研',
                opportunity_id='teda_901',
                index_published_at='2026-07-22',
            )

    def test_missing_deadline_fails_closed(self) -> None:
        html = DEMAND_FIXTURE.replace('四、报名截止时间：2026年7月29日', '四、报名截止时间：另行通知')
        with self.assertRaisesRegex(TedaParseError, 'REGISTRATION_DEADLINE_NOT_FOUND'):
            parse_fixture(
                html,
                source_url='https://www.tedahospital.com.cn/article/show/9/901',
                expected_title='天津市泰达医院生物安全柜设备需求调研',
                opportunity_id='teda_901',
                index_published_at='2026-07-22',
            )

    def test_title_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(TedaParseError, 'TITLE_MISMATCH'):
            parse_fixture(
                DEMAND_FIXTURE,
                source_url='https://www.tedahospital.com.cn/article/show/9/901',
                expected_title='天津市泰达医院其他设备需求调研',
                opportunity_id='teda_901',
                index_published_at='2026-07-22',
            )

    def test_unapproved_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(TedaParseError, 'SOURCE_URL_REJECTED'):
            parse_fixture(
                DEMAND_FIXTURE,
                source_url='https://example.com/article/show/9/901',
                expected_title='天津市泰达医院生物安全柜设备需求调研',
                opportunity_id='teda_901',
                index_published_at='2026-07-22',
            )

    def test_detail_and_index_publication_dates_must_agree(self) -> None:
        with self.assertRaisesRegex(TedaParseError, 'PUBLISHED_DATE_MISMATCH'):
            parse_fixture(
                DEMAND_FIXTURE,
                source_url='https://www.tedahospital.com.cn/article/show/9/901',
                expected_title='天津市泰达医院生物安全柜设备需求调研',
                opportunity_id='teda_901',
                index_published_at='2026-07-23',
            )

    def test_index_publication_date_is_allowed_when_detail_has_no_footer_date(self) -> None:
        html = DEMAND_FIXTURE.replace('<p>天津市泰达医院</p><p>2026年7月22日</p>', '')
        record = parse_fixture(
            html,
            source_url='https://www.tedahospital.com.cn/article/show/9/901',
            expected_title='天津市泰达医院生物安全柜设备需求调研',
            opportunity_id='teda_901',
            index_published_at='2026-07-22',
        )
        published_evidence = [
            item for item in record['evidence'] if item['field_path'] == 'facts.published_at'
        ][0]
        self.assertEqual(record['facts']['published_at'], '2026-07-22')
        self.assertEqual(published_evidence['source_url'], INDEX_URL)

    def test_missing_official_publication_date_is_explicitly_unsupported(self) -> None:
        html = DEMAND_FIXTURE.replace('<p>天津市泰达医院</p><p>2026年7月22日</p>', '')
        with self.assertRaisesRegex(TedaParseError, 'OFFICIAL_PUBLISHED_DATE_NOT_AVAILABLE'):
            parse_fixture(
                html,
                source_url='https://www.tedahospital.com.cn/article/show/9/901',
                expected_title='天津市泰达医院生物安全柜设备需求调研',
                opportunity_id='teda_901',
                index_published_at=None,
            )


if __name__ == '__main__':
    unittest.main()
