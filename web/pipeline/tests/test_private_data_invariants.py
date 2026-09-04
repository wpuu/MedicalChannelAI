import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class PrivateDataInvariantTests(unittest.TestCase):
    def test_reminder_is_independent_from_non_terminal_sales_stage(self):
        source = (WEB_ROOT / "api" / "_privateCore.js").read_text(encoding="utf-8")
        self.assertIn(
            "const REMINDER_TERMINAL_STATUSES = new Set(['WON', 'LOST', 'NOT_FIT', 'ARCHIVED'])",
            source,
        )
        self.assertIn(
            "REMINDER_TERMINAL_STATUSES.has(status) && reminderSupplied && remindAt",
            source,
        )
        self.assertIn(
            "else if (REMINDER_TERMINAL_STATUSES.has(mutation.status)) nextReminder = null",
            source,
        )
        self.assertIn(
            "AND f.status NOT IN ('WON', 'LOST', 'NOT_FIT', 'ARCHIVED')",
            source,
        )
        self.assertNotIn("status !== 'MONITOR' && reminderSupplied && remindAt", source)
        self.assertNotIn("AND f.status = 'MONITOR'", source)

    def test_profile_write_deduplicates_logical_resource_scopes(self):
        source = (WEB_ROOT / "api" / "profile.js").read_text(encoding="utf-8")
        self.assertIn("productCapabilityMap.set(item.keyword.toLowerCase(), item)", source)
        self.assertIn("relationshipMap.set(targetKey(item), item)", source)
        self.assertIn("product_capabilities: [...productCapabilityMap.values()]", source)
        self.assertIn("hospital_relationships: [...relationshipMap.values()]", source)

    def test_profile_destructive_writes_are_scoped_to_current_organization(self):
        source = (WEB_ROOT / "api" / "profile.js").read_text(encoding="utf-8")
        self.assertIn("DELETE FROM private_product_capabilities WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}", source)
        self.assertIn("DELETE FROM private_hospital_relationships WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}", source)
        self.assertIn("DELETE FROM private_target_hospitals WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}", source)

    def test_profile_resource_rows_are_written_in_bounded_bulk_statements(self):
        source = (WEB_ROOT / "api" / "profile.js").read_text(encoding="utf-8")
        self.assertIn("const capabilityRows = profile.product_capabilities.map", source)
        self.assertIn("tx(capabilityRows, 'id', 'organization_id', 'user_id', 'keyword', 'capability_type')", source)
        self.assertIn("const relationshipRows = profile.hospital_relationships.map", source)
        self.assertIn("tx(relationshipRows, 'id', 'organization_id', 'user_id', 'hospital', 'department', 'relationship_strength')", source)
        self.assertIn("const targetRows = profile.target_hospitals.map", source)
        self.assertIn("tx(targetRows, 'id', 'organization_id', 'user_id', 'hospital', 'department')", source)
        write_start = source.index("await sql.begin(async (tx) => {", source.index("const profile = validateProfile"))
        write_block = source[write_start:]
        self.assertNotIn("for (const item of profile.product_capabilities)", write_block)
        self.assertNotIn("for (const item of profile.hospital_relationships)", write_block)
        self.assertNotIn("for (const item of profile.target_hospitals)", write_block)


if __name__ == "__main__":
    unittest.main()
