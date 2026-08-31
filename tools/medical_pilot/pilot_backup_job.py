from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable

from .pilot_backup import create_sqlite_backup
from .pilot_restore import restore_smoke


class PilotBackupJobError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def run_backup_job(
    *,
    db_path: Path,
    out_dir: Path,
    keep: int = 14,
    now: datetime | None = None,
    backup_creator: Callable[..., dict[str, object]] = create_sqlite_backup,
    restore_checker: Callable[..., dict[str, object]] = restore_smoke,
) -> dict[str, object]:
    backup = backup_creator(db_path=Path(db_path), out_dir=Path(out_dir), keep=keep, now=now)
    backup_file = backup.get("backup_file")
    if backup.get("status") != "PASS" or not isinstance(backup_file, str) or not backup_file:
        raise PilotBackupJobError("BACKUP_CREATE_NOT_PASS")

    backup_path = Path(out_dir) / backup_file
    restore = restore_checker(backup_path=backup_path)
    if restore.get("status") != "PASS":
        raise PilotBackupJobError("RESTORE_SMOKE_NOT_PASS")

    return {
        "schema_version": "0.1",
        "status": "PASS",
        "operation": "BACKUP_AND_RESTORE_SMOKE",
        "backup_file": backup_file,
        "size_bytes": backup.get("size_bytes"),
        "sha256": backup.get("sha256"),
        "retention_keep": backup.get("retention_keep"),
        "old_backups_removed": len(backup.get("removed") or []),
        "backup_integrity": backup.get("backup_integrity"),
        "foreign_key_check": backup.get("foreign_key_check"),
        "restore_smoke": "PASS",
        "production_database_replaced": False,
        "contains_customer_data": True,
    }


def _safe_failure(exc: Exception) -> dict[str, Any]:
    code = getattr(exc, "code", None) or type(exc).__name__
    return {
        "schema_version": "0.1",
        "status": "FAIL",
        "operation": "BACKUP_AND_RESTORE_SMOKE",
        "error_class": str(code)[:120],
        "production_database_replaced": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a consistent Pilot backup and immediately prove it can restore into an isolated temporary database."
    )
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()
    try:
        result = run_backup_job(db_path=args.db, out_dir=args.out_dir, keep=args.keep)
    except Exception as exc:
        result = _safe_failure(exc)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
