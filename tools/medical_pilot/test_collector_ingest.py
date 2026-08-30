from __future__ import annotations

import unittest

from .collector_ingest import _allowed_fetch_hosts
from .registry import resolve_source


class CollectorIngestTests(unittest.TestCase):
    def test_tianjin_government_approved_alias_host_is_fetchable(self) -> None:
        url = (
            "https://www.ccgp-tianjin.gov.cn/portal/documentView.do"
            "?method=view&id=123456&ver=2"
        )
        source = resolve_source(url)

        hosts = _allowed_fetch_hosts(source, url)

        self.assertIn("www.ccgp-tianjin.gov.cn", hosts)
        self.assertIn("ccgp-tianjin.gov.cn", hosts)
        self.assertIn("tjgp.cz.tj.gov.cn", hosts)

    def test_non_registered_host_never_reaches_fetch_host_builder(self) -> None:
        with self.assertRaises(ValueError):
            resolve_source("https://attacker.example/portal/documentView.do?method=view&id=1&ver=2")


if __name__ == "__main__":
    unittest.main()
