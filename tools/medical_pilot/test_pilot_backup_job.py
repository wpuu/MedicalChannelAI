from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.pilot_backup_job import PilotBackupJobError, run_backup_job


NOW = datetime(2026, 8, 31, 1, 5, tzinfo=timezone.utc)


class PilotBackupJobTests(unittest.TestCase):
    def test_success_requires_backup_and_restore_smoke(self) -> None:
        calls = []

        def backup_creator(**kwargs):
            calls.append(("backup", kwargs))
            out_dir = Path(kwargs["out_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "pilot-20260831T010500Z.sqlite").write_bytes(b"fake")
            return {
                "status": "PASS",
                "backup_file": "pilot-20260831T010500Z.sqlite",
                "size_bytes": 4,
                "sha256": "a" * 64,
                "retention_keep": 14,
                "removed": [],
                "backup_integrity": "PASS",
                "foreign_key_check": "PASS",
            }

        def restore_checker(**kwargs):
            calls.append(("restore", kwargs))
            return {"status": "PASS"}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = run_backup_job(
                db_path=root / "pilot.sqlite",
                out_dir=root / "backups",
                keep=14,
                now=NOW,
                backup_creator=backup_creator,
                restore_checker=restore_checker,
            )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["restore_smoke"], "PASS")
        self.assertFalse(result["production_database_replaced"])
        self.assertEqual([name for name, _ in calls], ["backup", "restore"])

    def test_restore_failure_makes_whole_job_fail(self) -> None:
        def backup_creator(**kwargs):
            out_dir = Path(kwargs["out_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "pilot-20260831T010500Z.sqlite").write_bytes(b"fake")
            return {"status": "PASS", "backup_file": "pilot-20260831T010500Z.sqlite"}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(PilotBackupJobError) as context:
                run_backup_job(
                    db_path=root / "pilot.sqlite",
                    out_dir=root / "backups",
                    backup_creator=backup_creator,
                    restore_checker=lambda **_: {"status": "FAIL"},
                )
        self.assertEqual(context.exception.code, "RESTORE_SMOKE_NOT_PASS")

    def test_invalid_backup_result_never_runs_restore(self) -> None:
        restore_calls = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(PilotBackupJobError) as context:
                run_backup_job(
                    db_path=root / "pilot.sqlite",
                    out_dir=root / "backups",
                    backup_creator=lambda **_: {"status": "FAIL"},
                    restore_checker=lambda **kwargs: restore_calls.append(kwargs) or {"status": "PASS"},
                )
        self.assertEqual(context.exception.code, "BACKUP_CREATE_NOT_PASS")
        self.assertEqual(restore_calls, [])


if __name__ == "__main__":
    unittest.main()
