from __future__ import annotations

import unittest

from medical_channel_pipeline.tjzyefy_market_research import (
    TjzyefyParseError,
    parse_tjzyefy_market_research,
)

INDEX_URL = 'https://www.tjzyefy.com/xwgg/ggtz/'
OBSERVED_AT = '2026-09-05T16:24:41+00:00'
TITLE = '关于租赁算力服务器及配套网络专线的调研公告'
SOURCE_URL = 'https://www.tjzyefy.com/system/2026/08/10/030196192.shtml'


def page(body: str) -> str:
    return f'''<html><body>
      <h1>{TITLE}</h1>
      <div>2026-08-10 08:39 发布人：天津中医药大学第二附属医院</div>
      <p>天津中医药大学第二附属医院</p>
      <div>{body}</div>
    </body></html>'''


class TjzyefyStructuredComputeResearchTests(unittest.TestCase):
    def test_structured_medical_compute_research_is_grounded(self) -> None:
        html = page(
            '一、项目背景与目标 为满足我院医疗数据处理、科研分析及AI辅助诊断等业务需求。'
            '三、核心需求清单 '
            '1. 算力服务器（1台）：需配置高性能GPU，满足大模型微调、医疗影像分析等高并发计算需求。 '
            '2. 存储服务器（1台）：满足海量医疗影像及科研数据的存储与调用。 '
            '3. 数据专线（1条）：建设从数据中心至我院的点对点专线。 '
            '四、供应商资质与服务要求 数据安全须满足相关要求。 '
            '六、时间安排 方案报送截止：2026年8月14日17:00前 '
            '七、联系方式 技术咨询：022-60637725 王老师 方案及报价请发送邮箱：zyefyxxzx@163.com'
        )
        record = parse_tjzyefy_market_research(
            html,
            source_url=SOURCE_URL,
            index_url=INDEX_URL,
            index_published_at='2026-08-10',
            expected_title=TITLE,
            observed_at=OBSERVED_AT,
            opportunity_id='tjzyefy_20260810_030196192',
        )
        facts = record['facts']
        self.assertEqual(facts['lifecycle_state'], 'MARKET_RESEARCH')
        self.assertEqual(facts['notice_type'], '调研公告')
        self.assertEqual(facts['registration_deadline'], '2026-08-14T17:00:00+08:00')
        self.assertIsNone(facts['registration_deadline_date'])
        self.assertEqual(
            [item['raw_name'] for item in facts['product_items']],
            ['算力服务器', '存储服务器', '数据专线'],
        )
        self.assertEqual(facts['public_contact']['name'], '王老师')
        self.assertEqual(facts['public_contact']['phone'], '022-60637725')
        self.assertEqual(facts['public_contact']['email'], 'zyefyxxzx@163.com')
        lifecycle_evidence = next(
            item for item in record['evidence'] if item['field_path'] == 'facts.lifecycle_state'
        )
        self.assertIn('核心需求清单', lifecycle_evidence['locator'])
        self.assertNotIn('院内调研；', lifecycle_evidence['locator'])

    def test_generic_title_does_not_bypass_body_verification(self) -> None:
        html = page(
            '现就算力资源使用情况开展一般调研，请相关单位反馈意见。'
            '方案报送截止：2026年8月14日17:00前。'
        )
        with self.assertRaisesRegex(TjzyefyParseError, 'TJZYEFY_NOT_MARKET_RESEARCH'):
            parse_tjzyefy_market_research(
                html,
                source_url=SOURCE_URL,
                index_url=INDEX_URL,
                index_published_at='2026-08-10',
                expected_title=TITLE,
                observed_at=OBSERVED_AT,
                opportunity_id='tjzyefy_20260810_030196192',
            )


if __name__ == '__main__':
    unittest.main()
