from __future__ import annotations

import unittest

from medical_channel_pipeline.tjfch_procurement import TjfchParseError, parse_tjfch_procurement_notice


SOURCE_URL = 'https://www.tjfch.com.cn/system/2026/05/06/030189759.shtml'
INDEX_URL = 'https://www.tjfch.com.cn/ywgk/ynbx/index.shtml'
TITLE = '天津市第一中心医院手术无影灯采购项目院内比选公告'
IGM_SOURCE_URL = 'https://www.tjfch.com.cn/system/2026/08/31/030197537.shtml'
IGM_INDEX_TITLE = '天津市第一中心医院甲型肝炎病毒IgM抗体质控品等采购项目院内比选...'
IGM_FULL_TITLE = '天津市第一中心医院甲型肝炎病毒IgM抗体质控品等采购项目院内比选公告'


def verified_html(*, title: str = TITLE, deadline: str = '2026年5月13日14:00') -> str:
    return f'''
    <html><body>
      <h1>{title}</h1>
      <div>2026-05-06 15:43</div>
      <p>天津市第一中心医院将以院内比选方式，对手术无影灯采购项目实施采购。</p>
      <p>项目编号：YNBX-2026-G-6003。</p>
      <p>项目预算：19800元。</p>
      <p>院内比选响应文件递交截止时间：{deadline}。</p>
      <p>政务邮箱：sdyzxsbwzcsbk@tj.gov.cn</p>
      <p>联系电话：022-23628323</p>
      <p>联系人：王老师</p>
    </body></html>
    '''


def igm_html(*, title: str = IGM_FULL_TITLE) -> str:
    return f'''
    <html><body>
      <h1>{title}</h1>
      <div>2026-08-31 16:10</div>
      <p>天津市第一中心医院将以院内比选方式，对甲型肝炎病毒IgM抗体质控品等实施采购。</p>
      <p>项目预算：4588元。</p>
      <p>院内比选响应文件递交截止时间：2026年9月7日17:00。</p>
      <p>联系电话：022-23628323</p>
      <p>联系人：王老师</p>
    </body></html>
    '''


class TjfchProcurementTests(unittest.TestCase):
    def parse(self, html: str) -> dict:
        return parse_tjfch_procurement_notice(
            html,
            source_url=SOURCE_URL,
            index_url=INDEX_URL,
            index_published_at='2026-05-06',
            expected_title=TITLE,
            observed_at='2026-05-06T08:00:00+00:00',
            opportunity_id='tjfch_20260506_030189759',
        )

    def parse_igm(self, html: str) -> dict:
        return parse_tjfch_procurement_notice(
            html,
            source_url=IGM_SOURCE_URL,
            index_url=INDEX_URL,
            index_published_at='2026-08-31',
            expected_title=IGM_INDEX_TITLE,
            observed_at='2026-09-03T04:00:00+00:00',
            opportunity_id='tjfch_20260831_030197537',
        )

    def test_verified_medical_equipment_notice_becomes_bidding_record(self) -> None:
        record = self.parse(verified_html())
        facts = record['facts']
        self.assertEqual(facts['project_number'], 'YNBX-2026-G-6003')
        self.assertEqual(facts['buyer_name'], '天津市第一中心医院')
        self.assertEqual(facts['hospital_name'], '天津市第一中心医院')
        self.assertEqual(facts['lifecycle_state'], 'BIDDING')
        self.assertEqual(facts['notice_type'], '院内比选采购公告')
        self.assertEqual(facts['published_at'], '2026-05-06')
        self.assertEqual(facts['bid_deadline'], '2026-05-13T14:00:00+08:00')
        self.assertEqual(facts['budget_cny'], 19800)
        self.assertEqual(facts['procurement_method'], '院内比选')
        self.assertEqual(facts['public_contact']['name'], '王老师')
        self.assertEqual(facts['public_contact']['phone'], '022-23628323')
        self.assertEqual(facts['public_contact']['email'], 'sdyzxsbwzcsbk@tj.gov.cn')

    def test_truncated_index_title_recovers_full_medical_procurement_title_from_detail_h1(self) -> None:
        record = self.parse_igm(igm_html())
        facts = record['facts']
        self.assertEqual(facts['project_name'], IGM_FULL_TITLE)
        self.assertEqual(facts['published_at'], '2026-08-31')
        self.assertEqual(facts['budget_cny'], 4588)
        self.assertEqual(facts['bid_deadline'], '2026-09-07T17:00:00+08:00')
        self.assertEqual(record['opportunity_id'], 'tjfch_20260831_030197537')
        self.assertEqual(record['source']['url'], IGM_SOURCE_URL)

    def test_truncated_ambiguous_candidate_resolving_to_result_is_unsupported(self) -> None:
        result_title = '天津市第一中心医院甲型肝炎病毒IgM抗体质控品等采购项目院内比选结果公示'
        with self.assertRaisesRegex(TjfchParseError, 'TJFCH_NOTICE_TYPE_UNSUPPORTED'):
            self.parse_igm(igm_html(title=result_title))

    def test_truncated_candidate_requires_matching_detail_h1(self) -> None:
        with self.assertRaisesRegex(TjfchParseError, 'TJFCH_TITLE_MISMATCH'):
            self.parse_igm(igm_html(title='天津市第一中心医院其他采购项目院内比选公告'))

    def test_relative_deadline_is_not_invented(self) -> None:
        html = verified_html(deadline='本公告期限结束后5日内')
        with self.assertRaisesRegex(TjfchParseError, 'TJFCH_BID_DEADLINE_NOT_EXACT'):
            self.parse(html)

    def test_title_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(TjfchParseError, 'TJFCH_TITLE_MISMATCH'):
            self.parse(verified_html(title='天津市第一中心医院其他项目院内比选公告'))

    def test_detail_published_date_must_be_confirmed_on_page(self) -> None:
        html = verified_html().replace('2026-05-06 15:43', '发布日期未提供')
        with self.assertRaisesRegex(TjfchParseError, 'TJFCH_DETAIL_PUBLISHED_DATE_NOT_CONFIRMED'):
            self.parse(html)

    def test_afternoon_deadline_is_normalized_to_24_hour_time(self) -> None:
        record = self.parse(verified_html(deadline='2026年5月13日下午2:30'))
        self.assertEqual(record['facts']['bid_deadline'], '2026-05-13T14:30:00+08:00')

    def test_legacy_domain_is_rejected_even_with_valid_detail_shape(self) -> None:
        with self.assertRaisesRegex(TjfchParseError, 'TJFCH_SOURCE_HOST_REJECTED'):
            parse_tjfch_procurement_notice(
                verified_html(),
                source_url='https://www.tj-fch.com/system/2026/05/06/030189759.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-05-06',
                expected_title=TITLE,
                observed_at='2026-05-06T08:00:00+00:00',
                opportunity_id='tjfch_20260506_030189759',
            )


if __name__ == '__main__':
    unittest.main()
