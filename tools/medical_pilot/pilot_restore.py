from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from .pilot_backup import (
    PilotBackupError,
    _sha256_file,
    copy_sqlite_consistent,
    inspect_sqlite_database,
)


class PilotRestoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def verify_backup(*, backup_path: Path) -> dict[str, object]:
    backup = Path(backup_path)
    check = inspect_sqlite_database(backup)
    if backup.is_symlink() or not backup.is_file():
        raise PilotRestoreError("BACKUP_NOT_REGULAR_FILE")
    return {
        "schema_version": "0.1",
        "status": "PASS",
        "operation": "VERIFY_BACKUP",
        "backup_file": backup.name,
        "size_bytes": backup.stat().st_size,
        "sha256": _sha256_file(backup),
        "integrity_check": check["integrity_check"],
        "foreign_key_check": check["foreign_key_check"],
        "table_count": check["table_count"],
        "contains_customer_data": True,
    }


def prepare_restore_candidate(*, backup_path: Path, output_path: Path) -> dict[str, object]:
    backup = Path(backup_path)
    backup_check = inspect_sqlite_database(backup)
    output = Path(output_path)
    if output.exists() or output.is_symlink():
        raise PilotRestoreError("RESTORE_CANDIDATE_ALREADY_EXISTS")
    restored_check = copy_sqlite_consistent(source_path=backup, destination_path=output)
    if restored_check["table_count"] != backup_check["table_count"]:
        output.unlink(missing_ok=True)
        raise PilotRestoreError("RESTORE_TABLE_COUNT_MISMATCH")
    return {
        "schema_version": "0.1",
        "status": "PASS",
        "operation": "PREPARE_RESTORE_CANDIDATE",
        "candidate_file": output.name,
        "size_bytes": output.stat().st_size,
        "sha256": _sha256_file(output),
        "integrity_check": restored_check["integrity_check"],
        "foreign_key_check": restored_check["foreign_key_check"],
        "table_count": restored_check["table_count"],
        "file_mode": "0600",
        "contains_customer_data": True,
        "production_database_replaced": False,
    }


def restore_smoke(*, backup_path: Path) -> dict[str, object]:
    backup = Path(backup_path)
    verify = verify_backup(backup_path=backup)
    with tempfile.TemporaryDirectory(prefix="mcai-restore-smoke-") as temp_dir:
        candidate = Path(temp_dir) / "restored.sqlite"
        prepared = prepare_restore_candidate(backup_path=backup, output_path=candidate)
        if prepared["table_count"] != verify["table_count"]:
            raise PilotRestoreError("RESTORE_SMOKE_TABLE_COUNT_MISMATCH")
    return {
        "schema_version": "0.1",
        "status": "PASS",
        "operation": "RESTORE_SMOKE",
        "integrity_check": "PASS",
        "foreign_key_check": "PASS",
        "table_count": verify["table_count"],
        "temporary_candidate_removed": True,
        "production_database_replaced": False,
    }


def _safe_failure(exc: Exception, operation: str) -> dict[str, Any]:
    code = getattr(exc, "code", None) or type(exc).__name__
    return {
        "schema_version": "0.1",
        "status": "FAIL",
        "operation": operation,
        "error_class": str(code)[:120],
        "production_database_replaced": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a MedicalChannelAI SQLite backup or prepare a separate restore candidate. "
            "This tool never replaces the production database."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--backup", required=True, type=Path)

    smoke_parser = subparsers.add_parser("smoke")
    smoke_parser.add_argument("--backup", required=True, type=Path)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--backup", required=True, type=Path)
    prepare_parser.add_argument("--output", required=True, type=Path)

    args = parser.parse_args()
    operation = str(args.command).upper()
    try:
        if args.command == "verify":
            result = verify_backup(backup_path=args.backup)
        elif args.command == "smoke":
            result = restore_smoke(backup_path=args.backup)
        elif args.command == "prepare":
            result = prepare_restore_candidate(backup_path=args.backup, output_path=args.output)
        else:
            raise PilotRestoreError("COMMAND_NOT_SUPPORTED")
    except (PilotBackupError, PilotRestoreError, OSError) as exc:
        result = _safe_failure(exc, operation)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
