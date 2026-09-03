from __future__ import annotations

import unittest

from medical_channel_pipeline.tjfch_test_discovery import (
    INDEX_URL,
    TjfchTestDiscoveryError,
    parse_tjfch_test_index_html,
)


class TjfchTestDiscoveryTests(unittest.TestCase):
    def test_official_ywgk_entry_discovers_only_test_enterprise_recruitment(self) -> None:
        html = '''
        <html><body>
          <a href="/system/2026/06/09/030192069.shtml">天津市第一中心医院共享设备调度系统项目测试企业征集公告</a>
          <a href="/system/2026/06/18/030192796.shtml">天津市第一中心医院项目成本和DRG成本核算系统测试企业征集公告</a>
          <a href="/system/2026/06/20/030192999.shtml">天津市第一中心医院项目成本和DRG成本核算系统项目测试评分细则公示</a>
          <a href="/system/2026/06/21/030193000.shtml">天津市第一中心医院显微镜摄像头项目院内比选公告</a>
        </body></html>
        '''
        items = parse_tjfch_test_index_html(html)
        self.assertEqual(INDEX_URL, "https://www.tjfch.com.cn/ywgk/")
        self.assertEqual([item.title for item in items], [
            "天津市第一中心医院共享设备调度系统项目测试企业征集公告",
            "天津市第一中心医院项目成本和DRG成本核算系统测试企业征集公告",
        ])

    def test_discovery_does_not_claim_url_path_date_is_publication_date(self) -> None:
        html = '''
        <a href="/system/2026/06/09/030192069.shtml">天津市第一中心医院共享设备调度系统项目测试企业征集公告</a>
        '''
        item = parse_tjfch_test_index_html(html)[0]
        self.assertFalse(hasattr(item, "published_at"))
        self.assertIn("/2026/06/09/", item.detail_url)

    def test_external_and_duplicate_links_are_ignored(self) -> None:
        html = '''
        <a href="https://evil.example/system/2026/06/09/030192069.shtml">天津市第一中心医院共享设备调度系统项目测试企业征集公告</a>
        <a href="/system/2026/06/09/030192069.shtml">天津市第一中心医院共享设备调度系统项目测试企业征集公告</a>
        <a href="/system/2026/06/09/030192069.shtml">天津市第一中心医院共享设备调度系统项目测试企业征集公告</a>
        '''
        items = parse_tjfch_test_index_html(html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].detail_url, "https://www.tjfch.com.cn/system/2026/06/09/030192069.shtml")

    def test_candidate_cap_is_bounded(self) -> None:
        html = ''.join(
            f'<a href="/system/2026/06/{10 + i:02d}/{30192000 + i}.shtml">天津市第一中心医院测试项目{i}测试企业征集公告</a>'
            for i in range(3)
        )
        self.assertEqual(len(parse_tjfch_test_index_html(html, max_candidates=2)), 2)

    def test_legacy_broken_tls_domain_is_rejected_as_test_index(self) -> None:
        with self.assertRaisesRegex(TjfchTestDiscoveryError, "TJFCH_TEST_INDEX_HOST_REJECTED"):
            parse_tjfch_test_index_html(
                '<a href="/system/2026/07/07/030193968.shtml">天津市第一中心医院出生缺陷防控系统项目测试企业征集公告</a>',
                index_url="https://www.tj-fch.com/ywgk/",
            )


if __name__ == "__main__":
    unittest.main()
