from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class CollectorAutomationEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.namespace = (WEB_ROOT / "collector_namespace.py").read_text(encoding="utf-8")
        self.health = (WEB_ROOT / "collector_automation_health.py").read_text(encoding="utf-8")
        self.trigger = (WEB_ROOT / "api" / "collector-run.py").read_text(encoding="utf-8")
        self.queue = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        self.status = (WEB_ROOT / "api" / "collector-status.py").read_text(encoding="utf-8")

    def test_new_tianjin_canonical_keys_share_runtime_v2_namespace(self) -> None:
        for marker in (
            'TJZYEFY_RECORDS_KEY = "medicalchannelai:collector-tjzyefy-records:v2"',
            'TJZYEFY_INTENT_RECORDS_KEY = "medicalchannelai:collector-tjzyefy-intent-records:v2"',
            'TJZXFC_RECORDS_KEY = "medicalchannelai:collector-tjzxfc-records:v2"',
            '"TJZYEFY_RECORDS_KEY": TJZYEFY_RECORDS_KEY',
            '"TJZYEFY_INTENT_RECORDS_KEY": TJZYEFY_INTENT_RECORDS_KEY',
            '"TJZXFC_RECORDS_KEY": TJZXFC_RECORDS_KEY',
        ):
            self.assertIn(marker, self.namespace)

    def test_persistent_health_evidence_has_no_secret_or_customer_fields(self) -> None:
        self.assertIn('AUTOMATION_HEALTH_KEY = "medicalchannelai:collector-automation-health:v2"', self.namespace)
        self.assertIn("def update_automation_health(", self.health)
        self.assertIn("def public_automation_health(", self.health)
        for forbidden in ("api_key", "secret", "token", "user_id", "organization_id", "hospital_relationship"):
            self.assertNotIn(forbidden, self.health.lower())

    def test_deep_trigger_chain_tick_and_source_scan_each_leave_evidence(self) -> None:
        self.assertIn("last_deep_trigger_at=now.isoformat()", self.trigger)
        self.assertIn('last_chain_schedule_status="SCHEDULED"', self.queue)
        self.assertIn("last_tick_delivered_at=now.isoformat()", self.queue)
        self.assertIn('"last_source_scan_at": delivered_at.isoformat()', self.queue)
        self.assertIn("last_deep_completed_at=datetime.now(timezone.utc).isoformat()", self.queue)

    def test_collector_status_includes_only_aggregate_automation_health(self) -> None:
        self.assertIn('"automation": public_automation_health(cache)', self.status)
        self.assertNotIn("detail_url", self.health)
        self.assertNotIn("project_name", self.health)


if __name__ == "__main__":
    unittest.main()
