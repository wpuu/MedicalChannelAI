from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_sqlite_backup(
    *,
    db_path: Path,
    out_dir: Path,
    keep: int = 14,
    now: datetime | None = None,
) -> dict[str, object]:
    db_path = Path(db_path)
    out_dir = Path(out_dir)
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")
    if not isinstance(keep, int) or isinstance(keep, bool) or keep < 1 or keep > 365:
        raise ValueError("keep must be an integer between 1 and 365")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    current = current.astimezone(timezone.utc)

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = current.strftime("%Y%m%dT%H%M%SZ")
    final_path = out_dir / f"pilot-{timestamp}.sqlite"
    temp_path = out_dir / f".pilot-{timestamp}.sqlite.tmp"
    if final_path.exists() or temp_path.exists():
        raise FileExistsError(f"backup target already exists for {timestamp}")

    try:
        source = sqlite3.connect(str(db_path), timeout=30.0)
        destination = sqlite3.connect(str(temp_path), timeout=30.0)
        try:
            source.execute("PRAGMA busy_timeout=30000")
            destination.execute("PRAGMA busy_timeout=30000")
            source.backup(destination)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise RuntimeError("backup integrity_check failed")
        finally:
            destination.close()
            source.close()
        temp_path.chmod(0o600)
        temp_path.replace(final_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    backups = sorted(
        (
            item
            for item in out_dir.glob("pilot-*.sqlite")
            if item.is_file() and item.name != final_path.name
        ),
        key=lambda item: item.name,
        reverse=True,
    )
    removed: list[str] = []
    for stale in backups[max(keep - 1, 0) :]:
        stale.unlink()
        removed.append(stale.name)

    return {
        "schema_version": "0.1",
        "backup_file": final_path.name,
        "created_at": current.isoformat(),
        "size_bytes": final_path.stat().st_size,
        "sha256": _sha256_file(final_path),
        "retention_keep": keep,
        "removed": removed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a consistent MedicalChannelAI Pilot SQLite backup")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()
    result = create_sqlite_backup(db_path=args.db, out_dir=args.out_dir, keep=args.keep)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
