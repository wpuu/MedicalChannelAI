from __future__ import annotations

import unittest
from datetime import date

from medical_channel_pipeline.tjmugh_discovery import (
    TjmughDiscoveryError,
    decode_tjmugh_html,
    parse_tjmugh_index_html,
    select_candidates_since,
    stable_opportunity_id,
)

INDEX_FIXTURE = """
<html><body>
<ul>
  <li><a href="/system/2026/08/25/030340001.shtml">天津医科大学总医院医疗设备项目市场调研论证邀请函</a><span>2026-08-25</span></li>
  <li><a href="https://www.tjmugh.com.cn/system/2026/08/20/030335555.shtml">天津医科大学总医院医疗设备项目市场调研论证邀请函</a><span>2026-08-20</span></li>
  <li><a href="http://www.tjmugh.com.cn/system/2026/08/31/030337994.shtml">天津医科大学总医院天津医科大学总医院医疗设备项目市场调研...</a><span>2026-08-31</span></li>
  <li><a href="/system/2026/08/25/030340002.shtml">天津医科大学总医院视频制作服务项目市场调研论证邀请函</a><span>2026-08-25</span></li>
  <li><a href="https://example.com/system/2026/08/25/030340003.shtml">医疗设备项目市场调研论证邀请函</a></li>
</ul>
</body></html>
"""


class TjmughDiscoveryTests(unittest.TestCase):
    def test_index_only_returns_supported_official_medical_equipment_notices(self) -> None:
        candidates = parse_tjmugh_index_html(INDEX_FIXTURE)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].published_at, '2026-08-31')
        self.assertTrue(candidates[0].detail_url.startswith('https://www.tjmugh.com.cn/system/'))
        self.assertIn('医疗设备', candidates[0].title)
        self.assertNotIn('视频制作', {item.title for item in candidates})

    def test_official_absolute_http_detail_link_is_upgraded_to_https(self) -> None:
        candidates = parse_tjmugh_index_html(INDEX_FIXTURE)
        current = next(item for item in candidates if item.published_at == '2026-08-31')
        self.assertEqual(
            current.detail_url,
            'https://www.tjmugh.com.cn/system/2026/08/31/030337994.shtml',
        )

    def test_missing_http_charset_can_recover_gb18030_index(self) -> None:
        html = (
            '<html><head><meta http-equiv="Content-Type" content="text/html; charset=gb2312"></head>'
            '<body><a href="/system/2026/08/31/030337994.shtml">'
            '天津医科大学总医院医疗设备项目市场调研论证邀请函</a></body></html>'
        )
        decoded = decode_tjmugh_html(html.encode('gb18030'), None)
        self.assertIn('天津医科大学总医院医疗设备项目市场调研论证邀请函', decoded)
        candidates = parse_tjmugh_index_html(decoded)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].published_at, '2026-08-31')

    def test_wrong_declared_utf8_can_still_recover_gb18030_body(self) -> None:
        html = (
            '<html><body><a href="/system/2026/08/31/030337994.shtml">'
            '天津医科大学总医院医疗设备项目市场调研论证邀请函</a></body></html>'
        )
        decoded = decode_tjmugh_html(html.encode('gb18030'), 'utf-8')
        self.assertIn('医疗设备', decoded)
        self.assertIn('市场调研', decoded)

    def test_stable_id_matches_existing_seed_contract(self) -> None:
        value = stable_opportunity_id(
            'https://www.tjmugh.com.cn/system/2026/08/05/030326488.shtml'
        )
        self.assertEqual(value, 'tjmugh_20260805_030326488')

    def test_candidate_window_is_date_bounded(self) -> None:
        candidates = parse_tjmugh_index_html(INDEX_FIXTURE)
        selected = select_candidates_since(
            candidates,
            start_date=date(2026, 8, 23),
            end_date=date(2026, 8, 25),
            max_candidates=10,
        )
        self.assertEqual([item.published_at for item in selected], ['2026-08-25'])

    def test_non_official_index_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(TjmughDiscoveryError, 'INDEX_HOST_REJECTED'):
            parse_tjmugh_index_html(INDEX_FIXTURE, index_url='https://example.com/index.shtml')


if __name__ == '__main__':
    unittest.main()
