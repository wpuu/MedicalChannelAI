from __future__ import annotations

import unittest

from tools.medical_pilot.registry import resolve_source


class TjgpcDiscoveryNegativeTests(unittest.TestCase):
    def test_w008_online_response_help_route_is_not_registered_as_procurement_discovery(self) -> None:
        url = (
            "https://tjgpc.zwfwb.tj.gov.cn/webInfo/"
            "getWebInfoListForwebInfoClass.do?fkWebInfoclassId=W008"
        )
        with self.assertRaises(ValueError):
            resolve_source(url)

    def test_home_entry_is_not_misclassified_as_notice_detail(self) -> None:
        with self.assertRaises(ValueError):
            resolve_source("https://tjgpc.zwfwb.tj.gov.cn/web_index1.do")


if __name__ == "__main__":
    unittest.main()
