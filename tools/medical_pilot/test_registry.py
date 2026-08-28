from __future__ import annotations

import unittest

from tools.medical_pilot.registry import adapter_for_source, load_registry, resolve_source


VALID_PROVENANCE_ROLES = {"PRIMARY_SOURCE", "OFFICIAL_MIRROR", "DISCOVERY_ONLY"}


class SourceRegistryTests(unittest.TestCase):
    def test_ccgp_detail_url_resolves_to_exact_registered_source(self) -> None:
        source = resolve_source(
            "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260827_27219613.htm"
        )
        self.assertEqual(source.source_id, "ccgp_local_notices")
        self.assertEqual(source.provenance_role, "OFFICIAL_MIRROR")
        self.assertTrue(source.enabled)
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

    def test_ccgp_intent_url_resolves_to_exact_registered_source(self) -> None:
        source = resolve_source(
            "https://cgyx.ccgp.gov.cn/cgyx/pub/proJ/details?projId=d9c9cde4-27c9-4d1f-a0f6-77994bf1ce25"
        )
        self.assertEqual(source.source_id, "ccgp_procurement_intent")
        self.assertEqual(source.provenance_role, "OFFICIAL_MIRROR")
        self.assertTrue(source.enabled)
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

    def test_tjmugh_detail_url_resolves_to_exact_registered_source(self) -> None:
        source = resolve_source(
            "https://www.tjmugh.com.cn/system/2026/05/29/030295720.shtml"
        )
        self.assertEqual(source.source_id, "tjmugh_procurement")
        self.assertEqual(source.provenance_role, "PRIMARY_SOURCE")
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

    def test_tianjin_native_detail_url_resolves_to_primary_source(self) -> None:
        source = resolve_source(
            "https://tjgp.cz.tj.gov.cn/portal/documentView.do?method=view&id=611515456&ver=2"
        )
        self.assertEqual(source.source_id, "tj_government_procurement")
        self.assertEqual(source.provenance_role, "PRIMARY_SOURCE")
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

    def test_domain_substring_attack_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_source(
                "https://www.ccgp.gov.cn.attacker.example/cggg/dfgg/gkzb/202608/t20260827_27219613.htm"
            )

    def test_unregistered_ccgp_path_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_source("https://www.ccgp.gov.cn/arbitrary/path")

    def test_registry_has_unique_source_ids_and_explicit_valid_provenance_roles(self) -> None:
        sources = load_registry()
        ids = [source.source_id for source in sources]
        self.assertEqual(len(ids), len(set(ids)))
        for source in sources:
            self.assertIn("provenance_role", source.raw, source.source_id)
            self.assertIn(source.provenance_role, VALID_PROVENANCE_ROLES, source.source_id)
            self.assertEqual(source.raw["provenance_role"], source.provenance_role, source.source_id)


if __name__ == "__main__":
    unittest.main()
