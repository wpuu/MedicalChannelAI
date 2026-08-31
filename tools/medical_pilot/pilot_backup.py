from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any


BACKUP_NAME_RE = re.compile(r"^pilot-(\d{8}T\d{6}Z)\.sqlite$")


class PilotBackupError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _require_regular_database(path: Path, *, missing_code: str, invalid_code: str) -> Path:
    candidate = Path(path)
    if not candidate.exists():
        raise PilotBackupError(missing_code)
    if candidate.is_symlink() or not candidate.is_file():
        raise PilotBackupError(invalid_code)
    return candidate


def inspect_sqlite_database(path: Path) -> dict[str, int | str]:
    database = _require_regular_database(
        Path(path),
        missing_code="DATABASE_MISSING",
        invalid_code="DATABASE_NOT_REGULAR_FILE",
    )
    try:
        with _readonly_connection(database) as conn:
            integrity_rows = conn.execute("PRAGMA integrity_check").fetchall()
            foreign_key_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
            table_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
            )
            user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            application_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
    except sqlite3.DatabaseError as exc:
        raise PilotBackupError("DATABASE_INVALID") from exc

    if integrity_rows != [("ok",)]:
        raise PilotBackupError("DATABASE_INTEGRITY_CHECK_FAILED")
    if foreign_key_violations:
        raise PilotBackupError("DATABASE_FOREIGN_KEY_CHECK_FAILED")
    return {
        "integrity_check": "PASS",
        "foreign_key_check": "PASS",
        "table_count": table_count,
        "user_version": user_version,
        "application_id": application_id,
    }


def _fsync_file(path: Path) -> None:
    with Path(path).open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(str(path), flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def copy_sqlite_consistent(*, source_path: Path, destination_path: Path) -> dict[str, int | str]:
    """Create one standalone consistent SQLite copy using SQLite's Backup API.

    The source is opened read-only, so committed WAL pages visible to SQLite are
    included without copying `-wal`/`-shm` sidecars. The destination must not exist.
    """

    source = _require_regular_database(
        Path(source_path),
        missing_code="SOURCE_DATABASE_MISSING",
        invalid_code="SOURCE_DATABASE_NOT_REGULAR_FILE",
    )
    destination = Path(destination_path)
    if destination.exists() or destination.is_symlink():
        raise PilotBackupError("DESTINATION_ALREADY_EXISTS")
    parent = destination.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        raise PilotBackupError("DESTINATION_PARENT_INVALID")
    if not os.access(parent, os.W_OK | os.X_OK):
        raise PilotBackupError("DESTINATION_PARENT_NOT_WRITABLE")
    if destination.resolve() == source.resolve():
        raise PilotBackupError("SOURCE_AND_DESTINATION_MUST_DIFFER")

    fd, temp_name = tempfile.mkstemp(prefix=".mcai-sqlite-copy-", suffix=".tmp", dir=parent)
    os.close(fd)
    temp_path = Path(temp_name)
    os.chmod(temp_path, 0o600)
    try:
        source_check = inspect_sqlite_database(source)
        with _readonly_connection(source) as source_conn:
            destination_conn = sqlite3.connect(str(temp_path), timeout=30.0)
            try:
                destination_conn.execute("PRAGMA busy_timeout=30000")
                destination_conn.execute("PRAGMA journal_mode=DELETE")
                source_conn.backup(destination_conn, pages=128, sleep=0.05)
            finally:
                destination_conn.close()
        destination_check = inspect_sqlite_database(temp_path)
        if destination_check["table_count"] != source_check["table_count"]:
            raise PilotBackupError("SQLITE_COPY_TABLE_COUNT_MISMATCH")
        _fsync_file(temp_path)
        os.replace(temp_path, destination)
        os.chmod(destination, 0o600)
        _fsync_directory(parent)
        return destination_check
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def create_sqlite_backup(
    *,
    db_path: Path,
    out_dir: Path,
    keep: int = 14,
    now: datetime | None = None,
) -> dict[str, object]:
    db_path = _require_regular_database(
        Path(db_path),
        missing_code="SOURCE_DATABASE_MISSING",
        invalid_code="SOURCE_DATABASE_NOT_REGULAR_FILE",
    )
    out_dir = Path(out_dir)
    if not isinstance(keep, int) or isinstance(keep, bool) or keep < 2 or keep > 365:
        raise PilotBackupError("RETENTION_KEEP_INVALID")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise PilotBackupError("BACKUP_TIME_MUST_BE_TIMEZONE_AWARE")
    current = current.astimezone(timezone.utc)

    if out_dir.exists():
        if out_dir.is_symlink() or not out_dir.is_dir():
            raise PilotBackupError("BACKUP_DIRECTORY_INVALID")
    else:
        out_dir.mkdir(parents=True, mode=0o700)
    if not os.access(out_dir, os.W_OK | os.X_OK):
        raise PilotBackupError("BACKUP_DIRECTORY_NOT_WRITABLE")

    timestamp = current.strftime("%Y%m%dT%H%M%SZ")
    final_path = out_dir / f"pilot-{timestamp}.sqlite"
    if final_path.exists() or final_path.is_symlink():
        raise PilotBackupError("BACKUP_TARGET_ALREADY_EXISTS")

    source_check = inspect_sqlite_database(db_path)
    backup_check = copy_sqlite_consistent(source_path=db_path, destination_path=final_path)

    backups = sorted(
        (
            item
            for item in out_dir.iterdir()
            if item.is_file() and not item.is_symlink() and BACKUP_NAME_RE.fullmatch(item.name)
        ),
        key=lambda item: item.name,
        reverse=True,
    )
    removed: list[str] = []
    for stale in backups[keep:]:
        stale.unlink()
        removed.append(stale.name)
    if removed:
        _fsync_directory(out_dir)

    return {
        "schema_version": "0.1",
        "status": "PASS",
        "operation": "CREATE_BACKUP",
        "backup_file": final_path.name,
        "created_at": current.isoformat(),
        "size_bytes": final_path.stat().st_size,
        "sha256": _sha256_file(final_path),
        "retention_keep": keep,
        "removed": removed,
        "source_integrity": source_check["integrity_check"],
        "backup_integrity": backup_check["integrity_check"],
        "foreign_key_check": backup_check["foreign_key_check"],
        "table_count": backup_check["table_count"],
        "file_mode": "0600",
        "contains_customer_data": True,
    }


def _safe_failure(exc: Exception) -> dict[str, Any]:
    code = getattr(exc, "code", None) or type(exc).__name__
    return {
        "schema_version": "0.1",
        "status": "FAIL",
        "operation": "CREATE_BACKUP",
        "error_class": str(code)[:120],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a consistent MedicalChannelAI Pilot SQLite backup")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()
    try:
        result = create_sqlite_backup(db_path=args.db, out_dir=args.out_dir, keep=args.keep)
    except Exception as exc:
        result = _safe_failure(exc)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
