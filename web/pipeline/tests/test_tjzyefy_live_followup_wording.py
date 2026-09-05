from __future__ import annotations

import unittest

from medical_channel_pipeline.tjzyefy_procurement_intent import (
    OFFICIAL_FOLLOWUP_SOURCE_PREFIX,
    OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC,
    parse_tjzyefy_procurement_intent,
)


class TjzyefyLiveFollowupWordingTests(unittest.TestCase):
    def test_real_legacy_tianjin_procurement_site_wording_is_preserved(self) -> None:
        title = '采购意向公告（2026年48号）-云影像服务项目'
        html = f'''
        <html><body>
          <h1>{title}</h1>
          <div>2026-08-04 14:10 发布人：天津中医药大学第二附属医院</div>
          <p>天津中医药大学第二附属医院</p>
          <p>我院将于近期对天津中医药大学第二附属医院云影像服务项目进行采购，欢迎各位有资质的服务商咨询。
          预计采购时间2026年9-10月。
          本项目具体招标信息请关注：天津市政采网（http://tjgp.cz.tj.gov.cn/）
          联系电话：022-60637523、022-60372615 联 系 人：刘老师、赵老师</p>
        </body></html>
        '''
        record = parse_tjzyefy_procurement_intent(
            html,
            source_url='https://www.tjzyefy.com/system/2026/08/04/030195992.shtml',
            index_url='https://www.tjzyefy.com/xwgg/ggtz/',
            index_published_at='2026-08-04',
            expected_title=title,
            observed_at='2026-09-05T03:30:00+00:00',
            opportunity_id='tjzyefy_intent_20260804_030195992',
        )
        self.assertIn(
            f'{OFFICIAL_FOLLOWUP_SOURCE_PREFIX}{OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC}',
            record.get('quality_flags', []),
        )


if __name__ == '__main__':
    unittest.main()
