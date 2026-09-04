import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class PrivateDataInvariantTests(unittest.TestCase):
    def test_reminder_is_independent_from_non_terminal_sales_stage(self):
        source = (WEB_ROOT / "api" / "private.js").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
