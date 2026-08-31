from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy/medical-agnes-benchmark.service"
RUNBOOK = ROOT / "deploy/AGNES_BENCHMARK.md"


class AgnesBenchmarkServiceTests(unittest.TestCase):
    def test_service_is_manual_oneshot_and_uses_root_managed_environment(self) -> None:
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn("Type=oneshot", text)
        self.assertIn("User=medicalai", text)
        self.assertIn("EnvironmentFile=/etc/medicalchannelai/pilot.env", text)
        self.assertNotIn("[Install]", text)
        self.assertNotIn("MCAI_AGNES_API_KEY=", text)

    def test_service_refuses_to_run_while_api_or_worker_is_active(self) -> None:
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn("systemctl is-active --quiet medical-pilot.service", text)
        self.assertIn("systemctl is-active --quiet medical-agnes-worker.service", text)
        self.assertIn("--maintenance-window", text)
        self.assertIn("--lease-db /srv/medical/data/pilot.sqlite", text)

    def test_service_writes_one_private_immutable_result_and_runbook_forbids_auto_admission(self) -> None:
        service = SERVICE.read_text(encoding="utf-8")
        runbook = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("--output /srv/medical/data/agnes-benchmark-result-v0.1.json", service)
        self.assertIn("ReadWritePaths=/srv/medical/data", service)
        self.assertIn("automatic_classifier_admission_allowed=false", runbook)
        self.assertIn("automatic_classifier_admission_performed=false", runbook)
        self.assertIn("BENCHMARK_PENDING", runbook)
        self.assertIn("0600", runbook)


if __name__ == "__main__":
    unittest.main()
