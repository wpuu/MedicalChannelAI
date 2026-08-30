from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .registry import REGISTRY_PATH, RegisteredSource, load_registry


COVERAGE_MANIFEST_PATH = Path(__file__).with_name("coverage_manifest.tianjin.v0.1.json")


@dataclass(frozen=True)
class SourceObservation:
    source_id: str
    checked_at: str
    success: bool
    full_refresh_complete: bool
    last_success_at: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class SourceHealth:
    source_id: str
    health_status: str
    checked_at: str | None
    last_success_at: str | None
    error_code: str | None
    reason: str

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "health_status": self.health_status,
            "checked_at": self.checked_at,
            "last_success_at": self.last_success_at,
            "error_code": self.error_code,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CoverageReport:
    scope_id: str
    scope_label: str
    coverage_status: str
    exhaustiveness_claim: str
    required_source_health: tuple[SourceHealth, ...]
    missing_implementation_source_ids: tuple[str, ...]
    optional_missing_source_ids: tuple[str, ...]
    failed_source_ids: tuple[str, ...]
    unknown_source_ids: tuple[str, ...]
    generated_at: str

    def as_dict(self) -> dict:
        return {
            "scope_id": self.scope_id,
            "scope_label": self.scope_label,
            "coverage_status": self.coverage_status,
            "exhaustiveness_claim": self.exhaustiveness_claim,
            "required_source_health": [item.as_dict() for item in self.required_source_health],
            "missing_implementation_source_ids": list(self.missing_implementation_source_ids),
            "optional_missing_source_ids": list(self.optional_missing_source_ids),
            "failed_source_ids": list(self.failed_source_ids),
            "unknown_source_ids": list(self.unknown_source_ids),
            "generated_at": self.generated_at,
        }


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def load_coverage_manifest(path: Path = COVERAGE_MANIFEST_PATH) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_source_health(
    source: RegisteredSource,
    observation: SourceObservation | None,
    *,
    now: datetime,
) -> SourceHealth:
    if not source.enabled:
        return SourceHealth(
            source_id=source.source_id,
            health_status="DISABLED",
            checked_at=None,
            last_success_at=None,
            error_code=None,
            reason="source disabled in runtime registry",
        )
    if observation is None:
        return SourceHealth(
            source_id=source.source_id,
            health_status="UNKNOWN",
            checked_at=None,
            last_success_at=None,
            error_code=None,
            reason="no refresh observation available",
        )
    if observation.source_id != source.source_id:
        raise ValueError("observation/source_id mismatch")

    if not observation.success:
        return SourceHealth(
            source_id=source.source_id,
            health_status="FAILED",
            checked_at=observation.checked_at,
            last_success_at=observation.last_success_at,
            error_code=observation.error_code or "UNKNOWN_FETCH_ERROR",
            reason="latest refresh failed",
        )

    if not observation.full_refresh_complete:
        return SourceHealth(
            source_id=source.source_id,
            health_status="DEGRADED",
            checked_at=observation.checked_at,
            last_success_at=observation.last_success_at or observation.checked_at,
            error_code=observation.error_code,
            reason="refresh succeeded only partially",
        )

    last_success_at = observation.last_success_at or observation.checked_at
    success_time = _parse_iso(last_success_at)
    age_minutes = (now.astimezone(timezone.utc) - success_time).total_seconds() / 60
    freshness_sla = int(source.raw.get("freshness_sla_minutes") or 60)
    if age_minutes < 0:
        return SourceHealth(
            source_id=source.source_id,
            health_status="DEGRADED",
            checked_at=observation.checked_at,
            last_success_at=last_success_at,
            error_code="CLOCK_SKEW",
            reason="last success timestamp is in the future",
        )
    if age_minutes > freshness_sla:
        return SourceHealth(
            source_id=source.source_id,
            health_status="DEGRADED",
            checked_at=observation.checked_at,
            last_success_at=last_success_at,
            error_code="STALE_SOURCE",
            reason=f"last full success exceeds {freshness_sla} minute freshness SLA",
        )
    return SourceHealth(
        source_id=source.source_id,
        health_status="HEALTHY",
        checked_at=observation.checked_at,
        last_success_at=last_success_at,
        error_code=None,
        reason="latest full refresh is within freshness SLA",
    )


def build_coverage_report(
    observations: Iterable[SourceObservation],
    *,
    now: datetime,
    registry_path: Path = REGISTRY_PATH,
    manifest_path: Path = COVERAGE_MANIFEST_PATH,
) -> CoverageReport:
    registry = {source.source_id: source for source in load_registry(registry_path)}
    manifest = load_coverage_manifest(manifest_path)
    observation_map = {observation.source_id: observation for observation in observations}

    required_health: list[SourceHealth] = []
    missing_implementation: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []

    for requirement in manifest.get("required_sources", []):
        source_id = requirement["source_id"]
        if requirement.get("implementation_status") != "IMPLEMENTED":
            missing_implementation.append(source_id)
            continue
        source = registry.get(source_id)
        if source is None:
            missing_implementation.append(source_id)
            continue
        health = evaluate_source_health(source, observation_map.get(source_id), now=now)
        required_health.append(health)
        if health.health_status in {"FAILED", "DEGRADED", "DISABLED"}:
            failed.append(source_id)
        elif health.health_status == "UNKNOWN":
            unknown.append(source_id)

    optional_missing = tuple(
        item["source_id"]
        for item in manifest.get("optional_sources", [])
        if item.get("implementation_status") != "IMPLEMENTED"
    )

    if failed:
        coverage_status = "DEGRADED"
    elif missing_implementation or unknown:
        coverage_status = "PARTIAL"
    elif required_health:
        coverage_status = "CURRENT"
    else:
        coverage_status = "UNKNOWN"

    return CoverageReport(
        scope_id=manifest["scope_id"],
        scope_label=manifest["scope_label"],
        coverage_status=coverage_status,
        exhaustiveness_claim=manifest.get("exhaustiveness_claim", "NOT_EXHAUSTIVE"),
        required_source_health=tuple(required_health),
        missing_implementation_source_ids=tuple(sorted(missing_implementation)),
        optional_missing_source_ids=tuple(sorted(optional_missing)),
        failed_source_ids=tuple(sorted(failed)),
        unknown_source_ids=tuple(sorted(unknown)),
        generated_at=now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
