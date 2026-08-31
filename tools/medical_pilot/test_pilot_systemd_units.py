from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "deploy"


class PilotSystemdUnitTests(unittest.TestCase):
    def test_api_unit_requires_env_file_and_runs_preflight(self) -> None:
        text = (DEPLOY / "medical-pilot.service").read_text(encoding="utf-8")
        self.assertIn("EnvironmentFile=/etc/medicalchannelai/pilot.env", text)
        self.assertNotIn("EnvironmentFile=-/etc/medicalchannelai/pilot.env", text)
        self.assertIn(
            "ExecStartPre=/usr/bin/python3 -m tools.medical_pilot.pilot_host_preflight --role api --db /srv/medical/data/pilot.sqlite",
            text,
        )

    def test_worker_unit_requires_env_file_and_runs_worker_preflight(self) -> None:
        text = (DEPLOY / "medical-agnes-worker.service").read_text(encoding="utf-8")
        self.assertIn("EnvironmentFile=/etc/medicalchannelai/pilot.env", text)
        self.assertNotIn("EnvironmentFile=-/etc/medicalchannelai/pilot.env", text)
        self.assertIn(
            "ExecStartPre=/usr/bin/python3 -m tools.medical_pilot.pilot_host_preflight --role worker --db /srv/medical/data/pilot.sqlite",
            text,
        )

    def test_acceptance_unit_is_manual_oneshot_using_frozen_manifest(self) -> None:
        text = (DEPLOY / "medical-pilot-acceptance.service").read_text(encoding="utf-8")
        self.assertIn("Type=oneshot", text)
        self.assertIn("EnvironmentFile=/etc/medicalchannelai/pilot.env", text)
        self.assertIn(
            "ExecStart=/usr/bin/python3 -m tools.medical_pilot.pilot_host_acceptance --manifest deploy/pilot-host-acceptance-v0.1.json --db /srv/medical/data/pilot.sqlite",
            text,
        )
        self.assertNotIn("[Install]", text)

    def test_backup_unit_runs_backup_and_restore_smoke_with_private_boundary(self) -> None:
        text = (DEPLOY / "medical-pilot-backup.service").read_text(encoding="utf-8")
        self.assertIn("Type=oneshot", text)
        self.assertIn(
            "ExecStart=/usr/bin/python3 -m tools.medical_pilot.pilot_backup_job --db /srv/medical/data/pilot.sqlite --out-dir /srv/medical/backups --keep 14",
            text,
        )
        self.assertIn("UMask=0077", text)
        self.assertIn("ReadWritePaths=/srv/medical/backups", text)
        self.assertNotIn("pilot_restore prepare", text)

    def test_backup_timer_is_daily_persistent_and_shanghai_scoped(self) -> None:
        text = (DEPLOY / "medical-pilot-backup.timer").read_text(encoding="utf-8")
        self.assertIn("OnCalendar=*-*-* 03:40:00 Asia/Shanghai", text)
        self.assertIn("Persistent=true", text)
        self.assertIn("RandomizedDelaySec=300", text)
        self.assertIn("Unit=medical-pilot-backup.service", text)
        self.assertIn("WantedBy=timers.target", text)


if __name__ == "__main__":
    unittest.main()
