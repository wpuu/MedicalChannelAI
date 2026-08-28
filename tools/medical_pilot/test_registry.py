from __future__ import annotations

import unittest

from tools.medical_pilot.registry import adapter_for_source, load_registry, resolve_source


class SourceRegistryTests(unittest.TestCase):
    def test_ccgp_detail_url_resolves_to_exact_registered_source(self) -> None:
        source = resolve_source(
            "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260827_27219613.htm"
        )
        self.assertEqual(source.source_id, "ccgp_local_notices")
        self.assertTrue(source.enabled)
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

    def test_ccgp_intent_url_resolves_to_exact_registered_source(self) -> None:
        source = resolve_source(
            "https://cgyx.ccgp.gov.cn/cgyx/pub/proJ/details?projId=d9c9cde4-27c9-4d1f-a0f6-77994bf1ce25"
        )
        self.assertEqual(source.source_id, "ccgp_procurement_intent")
        self.assertTrue(source.enabled)
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

    def test_tjmugh_detail_url_resolves_to_exact_registered_source(self) -> None:
        source = resolve_source(
            "https://www.tjmugh.com.cn/system/2026/05/29/030295720.shtml"
        )
        self.assertEqual(source.source_id, "tjmugh_procurement")
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

    def test_domain_substring_attack_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_source(
                "https://www.ccgp.gov.cn.attacker.example/cggg/dfgg/gkzb/202608/t20260827_27219613.htm"
            )

    def test_unregistered_ccgp_path_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_source("https://www.ccgp.gov.cn/arbitrary/path")

    def test_registry_has_unique_source_ids(self) -> None:
        sources = load_registry()
        ids = [source.source_id for source in sources]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
