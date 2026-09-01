from __future__ import annotations

import unittest
from datetime import date

from medical_channel_pipeline.tjnothop_discovery import (
    TjnothopDiscoveryError,
    parse_tjnothop_index_html,
    select_candidates_since,
    stable_opportunity_id,
)


INDEX_HTML = """
<html><body>
<ul>
  <li><a href="/system/2026/08/17/030103001.shtml">天津市天津医院便携式彩色多普勒超声系统采购项目调研公告</a><span>2026-08-17</span></li>
  <li><a href="/system/2026/08/04/030102749.shtml">天津市天津医院2026年专职总会计师招聘公告</a><span>2026-08-04</span></li>
  <li><a href="/system/2026/07/14/030101456.shtml">天津市天津医院 光学相干断层扫描仪采购项目调研公告</a><span>2026-07-14</span></li>
  <li><a href="/system/2026/06/18/030100525.shtml">天津市天津医院 关于采购骨密度设备维保项目入围遴选调研公告</a><span>2026-06-18</span></li>
  <li><a href="https://evil.example/system/2026/08/18/999.shtml">天津市天津医院某设备采购项目调研公告</a><span>2026-08-18</span></li>
</ul>
</body></html>
"""


class TjnothopDiscoveryTests(unittest.TestCase):
    def test_index_only_returns_standard_equipment_procurement_research(self) -> None:
        candidates = parse_tjnothop_index_html(INDEX_HTML)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].published_at, "2026-08-17")
        self.assertIn("便携式彩色多普勒超声系统", candidates[0].title)
        self.assertEqual(candidates[1].published_at, "2026-07-14")
        self.assertIn("光学相干断层扫描仪", candidates[1].title)

    def test_non_procurement_news_recruitment_and_maintenance_are_excluded(self) -> None:
        titles = [candidate.title for candidate in parse_tjnothop_index_html(INDEX_HTML)]
        self.assertFalse(any("招聘" in title for title in titles))
        self.assertFalse(any("维保" in title for title in titles))

    def test_candidate_window_uses_official_index_date(self) -> None:
        candidates = parse_tjnothop_index_html(INDEX_HTML)
        selected = select_candidates_since(
            candidates,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            max_candidates=10,
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].published_at, "2026-08-17")

    def test_stable_id_uses_official_detail_path(self) -> None:
        self.assertEqual(
            stable_opportunity_id("https://www.tjnothop.cn/system/2026/07/03/030101007.shtml"),
            "tjnothop_20260703_030101007",
        )

    def test_non_official_index_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(TjnothopDiscoveryError, "TJNOTHOP_INDEX_HOST_REJECTED"):
            parse_tjnothop_index_html(INDEX_HTML, index_url="https://example.com/index.shtml")


if __name__ == "__main__":
    unittest.main()
