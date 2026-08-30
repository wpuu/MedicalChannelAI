from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any


_PRIVATE_TOP_LEVEL_FIELDS = {
    "tenant_id",
    "profile_id",
    "customer_context",
    "hospital_relationships",
    "product_capabilities",
    "partnering_policy",
    "followup",
    "followup_history",
    "followup_status",
}


def _json_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _required_text(value: Any, name: str, *, max_length: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    text = value.strip()
    if len(text) > max_length:
        raise ValueError(f"{name} is too long")
    return text


def _reject_private_public_payload(payload: dict[str, Any], name: str) -> None:
    leaked = sorted(_PRIVATE_TOP_LEVEL_FIELDS.intersection(payload))
    if leaked:
        raise ValueError(f"{name} contains customer-private fields: {','.join(leaked)}")


def _payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sort_time(opportunity: dict[str, Any]) -> str:
    for key in ("published_at", "publish_date", "first_seen_at", "updated_at", "last_seen_at"):
        value = opportunity.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class SQLiteTodayActionsRepository:
    """Single-host Pilot repository with tenant-private profiles and shared public facts.

    Public procurement opportunities/evidence are stored once and may be evaluated by
    multiple tenants. Customer profiles remain tenant-scoped. This avoids duplicating
    the same government procurement records for every customer while preserving the
    private-data boundary required by Today Actions.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_customer_profiles ("
                "tenant_id TEXT NOT NULL, "
                "profile_id TEXT NOT NULL, "
                "updated_at TEXT NOT NULL, "
                "payload TEXT NOT NULL, "
                "PRIMARY KEY(tenant_id, profile_id))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_public_opportunities ("
                "opportunity_id TEXT PRIMARY KEY, "
                "sort_time TEXT NOT NULL, "
                "payload TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_medical_public_opportunities_time "
                "ON medical_public_opportunities(sort_time DESC, opportunity_id)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_public_evidence ("
                "fact_id TEXT PRIMARY KEY, "
                "opportunity_id TEXT NOT NULL, "
                "verification_status TEXT NOT NULL, "
                "payload TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_medical_public_evidence_opp "
                "ON medical_public_evidence(opportunity_id, fact_id)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def upsert_profile(self, profile: dict[str, Any]) -> None:
        profile = copy.deepcopy(_json_object(profile, "profile"))
        tenant_id = _required_text(profile.get("tenant_id"), "profile.tenant_id", max_length=128)
        profile_id = _required_text(profile.get("profile_id"), "profile.profile_id", max_length=160)
        updated_at = profile.get("updated_at")
        if not isinstance(updated_at, str) or not updated_at.strip():
            updated_at = ""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO medical_customer_profiles(tenant_id, profile_id, updated_at, payload) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(tenant_id, profile_id) DO UPDATE SET "
                "updated_at=excluded.updated_at, payload=excluded.payload",
                (tenant_id, profile_id, updated_at, _payload_json(profile)),
            )

    def upsert_public_opportunity(self, opportunity: dict[str, Any]) -> None:
        opportunity = copy.deepcopy(_json_object(opportunity, "opportunity"))
        _reject_private_public_payload(opportunity, "opportunity")
        opportunity_id = _required_text(
            opportunity.get("opportunity_id"),
            "opportunity.opportunity_id",
            max_length=160,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO medical_public_opportunities(opportunity_id, sort_time, payload) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(opportunity_id) DO UPDATE SET "
                "sort_time=excluded.sort_time, payload=excluded.payload",
                (opportunity_id, _sort_time(opportunity), _payload_json(opportunity)),
            )

    def upsert_public_evidence(self, evidence: dict[str, Any]) -> None:
        evidence = copy.deepcopy(_json_object(evidence, "evidence"))
        _reject_private_public_payload(evidence, "evidence")
        fact_id = _required_text(evidence.get("fact_id"), "evidence.fact_id", max_length=180)
        opportunity_id = _required_text(
            evidence.get("opportunity_id"),
            "evidence.opportunity_id",
            max_length=160,
        )
        verification_status = _required_text(
            evidence.get("verification_status"),
            "evidence.verification_status",
            max_length=40,
        )
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM medical_public_opportunities WHERE opportunity_id=?",
                (opportunity_id,),
            ).fetchone()
            if exists is None:
                raise ValueError("evidence opportunity_id is not present in public opportunity store")
            conn.execute(
                "INSERT INTO medical_public_evidence(fact_id, opportunity_id, verification_status, payload) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(fact_id) DO UPDATE SET "
                "opportunity_id=excluded.opportunity_id, "
                "verification_status=excluded.verification_status, payload=excluded.payload",
                (fact_id, opportunity_id, verification_status, _payload_json(evidence)),
            )

    def load_profile(self, tenant_id: str, profile_id: str) -> dict[str, Any] | None:
        tenant_id = _required_text(tenant_id, "tenant_id", max_length=128)
        profile_id = _required_text(profile_id, "profile_id", max_length=160)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM medical_customer_profiles "
                "WHERE tenant_id=? AND profile_id=?",
                (tenant_id, profile_id),
            ).fetchone()
        if row is None:
            return None
        profile = _json_object(json.loads(row[0]), "stored profile")
        if profile.get("tenant_id") != tenant_id or profile.get("profile_id") != profile_id:
            raise RuntimeError("stored profile identity diverges from repository key")
        return copy.deepcopy(profile)

    def load_public_opportunity(self, opportunity_id: str) -> dict[str, Any] | None:
        opportunity_id = _required_text(opportunity_id, "opportunity_id", max_length=160)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM medical_public_opportunities WHERE opportunity_id=?",
                (opportunity_id,),
            ).fetchone()
        if row is None:
            return None
        item = _json_object(json.loads(row[0]), "stored opportunity")
        _reject_private_public_payload(item, "stored opportunity")
        if item.get("opportunity_id") != opportunity_id:
            raise RuntimeError("stored opportunity identity diverges from repository key")
        return copy.deepcopy(item)

    def list_opportunities(
        self,
        tenant_id: str,
        profile: dict[str, Any],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        tenant_id = _required_text(tenant_id, "tenant_id", max_length=128)
        profile = _json_object(profile, "profile")
        if profile.get("tenant_id") != tenant_id:
            raise ValueError("profile tenant_id does not match requested tenant")
        _required_text(profile.get("profile_id"), "profile.profile_id", max_length=160)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 500:
            raise ValueError("limit must be 1..500")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM medical_public_opportunities "
                "ORDER BY sort_time DESC, opportunity_id LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = _json_object(json.loads(row[0]), "stored opportunity")
            _reject_private_public_payload(item, "stored opportunity")
            result.append(item)
        return copy.deepcopy(result)

    def load_evidence(
        self,
        tenant_id: str,
        opportunity_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        _required_text(tenant_id, "tenant_id", max_length=128)
        if not isinstance(opportunity_ids, list) or len(opportunity_ids) > 500:
            raise ValueError("opportunity_ids must be a list with at most 500 entries")
        ids: list[str] = []
        seen: set[str] = set()
        for value in opportunity_ids:
            opportunity_id = _required_text(value, "opportunity_id", max_length=160)
            if opportunity_id not in seen:
                seen.add(opportunity_id)
                ids.append(opportunity_id)
        result: dict[str, list[dict[str, Any]]] = {opportunity_id: [] for opportunity_id in ids}
        if not ids:
            return result
        placeholders = ",".join("?" for _ in ids)
        query = (
            "SELECT opportunity_id, payload FROM medical_public_evidence "
            f"WHERE opportunity_id IN ({placeholders}) ORDER BY opportunity_id, fact_id"
        )
        with self._connect() as conn:
            rows = conn.execute(query, tuple(ids)).fetchall()
        for opportunity_id, payload_raw in rows:
            item = _json_object(json.loads(payload_raw), "stored evidence")
            _reject_private_public_payload(item, "stored evidence")
            if item.get("opportunity_id") != opportunity_id:
                raise RuntimeError("stored evidence opportunity identity diverges from repository key")
            result[str(opportunity_id)].append(item)
        return copy.deepcopy(result)
