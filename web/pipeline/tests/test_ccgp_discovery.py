from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlparse

from medical_channel_pipeline.ccgp_discovery import (
    build_search_url,
    is_primary_opportunity_candidate,
    parse_search_html,
)


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

LABELED_REGION_FIXTURE = """
<html><body>
<ul class="vT-srch-result-list-bid">
  <li>
    <a href="/cggg/dfgg/gkzb/202609/t20260907_27280838.htm">北京市某医院医疗设备采购项目</a>
    <span>2026.09.07 16:02 | 地域：北京 | 采购人：北京市某医院 | 公开招标公告</span>
  </li>
  <li>
    <a href="/cggg/dfgg/gkzb/202609/t20260907_27280839.htm">河北省某医院医疗设备采购项目</a>
    <span>2026.09.07 15:20 行政区域：河北省 | 采购人：河北省某医院</span>
  </li>
</ul>
</body></html>
"""

CURRENT_BARE_REGION_FIXTURE = """
<html><body>
<ul class="vT-srch-result-list-bid">
  <li>
    <a href="/cggg/zygg/gkzb/202609/t20260907_27280838.htm"><em>中国中医科学院广安门医院</em>设备采购项目</a>
    <p>项目概况……</p>
    <span>2026.09.07 17:21</span>
    | 采购人：中国中医科学院广安门医院
    | 代理机构：某招标有限公司 <i>公开招标公告</i>
    | 北京 |
  </li>
  <li>
    <a href="/cggg/dfgg/jzxcs/202609/t20260907_27280839.htm">河北某医院服务项目</a>
    <span>2026-09-07 16:00</span>
    | 采购人：河北某医院
    | 代理机构：某代理机构 <b>竞争性磋商公告</b>
    | 河北 |
  </li>
</ul>
</body></html>
"""

RESULT_FIXTURE = """
<html><body>
<ul class="vT-srch-result-list-bid">
  <li>
    <a href="/cggg/dfgg/zbgg/202609/t20260902_27255285.htm">天津市第一中心医院水西院区大型设备维保服务项目中标公告</a>
    <span>2026-09-02 | 采购人:天津市第一中心医院 | 天津市 | 中标公告</span>
  </li>
  <li>
    <a href="/cggg/dfgg/gzgg/202609/t20260903_27260000.htm">天津市某医院医疗设备采购项目更正公告</a>
    <span>2026-09-03 | 采购人:天津市某医院 | 天津市 | 更正公告</span>
  </li>
  <li>
    <a href="/cggg/dfgg/gkzb/202609/t20260902_27260001.htm">天津中医药大学第二附属医院流式细胞仪等医疗设备采购项目</a>
    <span>2026-09-02 | 采购人:天津中医药大学第二附属医院 | 天津市 | 公开招标公告</span>
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
        self.assertEqual(candidates[1].region, "天津市滨海新区")
        self.assertEqual(first.notice_type, "公开招标公告")
        self.assertTrue(first.detail_url.startswith("https://www.ccgp.gov.cn/"))

    def test_parse_labeled_region_metadata(self) -> None:
        candidates = parse_search_html(LABELED_REGION_FIXTURE, keyword="医疗")
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].region, "北京")
        self.assertEqual(candidates[0].buyer_name, "北京市某医院")
        self.assertEqual(candidates[1].region, "河北省")

    def test_parse_current_bare_pipe_delimited_region_field(self) -> None:
        candidates = parse_search_html(CURRENT_BARE_REGION_FIXTURE, keyword="医院")
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].title, "中国中医科学院广安门医院设备采购项目")
        self.assertEqual(candidates[0].published_at, "2026-09-07")
        self.assertEqual(candidates[0].buyer_name, "中国中医科学院广安门医院")
        self.assertEqual(candidates[0].region, "北京")
        self.assertEqual(candidates[0].notice_type, "公开招标公告")
        self.assertEqual(candidates[1].region, "河北")
        self.assertEqual(candidates[1].notice_type, "竞争性磋商公告")

    def test_region_is_not_inferred_from_buyer_or_free_text(self) -> None:
        fixture = """
        <html><body><ul class="vT-srch-result-list-bid"><li>
          <a href="/cggg/zygg/gkzb/202609/t20260907_27289999.htm">北京某医院设备项目</a>
          <p>项目地点位于北京市，采购人：北京某医院</p>
          | 公开招标公告 |
        </li></ul></body></html>
        """
        candidate = parse_search_html(fixture, keyword="医院")[0]
        self.assertIsNone(candidate.region)

    def test_primary_opportunity_budget_rejects_result_and_event_notices(self) -> None:
        candidates = parse_search_html(RESULT_FIXTURE, keyword="医院")
        self.assertEqual(len(candidates), 3)
        self.assertFalse(is_primary_opportunity_candidate(candidates[0]))
        self.assertFalse(is_primary_opportunity_candidate(candidates[1]))
        self.assertTrue(is_primary_opportunity_candidate(candidates[2]))

    def test_result_path_is_rejected_even_if_metadata_is_mislabelled(self) -> None:
        fixture = """
        <html><body><ul class="vT-srch-result-list-bid"><li>
          <a href="/cggg/dfgg/zbgg/202609/t20260902_27255285.htm">天津市第一中心医院大型设备维保服务项目</a>
          <span>2026-09-02 | 采购人:天津市第一中心医院 | 天津市 | 竞争性磋商公告</span>
        </li></ul></body></html>
        """
        candidate = parse_search_html(fixture, keyword="医院")[0]
        self.assertFalse(is_primary_opportunity_candidate(candidate))

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
