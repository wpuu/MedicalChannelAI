from __future__ import annotations

import unittest

from medical_channel_pipeline.tjzxfc_market_research import (
    TjzxfcParseError,
    parse_tjzxfc_market_research,
)

INDEX_URL = 'https://www.tjzxfc.cn/ywgk/zbgg/index.shtml'
OBSERVED_AT = '2026-09-04T10:50:00+00:00'


class TjzxfcMarketResearchTests(unittest.TestCase):
    def test_medical_equipment_preprocurement_research_becomes_verified_record(self) -> None:
        html = '''
        <html><body>
          <h1>设备科医用设备采购前市场调研</h1>
          <div>时间： 2026-03-31 来源：设备科</div>
          <p>天津市中心妇产科医院设备科现对以下医用设备进行市场调研，请相关经销商按经营范围完成调研问卷填报，填报提交时间截至到2026年04月10日（周五）17：00点。</p>
          <table>
            <tr><th>项目序号</th><th>调研设备</th><th>诊疗用途</th></tr>
            <tr><td>1</td><td>乳管镜</td><td>用于乳头溢液检查和治疗</td></tr>
            <tr><td>2</td><td>染色体扫描分析系统</td><td>用于染色体核型分析</td></tr>
            <tr><td>3</td><td>采血贴管机</td><td>自动给采血管打印和粘贴条码</td></tr>
          </table>
          <p>天津市中心妇产科医院 设备科 2026-03-31</p>
        </body></html>
        '''
        record = parse_tjzxfc_market_research(
            html,
            source_url='https://www.tjzxfc.cn/system/2026/03/31/030269964.shtml',
            index_url=INDEX_URL,
            index_published_at='2026-03-31',
            expected_title='设备科医用设备采购前市场调研',
            observed_at=OBSERVED_AT,
            opportunity_id='tjzxfc_20260331_030269964',
        )
        facts = record['facts']
        self.assertEqual(facts['hospital_name'], '天津市中心妇产科医院')
        self.assertEqual(facts['lifecycle_state'], 'MARKET_RESEARCH')
        self.assertEqual(facts['registration_deadline'], '2026-04-10T17:00:00+08:00')
        self.assertIsNone(facts.get('registration_deadline_date'))
        self.assertEqual([item['raw_name'] for item in facts['product_items']], ['乳管镜', '染色体扫描分析系统', '采血贴管机'])
        self.assertEqual(facts['department'], '设备科')

    def test_pathology_device_title_is_kept_because_detail_proves_medical_scope(self) -> None:
        html = '''
        <html><body>
          <h1>天津市中心妇产科医院 载玻片打号机采购项目市场调研邀请公告</h1>
          <div>时间： 2026-07-08 来源：信息科</div>
          <p>为进一步规范我院病理科标本标识管理，根据科室设备采购计划，我院拟开展病理科载玻片打号机采购项目院内论证工作，现面向社会公开邀请供应商参与本次市场调研。</p>
          <p>资料提交截止时间：2026年7月15日17:00。</p>
          <p>天津市中心妇产科医院</p>
        </body></html>
        '''
        record = parse_tjzxfc_market_research(
            html,
            source_url='https://www.tjzxfc.cn/system/2026/07/08/030313811.shtml',
            index_url=INDEX_URL,
            index_published_at='2026-07-08',
            expected_title='天津市中心妇产科医院 载玻片打号机采购项目市场调研邀请公告',
            observed_at=OBSERVED_AT,
            opportunity_id='tjzxfc_20260708_030313811',
        )
        item = record['facts']['product_items'][0]
        self.assertEqual(item['raw_name'], '载玻片打号机')
        self.assertEqual(item['category'], '病理')
        self.assertEqual(record['facts']['registration_deadline'], '2026-07-15T17:00:00+08:00')

    def test_date_only_deadline_is_preserved_without_invented_time(self) -> None:
        html = '''
        <h1>天津市中心妇产科医院病理设备采购项目市场调研公告</h1>
        <div>时间：2026-08-20 来源：设备科</div>
        <p>天津市中心妇产科医院拟对病理设备开展市场调研。报名时限：自公告发布之日起至2026年8月25日。</p>
        '''
        record = parse_tjzxfc_market_research(
            html,
            source_url='https://www.tjzxfc.cn/system/2026/08/20/030333150.shtml',
            index_url=INDEX_URL,
            index_published_at='2026-08-20',
            expected_title='天津市中心妇产科医院病理设备采购项目市场调研公告',
            observed_at=OBSERVED_AT,
            opportunity_id='tjzxfc_20260820_030333150',
        )
        self.assertIsNone(record['facts']['registration_deadline'])
        self.assertEqual(record['facts']['registration_deadline_date'], '2026-08-25')
        self.assertIn('DEADLINE_TIME_NOT_PUBLISHED', record['quality_flags'])

    def test_generic_facility_market_research_is_rejected_by_medical_scope(self) -> None:
        html = '''
        <h1>天津市中心妇产科医院报告厅提升改造项目市场调研邀请公告</h1>
        <div>时间：2026-08-17 来源：信息科</div>
        <p>天津市中心妇产科医院拟对报告厅音视频、显示屏、扩声和网络系统进行提升改造，现开展市场调研。</p>
        <p>截止时间：2026年8月24日17:00。</p>
        '''
        with self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_NON_MEDICAL_EARLY_SIGNAL'):
            parse_tjzxfc_market_research(
                html,
                source_url='https://www.tjzxfc.cn/system/2026/08/17/030331860.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-08-17',
                expected_title='天津市中心妇产科医院报告厅提升改造项目市场调研邀请公告',
                observed_at=OBSERVED_AT,
                opportunity_id='tjzxfc_20260817_030331860',
            )

    def test_title_and_publication_date_must_match_official_index_identity(self) -> None:
        html = '''
        <h1>设备科医用设备采购前市场调研</h1>
        <div>时间：2026-04-01 来源：设备科</div>
        <p>天津市中心妇产科医院医用设备市场调研，截止时间2026年4月10日17:00。</p>
        '''
        with self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_PUBLISHED_DATE_MISMATCH'):
            parse_tjzxfc_market_research(
                html,
                source_url='https://www.tjzxfc.cn/system/2026/03/31/030269964.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-03-31',
                expected_title='设备科医用设备采购前市场调研',
                observed_at=OBSERVED_AT,
                opportunity_id='tjzxfc_20260331_030269964',
            )

    def test_non_official_detail_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_SOURCE_HOST_REJECTED'):
            parse_tjzxfc_market_research(
                '<p>天津市中心妇产科医院 医用设备市场调研 截止时间2026年4月10日17:00</p>',
                source_url='https://example.com/system/2026/03/31/030269964.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-03-31',
                expected_title='设备科医用设备采购前市场调研',
                observed_at=OBSERVED_AT,
                opportunity_id='tjzxfc_20260331_030269964',
            )


if __name__ == '__main__':
    unittest.main()
