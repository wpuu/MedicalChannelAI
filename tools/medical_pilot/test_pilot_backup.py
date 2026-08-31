from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.medical_pilot.pilot_backup import create_sqlite_backup


NOW = datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc)


class PilotBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "pilot.sqlite"
        self.out = self.root / "backups"
        with sqlite3.connect(str(self.db)) as conn:
            conn.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO sample(value) VALUES ('alpha')")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_backup_is_consistent_and_hash_is_reported(self) -> None:
        result = create_sqlite_backup(db_path=self.db, out_dir=self.out, keep=14, now=NOW)
        target = self.out / str(result["backup_file"])
        self.assertTrue(target.is_file())
        self.assertEqual(len(str(result["sha256"])), 64)
        with sqlite3.connect(str(target)) as conn:
            row = conn.execute("SELECT value FROM sample").fetchone()
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
        self.assertEqual(row, ("alpha",))
        self.assertEqual(integrity, ("ok",))

    def test_online_backup_includes_committed_wal_pages_while_writer_connection_stays_open(self) -> None:
        writer = sqlite3.connect(str(self.db))
        try:
            self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower(), "wal")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("INSERT INTO sample(value) VALUES ('committed-in-live-wal')")
            writer.commit()
            wal_path = Path(str(self.db) + "-wal")
            self.assertTrue(wal_path.exists())
            self.assertGreater(wal_path.stat().st_size, 0)

            result = create_sqlite_backup(
                db_path=self.db,
                out_dir=self.out,
                keep=14,
                now=NOW,
            )
            target = self.out / str(result["backup_file"])
            with sqlite3.connect(str(target)) as conn:
                values = [row[0] for row in conn.execute("SELECT value FROM sample ORDER BY id")]
            self.assertEqual(values, ["alpha", "committed-in-live-wal"])
            self.assertTrue(wal_path.exists())
        finally:
            writer.close()

    def test_retention_keeps_requested_total_count(self) -> None:
        for day in range(1, 5):
            create_sqlite_backup(
                db_path=self.db,
                out_dir=self.out,
                keep=2,
                now=datetime(2026, 8, day, 10, 0, tzinfo=timezone.utc),
            )
        backups = sorted(self.out.glob("pilot-*.sqlite"))
        self.assertEqual(len(backups), 2)
        self.assertTrue(backups[-1].name.startswith("pilot-20260804"))

    def test_invalid_keep_and_naive_time_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            create_sqlite_backup(db_path=self.db, out_dir=self.out, keep=0, now=NOW)
        with self.assertRaises(ValueError):
            create_sqlite_backup(
                db_path=self.db,
                out_dir=self.out,
                keep=2,
                now=datetime(2026, 8, 30, 10, 0),
            )


if __name__ == "__main__":
    unittest.main()
