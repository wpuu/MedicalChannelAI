from __future__ import annotations

import unittest

from medical_channel_pipeline.ccgp_detail import _extract_project_number


class CcgpProjectNumberTests(unittest.TestCase):
    def test_notice_title_suffix_is_not_part_of_project_number(self) -> None:
        cases = {
            "项目编号：TGPC-2026-A-0286)公开招标公告 项目名称：测试": "TGPC-2026-A-0286",
            "项目编号：XCSD-2026-A-716）公开招标公告 项目名称：测试": "XCSD-2026-A-716",
            "项目编号：ABC-2026-001)竞争性磋商公告 项目名称：测试": "ABC-2026-001",
            "项目编号：ABC-2026-002）竞争性磋商公告 项目名称：测试": "ABC-2026-002",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(_extract_project_number(text), expected)

    def test_legitimate_parentheses_inside_project_number_are_preserved(self) -> None:
        self.assertEqual(
            _extract_project_number("项目编号：ABC(2026)-001 项目名称：测试"),
            "ABC(2026)-001",
        )


if __name__ == "__main__":
    unittest.main()
