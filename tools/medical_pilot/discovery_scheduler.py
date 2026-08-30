from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Callable, Any
from zoneinfo import ZoneInfo

from .discovery_cadence import load_discovery_policy, plan_discovery_cadence
from .discovery_runtime import (
    DISCOVERY_READY_LISTINGS,
    DiscoveryRunResult,
    discovery_readiness,
    run_source_discovery_once,
)


@dataclass(frozen=True)
class DiscoveryScheduleSlot:
    source_id: str
    slot_id: str
    kind: str
    scheduled_for: str
    interval_minutes: int
    consecutive_failures: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "source_id": self.source_id,
            "slot_id": self.slot_id,
            "kind": self.kind,
            "scheduled_for": self.scheduled_for,
            "interval_minutes": self.interval_minutes,
            "consecutive_failures": self.consecutive_failures,
        }


@dataclass(frozen=True)
class DiscoveryTickResult:
    local_time: str
    due_sources: tuple[str, ...]
    claimed_sources: tuple[str, ...]
    duplicate_claim_sources: tuple[str, ...]
    succeeded_sources: tuple[str, ...]
    failed_sources: tuple[dict[str, str], ...]
    runs: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "local_time": self.local_time,
            "due_sources": list(self.due_sources),
            "claimed_sources": list(self.claimed_sources),
            "duplicate_claim_sources": list(self.duplicate_claim_sources),
            "succeeded_sources": list(self.succeeded_sources),
            "failed_sources": list(self.failed_sources),
            "runs": list(self.runs),
        }


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")


def _utc_iso(value: datetime) -> str:
    _require_aware(value)
    return value.astimezone(timezone.utc).isoformat()


def _minute(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def _forced_slot(
    source_id: str,
    *,
    local: datetime,
    minute_offset: int,
    policy: dict[str, Any],
    interval_minutes: int,
    consecutive_failures: int,
) -> DiscoveryScheduleSlot | None:
    minute_of_day = local.hour * 60 + local.minute
    for item in policy.get("forced_refresh_windows") or []:
        if not isinstance(item, dict) or not isinstance(item.get("window"), str):
            continue
        start_raw, end_raw = item["window"].split("-", 1)
        start = _minute(start_raw)
        end = _minute(end_raw)
        span = end - start
        if span <= 0:
            raise ValueError("forced refresh window must not cross midnight")
        scheduled_minute = start + (minute_offset % span)
        if minute_of_day != scheduled_minute:
            continue
        scheduled = local.replace(
            hour=scheduled_minute // 60,
            minute=scheduled_minute % 60,
            second=0,
            microsecond=0,
        )
        slot_id = f"forced|{source_id}|{scheduled.date().isoformat()}|{start_raw}-{end_raw}"
        return DiscoveryScheduleSlot(
            source_id=source_id,
            slot_id=slot_id,
            kind="FORCED_REFRESH",
            scheduled_for=scheduled.isoformat(),
            interval_minutes=interval_minutes,
            consecutive_failures=consecutive_failures,
        )
    return None


def due_discovery_slot(
    source_id: str,
    *,
    now: datetime,
    consecutive_failures: int = 0,
) -> DiscoveryScheduleSlot | None:
    """Return the unique source slot due at this local minute, if any.

    Only sources with a verified dedicated discovery contract are eligible. Stable
    source minute offsets are honored. Source-level consecutive failures widen the
    regular cadence through the existing policy. Forced refresh windows intentionally
    bypass regular backoff but still use a stable per-source minute inside the window.

    The v0.1 scheduler is minute-granular. The policy's sub-minute jitter remains a
    future deployment concern; stable minute offsets already prevent synchronized
    source bursts in the single-host Pilot.
    """

    _require_aware(now)
    ready, _reason = discovery_readiness(source_id)
    if not ready:
        return None
    decision = plan_discovery_cadence(
        source_id,
        now=now,
        consecutive_failures=consecutive_failures,
    )
    policy = load_discovery_policy()
    timezone_name = str(policy["timezone"])
    local = now.astimezone(ZoneInfo(timezone_name))

    forced = _forced_slot(
        source_id,
        local=local,
        minute_offset=decision.minute_offset,
        policy=policy,
        interval_minutes=decision.interval_minutes,
        consecutive_failures=consecutive_failures,
    )
    if forced is not None:
        return forced

    minute_of_day = local.hour * 60 + local.minute
    if minute_of_day % decision.interval_minutes != decision.minute_offset:
        return None

    scheduled = local.replace(second=0, microsecond=0)
    slot_id = (
        f"regular|{source_id}|{scheduled.date().isoformat()}|"
        f"{minute_of_day:04d}|i{decision.interval_minutes}"
    )
    return DiscoveryScheduleSlot(
        source_id=source_id,
        slot_id=slot_id,
        kind="REGULAR",
        scheduled_for=scheduled.isoformat(),
        interval_minutes=decision.interval_minutes,
        consecutive_failures=consecutive_failures,
    )


class SQLiteDiscoveryScheduleLedger:
    """Persistent same-host slot claims plus source-level listing health state."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_discovery_schedule_slots ("
                "source_id TEXT NOT NULL, "
                "slot_id TEXT NOT NULL, "
                "slot_kind TEXT NOT NULL, "
                "scheduled_for TEXT NOT NULL, "
                "claimed_at TEXT NOT NULL, "
                "completed_at TEXT NULL, "
                "status TEXT NOT NULL, "
                "error_code TEXT NULL, "
                "PRIMARY KEY(source_id, slot_id))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_discovery_source_state ("
                "source_id TEXT PRIMARY KEY, "
                "consecutive_failures INTEGER NOT NULL DEFAULT 0, "
                "last_attempt_at TEXT NULL, "
                "last_success_at TEXT NULL, "
                "last_error_code TEXT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def consecutive_failures(self, source_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT consecutive_failures FROM medical_discovery_source_state WHERE source_id=?",
                (source_id,),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def claim(self, slot: DiscoveryScheduleSlot, *, now: datetime) -> bool:
        _require_aware(now)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO medical_discovery_schedule_slots("
                "source_id, slot_id, slot_kind, scheduled_for, claimed_at, status"
                ") VALUES (?, ?, ?, ?, ?, 'CLAIMED')",
                (
                    slot.source_id,
                    slot.slot_id,
                    slot.kind,
                    slot.scheduled_for,
                    _utc_iso(now),
                ),
            )
        return cursor.rowcount == 1

    def mark_success(self, slot: DiscoveryScheduleSlot, *, now: datetime) -> None:
        timestamp = _utc_iso(now)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE medical_discovery_schedule_slots SET completed_at=?, status='SUCCEEDED', error_code=NULL "
                "WHERE source_id=? AND slot_id=? AND status='CLAIMED'",
                (timestamp, slot.source_id, slot.slot_id),
            )
            conn.execute(
                "INSERT INTO medical_discovery_source_state("
                "source_id, consecutive_failures, last_attempt_at, last_success_at, last_error_code"
                ") VALUES (?, 0, ?, ?, NULL) "
                "ON CONFLICT(source_id) DO UPDATE SET "
                "consecutive_failures=0, last_attempt_at=excluded.last_attempt_at, "
                "last_success_at=excluded.last_success_at, last_error_code=NULL",
                (slot.source_id, timestamp, timestamp),
            )
            conn.execute("COMMIT")

    def mark_failure(
        self,
        slot: DiscoveryScheduleSlot,
        *,
        now: datetime,
        error_code: str,
    ) -> None:
        timestamp = _utc_iso(now)
        safe_error = str(error_code)[:120] or "UNKNOWN_ERROR"
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE medical_discovery_schedule_slots SET completed_at=?, status='FAILED', error_code=? "
                "WHERE source_id=? AND slot_id=? AND status='CLAIMED'",
                (timestamp, safe_error, slot.source_id, slot.slot_id),
            )
            conn.execute(
                "INSERT INTO medical_discovery_source_state("
                "source_id, consecutive_failures, last_attempt_at, last_success_at, last_error_code"
                ") VALUES (?, 1, ?, NULL, ?) "
                "ON CONFLICT(source_id) DO UPDATE SET "
                "consecutive_failures=medical_discovery_source_state.consecutive_failures+1, "
                "last_attempt_at=excluded.last_attempt_at, last_error_code=excluded.last_error_code",
                (slot.source_id, timestamp, safe_error),
            )
            conn.execute("COMMIT")


def run_due_discovery_tick(
    *,
    db_path: Path,
    now: datetime,
    run_source: Callable[..., DiscoveryRunResult] = run_source_discovery_once,
) -> DiscoveryTickResult:
    """Run every due, verified discovery source once for the current minute slot."""

    _require_aware(now)
    ledger = SQLiteDiscoveryScheduleLedger(db_path)
    policy = load_discovery_policy()
    local = now.astimezone(ZoneInfo(str(policy["timezone"])))

    due_sources: list[str] = []
    claimed_sources: list[str] = []
    duplicate_claim_sources: list[str] = []
    succeeded_sources: list[str] = []
    failed_sources: list[dict[str, str]] = []
    runs: list[dict[str, Any]] = []

    for source_id in sorted(DISCOVERY_READY_LISTINGS):
        failures = ledger.consecutive_failures(source_id)
        slot = due_discovery_slot(
            source_id,
            now=now,
            consecutive_failures=failures,
        )
        if slot is None:
            continue
        due_sources.append(source_id)
        if not ledger.claim(slot, now=now):
            duplicate_claim_sources.append(source_id)
            continue
        claimed_sources.append(source_id)
        try:
            result = run_source(source_id, db_path=db_path, now=now)
        except Exception as exc:
            code = str(getattr(exc, "code", exc.__class__.__name__))[:120]
            ledger.mark_failure(slot, now=now, error_code=code)
            failed_sources.append({"source_id": source_id, "code": code})
            continue
        ledger.mark_success(slot, now=now)
        succeeded_sources.append(source_id)
        runs.append(result.as_dict())

    return DiscoveryTickResult(
        local_time=local.isoformat(),
        due_sources=tuple(due_sources),
        claimed_sources=tuple(claimed_sources),
        duplicate_claim_sources=tuple(duplicate_claim_sources),
        succeeded_sources=tuple(succeeded_sources),
        failed_sources=tuple(failed_sources),
        runs=tuple(runs),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one persistent cadence tick for verified Tianjin Pilot discovery sources."
    )
    parser.add_argument("--db", required=True, type=Path, help="Single-host Pilot SQLite path")
    args = parser.parse_args()
    result = run_due_discovery_tick(
        db_path=args.db,
        now=datetime.now(timezone.utc),
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
