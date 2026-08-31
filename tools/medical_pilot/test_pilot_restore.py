from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.medical_pilot.pilot_backup import PilotBackupError, create_sqlite_backup
from tools.medical_pilot.pilot_restore import (
    PilotRestoreError,
    prepare_restore_candidate,
    restore_smoke,
    verify_backup,
)


class PilotRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "pilot.sqlite"
        self.backups = self.root / "backups"
        with sqlite3.connect(str(self.db)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA wal_autocheckpoint=0")
            conn.execute("CREATE TABLE secrets(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO secrets(value) VALUES (?)", ("customer-secret-value",))
            conn.commit()
        self.backup_result = create_sqlite_backup(db_path=self.db, out_dir=self.backups, keep=14)
        self.backup = self.backups / str(self.backup_result["backup_file"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_backup_captures_committed_wal_data_and_result_does_not_echo_it(self) -> None:
        with sqlite3.connect(str(self.backup)) as conn:
            value = conn.execute("SELECT value FROM secrets").fetchone()
        self.assertEqual(value, ("customer-secret-value",))
        self.assertNotIn("customer-secret-value", json.dumps(self.backup_result, ensure_ascii=False))
        self.assertEqual(self.backup_result["backup_integrity"], "PASS")
        self.assertEqual(self.backup_result["foreign_key_check"], "PASS")

    def test_backup_and_restore_candidate_are_private_mode(self) -> None:
        self.assertEqual(os.stat(self.backup).st_mode & 0o777, 0o600)
        candidate = self.root / "restore-candidate.sqlite"
        result = prepare_restore_candidate(backup_path=self.backup, output_path=candidate)
        self.assertEqual(os.stat(candidate).st_mode & 0o777, 0o600)
        self.assertFalse(result["production_database_replaced"])
        with sqlite3.connect(str(candidate)) as conn:
            value = conn.execute("SELECT value FROM secrets").fetchone()
        self.assertEqual(value, ("customer-secret-value",))
        self.assertNotIn("customer-secret-value", json.dumps(result, ensure_ascii=False))

    def test_restore_smoke_uses_temporary_candidate_only(self) -> None:
        before = self.db.read_bytes()
        result = restore_smoke(backup_path=self.backup)
        after = self.db.read_bytes()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["temporary_candidate_removed"])
        self.assertFalse(result["production_database_replaced"])
        self.assertEqual(before, after)

    def test_prepare_restore_refuses_existing_target(self) -> None:
        candidate = self.root / "existing.sqlite"
        candidate.write_bytes(b"do-not-overwrite")
        with self.assertRaises(PilotRestoreError) as context:
            prepare_restore_candidate(backup_path=self.backup, output_path=candidate)
        self.assertEqual(context.exception.code, "RESTORE_CANDIDATE_ALREADY_EXISTS")
        self.assertEqual(candidate.read_bytes(), b"do-not-overwrite")

    def test_corrupt_backup_fails_closed(self) -> None:
        corrupt = self.root / "corrupt.sqlite"
        corrupt.write_bytes(b"not-a-sqlite-database")
        with self.assertRaises(PilotBackupError):
            verify_backup(backup_path=corrupt)

    def test_verify_reports_hash_and_no_customer_values(self) -> None:
        result = verify_backup(backup_path=self.backup)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(str(result["sha256"])), 64)
        self.assertTrue(result["contains_customer_data"])
        self.assertNotIn("customer-secret-value", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
