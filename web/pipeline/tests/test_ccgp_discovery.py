from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlparse

from medical_channel_pipeline.ccgp_discovery import build_search_url, parse_search_html


FIXTURE = """
<html><body>
<ul class="vT-srch-result-list-bid">
  <li>
    <a href="/cggg/dfgg/gkzb/202608/t20260827_27219613.htm">天津市胸科医院检验科设备租赁服务项目</a>
    <span>2026.08.27 10:30 | 采购人：天津市胸科医院 | 天津市 | 公开招标公告</span>
  </li>
  <li>
    <a href="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260827_27219685.htm">天津市泰达医院数字X光机（DR）采购项目</a>
    <span>2026-08-27 | 采购人:天津市泰达医院 | 天津市滨海新区 | 公开招标公告</span>
  </li>
  <li>
    <a href="http://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260827_27219711.htm">天津大学总医院直线加速器等设备维保服务</a>
    <span>2026-08-27 | 采购人:天津大学总医院 | 天津市 | 公开招标公告</span>
  </li>
</ul>
</body></html>
"""

EXTERNAL_FIXTURE = """
<html><body><ul class="vT-srch-result-list-bid"><li>
<a href="http://example.invalid/detail/1">外部链接</a>
<span>2026-08-27 | 采购人:测试 | 天津市 | 公开招标公告</span>
</li></ul></body></html>
"""


class CcgpDiscoveryTests(unittest.TestCase):
    def test_build_search_url_uses_tianjin_region_contract(self) -> None:
        url = build_search_url(
            keyword="检验科",
            notice_type="公开招标",
            page_index=2,
            start_date="2026-08-01",
            end_date="2026-08-31",
            region="天津",
        )
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "search.ccgp.gov.cn")
        self.assertEqual(params["kw"], ["检验科"])
        self.assertEqual(params["bidType"], ["1"])
        self.assertEqual(params["page_index"], ["2"])
        self.assertEqual(params["start_time"], ["2026:08:01"])
        self.assertEqual(params["end_time"], ["2026:08:31"])
        self.assertEqual(params["displayZone"], ["天津"])
        self.assertEqual(params["zoneId"], ["12"])

    def test_unsupported_region_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported region"):
            build_search_url(
                keyword="医疗",
                notice_type="公开招标",
                page_index=1,
                start_date="2026-08-01",
                end_date="2026-08-31",
                region="未配置地区",
            )

    def test_parse_search_html_yields_discovery_only_candidates(self) -> None:
        candidates = parse_search_html(FIXTURE, keyword="医疗")
        self.assertEqual(len(candidates), 3)
        first = candidates[0]
        self.assertEqual(first.evidence_status, "DISCOVERY_ONLY")
        self.assertEqual(first.published_at, "2026-08-27")
        self.assertEqual(first.buyer_name, "天津市胸科医院")
        self.assertEqual(first.region, "天津市")
        self.assertEqual(first.notice_type, "公开招标公告")
        self.assertTrue(first.detail_url.startswith("https://www.ccgp.gov.cn/"))

    def test_absolute_http_national_ccgp_link_is_upgraded_to_https(self) -> None:
        candidates = parse_search_html(FIXTURE, keyword="医疗")
        self.assertEqual(candidates[2].detail_url, "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260827_27219711.htm")

    def test_external_http_link_is_never_rewritten_into_trusted_ccgp_host(self) -> None:
        candidate = parse_search_html(EXTERNAL_FIXTURE, keyword="医疗")[0]
        self.assertEqual(candidate.detail_url, "http://example.invalid/detail/1")

    def test_rate_limit_page_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "CCGP_RATE_LIMITED"):
            parse_search_html("<html>您的访问过于频繁</html>", keyword="医疗")


if __name__ == "__main__":
    unittest.main()
