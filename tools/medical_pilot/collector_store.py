from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .collector_core import deterministic_id, normalize_space
from .institution_enrichment import (
    enrich_opportunity_customer_type,
    resolve_institution_evidence,
)
from .lifecycle import resolve_project_lifecycle
from .product_classifier import apply_product_classification, classify_product_facts
from .registry import RegisteredSource, load_registry
from .today_repo import SQLiteTodayActionsRepository


_PRIVATE_EVENT_FIELDS = {
    "tenant_id",
    "profile_id",
    "customer_context",
    "hospital_relationships",
    "product_capabilities",
    "partnering_policy",
    "followup",
    "followup_history",
}


class SQLitePublicEventLedger:
    """Single-host public event ledger used to rebuild current lifecycle safely."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_public_events ("
                "event_id TEXT PRIMARY KEY, "
                "canonical_project_id TEXT NOT NULL, "
                "effective_at TEXT NOT NULL, "
                "payload TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_medical_public_events_project "
                "ON medical_public_events(canonical_project_id, effective_at, event_id)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _validate_event(event: dict[str, Any]) -> tuple[str, str, str]:
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        leaked = sorted(_PRIVATE_EVENT_FIELDS.intersection(event))
        if leaked:
            raise ValueError(f"public event contains customer-private fields: {','.join(leaked)}")
        event_id = event.get("event_id")
        project_id = event.get("canonical_project_id")
        effective_at = event.get("effective_at") or event.get("published_at")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event.event_id is required")
        if not isinstance(project_id, str) or not project_id:
            raise ValueError("event.canonical_project_id is required")
        if not isinstance(effective_at, str) or not effective_at:
            raise ValueError("event effective_at/published_at is required")
        return event_id, project_id, effective_at

    def upsert(self, event: dict[str, Any]) -> None:
        event = copy.deepcopy(event)
        event_id, project_id, effective_at = self._validate_event(event)
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO medical_public_events(event_id, canonical_project_id, effective_at, payload) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "canonical_project_id=excluded.canonical_project_id, "
                "effective_at=excluded.effective_at, payload=excluded.payload",
                (event_id, project_id, effective_at, payload),
            )

    def list_project_events(self, canonical_project_id: str) -> list[dict[str, Any]]:
        if not isinstance(canonical_project_id, str) or not canonical_project_id:
            raise ValueError("canonical_project_id is required")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM medical_public_events "
                "WHERE canonical_project_id=? ORDER BY effective_at, event_id",
                (canonical_project_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            event = json.loads(row[0])
            self._validate_event(event)
            result.append(event)
        return result


def _source_by_id(source_id: str, registry: Iterable[RegisteredSource]) -> RegisteredSource:
    matches = [source for source in registry if source.source_id == source_id]
    if len(matches) != 1:
        raise ValueError(f"source registry does not resolve source_id={source_id}")
    return matches[0]


def _facts_for_event(facts: list[dict[str, Any]], event_id: str) -> list[dict[str, Any]]:
    return [
        fact
        for fact in facts
        if isinstance(fact, dict)
        and fact.get("event_id") == event_id
        and fact.get("fact_type") == "OFFICIAL_PUBLIC_FACT"
        and fact.get("verification_status") == "VERIFIED"
        and fact.get("model_generated") is False
    ]


def _field_value(current_facts: list[dict[str, Any]], field_name: str) -> tuple[Any, bool]:
    matches = [fact for fact in current_facts if fact.get("field_name") == field_name]
    if not matches:
        return None, False
    unique: dict[str, Any] = {}
    for fact in matches:
        value = fact.get("field_value")
        key = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        unique[key] = value
    if len(unique) != 1:
        return None, True
    return next(iter(unique.values())), False


def _region_for_source(source: RegisteredSource, buyer_name: str) -> dict[str, Any]:
    scope = source.raw.get("geographic_scope")
    if not isinstance(scope, dict):
        raise ValueError(f"source {source.source_id} is missing geographic_scope")
    country = scope.get("country")
    province = scope.get("province")
    city = scope.get("city")
    district = scope.get("district")
    if not all(isinstance(value, str) and value for value in (country, province, city)):
        raise ValueError(f"source {source.source_id} geographic_scope is incomplete")

    result = {
        "country": country,
        "province": province,
        "city": city,
        "district": district if isinstance(district, str) and district else None,
    }
    institution = resolve_institution_evidence(buyer_name)
    if institution is not None:
        evidence_region = institution.region
        if result["district"] is None and isinstance(evidence_region.get("district"), str):
            result["district"] = evidence_region["district"]
    return result


def _hospital_name(buyer_name: str) -> str | None:
    institution = resolve_institution_evidence(buyer_name)
    if institution is None or institution.institution_type != "HOSPITAL":
        return None
    return institution.canonical_name


def _rental_classification(facts: list[dict[str, Any]]) -> tuple[bool | None, str]:
    texts: list[str] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        if fact.get("fact_type") != "OFFICIAL_PUBLIC_FACT":
            continue
        if fact.get("verification_status") != "VERIFIED" or fact.get("model_generated") is not False:
            continue
        value = fact.get("field_value")
        if isinstance(value, str) and value.strip():
            texts.append(normalize_space(value))
    joined = "\n".join(texts)
    if any(marker in joined for marker in ("租赁", "租用", "租借", "出租")):
        return True, "DETERMINISTIC_EXPLICIT_RENTAL_PHRASE"
    if any(marker in joined for marker in ("购置", "购买", "买断")):
        return False, "DETERMINISTIC_EXPLICIT_PURCHASE_PHRASE"
    return None, "UNRESOLVED"


def _award_product_items(current_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for fact in current_facts:
        if fact.get("field_name") != "award_items":
            continue
        value = fact.get("field_value")
        if not isinstance(value, list):
            continue
        fact_id = fact.get("fact_id")
        if not isinstance(fact_id, str):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            raw_name = item.get("raw_name")
            if not isinstance(raw_name, str) or not raw_name.strip():
                continue
            result.append(
                {
                    "raw_name": raw_name.strip(),
                    "normalized_name": None,
                    "category_l1": None,
                    "category_l2": None,
                    "category_l3": None,
                    "quantity": item.get("quantity") if isinstance(item.get("quantity"), str) else None,
                    "unit": None,
                    "brand_if_officially_stated": item.get("brand") if isinstance(item.get("brand"), str) else None,
                    "model_if_officially_stated": item.get("model") if isinstance(item.get("model"), str) else None,
                    "fact_ids": [fact_id],
                }
            )
    return result


def build_opportunity_projection(
    *,
    events: list[dict[str, Any]],
    evidence_facts: list[dict[str, Any]],
    registry: list[RegisteredSource] | None = None,
) -> dict[str, Any]:
    """Project a current matchable opportunity from public event/fact evidence only."""

    if not events:
        raise ValueError("events are required")
    sources = registry if registry is not None else load_registry()
    lifecycle = resolve_project_lifecycle(events)
    current = next(
        (event for event in events if event.get("event_id") == lifecycle.current_event_id),
        None,
    )
    if current is None:
        raise RuntimeError("current lifecycle event is absent from event ledger")
    source = _source_by_id(str(current.get("source_id") or ""), sources)
    opportunity_id = deterministic_id("opp", f"opportunity|{lifecycle.canonical_project_id}")

    facts = [
        copy.deepcopy(fact)
        for fact in evidence_facts
        if isinstance(fact, dict) and fact.get("opportunity_id") == opportunity_id
    ]
    current_facts = _facts_for_event(facts, lifecycle.current_event_id)

    project_name, project_conflict = _field_value(current_facts, "project_name")
    buyer_name, buyer_conflict = _field_value(current_facts, "buyer_name")
    published_at, published_conflict = _field_value(current_facts, "published_at")
    project_number, number_conflict = _field_value(current_facts, "project_number")
    budget_cny, budget_conflict = _field_value(current_facts, "budget_cny")
    registration_deadline, registration_conflict = _field_value(current_facts, "registration_deadline")
    bid_deadline, bid_conflict = _field_value(current_facts, "bid_deadline")
    procurement_method, method_conflict = _field_value(current_facts, "procurement_method")
    expected_procurement_at, expected_conflict = _field_value(current_facts, "expected_procurement_at")

    if not isinstance(project_name, str) or not project_name.strip():
        raise ValueError("current verified event is missing a unique project_name fact")
    if not isinstance(buyer_name, str) or not buyer_name.strip():
        raise ValueError("current verified event is missing a unique buyer_name fact")

    fact_conflict = any(
        (
            project_conflict,
            buyer_conflict,
            published_conflict,
            number_conflict,
            budget_conflict,
            registration_conflict,
            bid_conflict,
            method_conflict,
            expected_conflict,
        )
    )
    verification_status = (
        "CONFLICTED"
        if lifecycle.verification_status == "CONFLICTED" or fact_conflict
        else lifecycle.verification_status
    )

    # Product/rental classification is intentionally scoped to the current lifecycle
    # event. Older intent/tender wording must not contaminate a later amendment/award.
    rental, rental_provenance = _rental_classification(current_facts)
    institution = resolve_institution_evidence(buyer_name)
    opportunity: dict[str, Any] = {
        "schema_version": "0.1",
        "opportunity_id": opportunity_id,
        "canonical_project_id": lifecycle.canonical_project_id,
        "project_number": project_number if isinstance(project_number, str) else current.get("project_number"),
        "buyer_name": buyer_name.strip(),
        "hospital_name": _hospital_name(buyer_name),
        "department": None,
        "region": _region_for_source(source, buyer_name),
        "project_name": project_name.strip(),
        "notice_type": current.get("event_type"),
        "lifecycle_state": lifecycle.lifecycle_state,
        "published_at": published_at if isinstance(published_at, str) else current.get("published_at"),
        "published_at_precision": current.get("published_at_precision"),
        "registration_deadline": registration_deadline if isinstance(registration_deadline, str) else None,
        "bid_deadline": bid_deadline if isinstance(bid_deadline, str) else None,
        "expected_procurement_at": expected_procurement_at if isinstance(expected_procurement_at, str) else None,
        "expected_procurement_precision": (
            "MONTH"
            if isinstance(expected_procurement_at, str) and len(expected_procurement_at) == 7
            else "DAY"
            if isinstance(expected_procurement_at, str) and len(expected_procurement_at) == 10
            else None
        ),
        "budget": {"amount": budget_cny, "currency": "CNY"} if isinstance(budget_cny, str) else None,
        "procurement_method": procurement_method if isinstance(procurement_method, str) else None,
        "product_categories": [],
        "product_items": _award_product_items(current_facts),
        "public_contact": None,
        "source_event_ids": list(lifecycle.source_event_ids),
        "current_event_id": lifecycle.current_event_id,
        "verification_status": verification_status,
        "coverage_status": "PARTIAL",
        "last_full_refresh_at": None,
        "created_at": min(
            str(event.get("fetched_at") or event.get("published_at") or "")
            for event in events
        ),
        "updated_at": str(current.get("fetched_at") or current.get("published_at") or ""),
        "is_rental_project": rental,
        "rental_classification_provenance": rental_provenance,
        "customer_type": "UNKNOWN",
        "customer_type_provenance": "UNRESOLVED",
        "customer_type_validation_status": "UNVERIFIED",
        "institution_evidence_id": None,
    }
    if institution is not None:
        opportunity["buyer_type"] = institution.institution_type
    opportunity = apply_product_classification(
        opportunity,
        classify_product_facts(current_facts),
    )
    opportunity = enrich_opportunity_customer_type(opportunity)
    return opportunity


def persist_collector_result(
    *,
    repository: SQLiteTodayActionsRepository,
    event_ledger: SQLitePublicEventLedger,
    event: dict[str, Any],
    facts: list[dict[str, Any]],
    registry: list[RegisteredSource] | None = None,
) -> dict[str, Any]:
    """Persist one collector result and rebuild its current public opportunity.

    Event is persisted first. If a later write fails, the user-facing opportunity is
    never allowed to invent missing evidence: Today Actions will either keep the old
    projection or block model grounding until the evidence write succeeds.
    """

    event_ledger.upsert(event)
    project_id = event.get("canonical_project_id")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("event.canonical_project_id is required")
    events = event_ledger.list_project_events(project_id)
    opportunity_id = deterministic_id("opp", f"opportunity|{project_id}")
    existing = repository.load_evidence("public-ingest", [opportunity_id]).get(opportunity_id, [])
    merged: dict[str, dict[str, Any]] = {
        fact["fact_id"]: copy.deepcopy(fact)
        for fact in existing
        if isinstance(fact, dict) and isinstance(fact.get("fact_id"), str)
    }
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        fact_id = fact.get("fact_id")
        if isinstance(fact_id, str) and fact_id:
            merged[fact_id] = copy.deepcopy(fact)
    all_facts = list(merged.values())
    opportunity = build_opportunity_projection(
        events=events,
        evidence_facts=all_facts,
        registry=registry,
    )
    repository.upsert_public_opportunity(opportunity)
    for fact in facts:
        if isinstance(fact, dict):
            repository.upsert_public_evidence(fact)
    return opportunity
