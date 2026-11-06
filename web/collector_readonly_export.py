"""Offline-only observation kernel. No client construction, routes or writes.

Two equal reads are evidence of observed stability, never an atomic snapshot.
The scope is a caller assertion, not authentication of the injected reader.
Values not understood by this kernel are preserved as opaque JSON and explicitly
listed as semantically uncovered. This envelope cannot authorize migration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Protocol

import collector_namespace as ns
from collector_epoch import epoch_key
from collector_incremental import SOURCE_POLICIES
from pipeline.medical_channel_pipeline.validation import CRITICAL_FACT_PATHS, validate_records
from pipeline.medical_channel_pipeline.ccgp_events import validate_notice_events


_D_SCOPE = {
    "project_id": "prj_7fk44eKUhdbfTUaXxEBMgIzZiqUM",
    "target": "preview",
    "preview_epoch": "mcai-p0-20261106-d",
    "database": "mcai_p0_epoch_20261106d",
}


class ReadOnlyCache(Protocol):
    def get(self, key: str) -> Any: ...


class ExportRejected(ValueError):
    """No partial export is returned on rejection."""


@dataclass(frozen=True)
class ExportLimits:
    max_value_bytes: int = 4_000_000
    max_total_bytes: int = 16_000_000  # Across BOTH observation passes.
    max_records: int = 10_000  # Includes staging/pending/committed copies.
    max_nodes: int = 500_000
    max_depth: int = 32


def _plan() -> dict[str, dict[str, Any]]:
    # Use v2 namespace constants, never collector_runtime's unbound v1 globals.
    plan = {}
    for name, sources in (
        ("CCGP", ["ccgp"]), ("TJMUGH", ["tjmugh"]),
        ("TJNOTHOP", ["tjnothop"]), ("TEDA", ["teda"]),
        ("TJFCH", ["tjfch", "tjfch_test"]), ("TJZYEFY", ["tjzyefy"]),
        ("TJZYEFY_INTENT", ["tjzyefy_intent"]), ("TJZXFC", ["tjzxfc"]),
    ):
        plan[getattr(ns, f"{name}_RECORDS_KEY")] = {"kind": "canonical", "sources": sources}
    # Exact _regional_records_key format; parity-tested against runtime.
    for market in ("BJ", "HE", "LN", "JL", "HL"):
        plan[f"medicalchannelai:collector-regional-records:v3:{market}"] = {
            "kind": "canonical", "sources": [f"regional_{market.lower()}"], "market": market,
        }
    plan[ns.CCGP_EVENTS_KEY] = {"kind": "events", "sources": ["ccgp"]}
    for key, kind in (
        (ns.META_KEY, "owner_version"), (ns.ACTIVE_CYCLE_KEY, "owner_version"),
        (ns.INCREMENTAL_ACTIVE_KEY, "owner_version"), (ns.INCREMENTAL_CHAIN_KEY, "owner_version"),
        (ns.SOURCE_HEALTH_KEY, "health_clocks"), (ns.CCGP_WATCH_KEY, "watch"),
        ("medicalchannelai:collector-ccgp-committed:v2", "committed"),
        ("medicalchannelai:collector-ccgp-cycle-staging:v2", "staging"),
    ):
        plan[key] = {"kind": kind}
    # SOURCE_POLICIES declares ccgp too; absent optional keys stay uninitialized.
    # Regional incremental state is not implemented by the current producer.
    for source in SOURCE_POLICIES:
        for kind in ("ledger", "bucket", "pending", "pending-barrier"):
            key = f"medicalchannelai:collector-incremental-{kind}:{source}:{ns.NAMESPACE_VERSION}"
            plan[key] = {"kind": kind, "sources": [source]}
    return plan


def _encode(value: Any, limits: ExportLimits) -> bytes:
    nodes = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > limits.max_depth or nodes > limits.max_nodes:
            raise ExportRejected("EXPORT_STRUCTURE_LIMIT")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ExportRejected("EXPORT_NON_JSON_VALUE")
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ExportRejected("EXPORT_NON_JSON_VALUE")

    visit(value, 0)
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError, UnicodeError):
        raise ExportRejected("EXPORT_NON_JSON_VALUE") from None
    if len(encoded) > limits.max_value_bytes:
        raise ExportRejected("EXPORT_VALUE_SIZE_LIMIT")
    return encoded


def _sha(encoded: bytes) -> str:
    return hashlib.sha256(encoded).hexdigest()


def _validate_values(values: dict[str, Any], plan: dict, limits: ExportLimits) -> None:
    total_records = 0
    canonical = []
    try:
        for key, spec in plan.items():
            value = values[key]
            if value is None:
                continue
            kind = spec["kind"]
            if kind in ("canonical", "events", "pending", "pending-barrier", "watch"):
                if type(value) is not list:
                    raise ValueError()
                if kind in ("canonical", "pending"):
                    validate_records(value)
                    total_records += len(value)
                elif kind == "events":
                    validate_notice_events(value)
                elif kind in ("pending-barrier", "watch") and any(type(item) is not str for item in value):
                    raise ValueError()
                if kind == "canonical":
                    if spec.get("market") and any(
                        row["facts"].get("market_code") != spec["market"] for row in value
                    ):
                        raise ValueError()
                    canonical.extend(value)
            else:
                if type(value) is not dict:
                    raise ValueError()
                if kind in ("committed", "staging"):
                    validate_records(value.get("records"))
                    validate_notice_events(value.get("events"))
                    total_records += len(value["records"])
        # Cross-shard duplicate identities are unsafe, even if each shard is valid.
        validate_records(canonical)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise ExportRejected("EXPORT_STATE_INVALID") from None
    if total_records > limits.max_records:
        raise ExportRejected("EXPORT_RECORD_COUNT_LIMIT")


def _uncovered_paths(value: Any, kind: str) -> list[str]:
    """Conservative JSON-pointer paths; unknown values remain opaque, not endorsed."""
    if value is None:
        return []
    escape = lambda key: key.replace('~', '~0').replace('/', '~1')
    if kind not in ("canonical", "pending"):
        return ["/**"]  # Entire auxiliary value's semantics are explicitly uncovered.
    paths = []
    known = {
        "": {"schema_version", "opportunity_id", "source", "facts", "evidence"},
        "source": {"source_type", "url", "observed_at"},
        "facts": {path.split('.', 1)[1] for path in CRITICAL_FACT_PATHS} | {
            "market_code", "market_name", "market_admin_code"},
    }
    for index, row in enumerate(value):
        for part, keys in known.items():
            obj = row if not part else row.get(part, {})
            base = f"/{index}" + (f"/{part}" if part else "")
            for key in obj:
                if key not in keys:
                    paths.append(base + '/' + escape(key))
        # The reused validator checks evidence references, not every extension.
        for number, evidence in enumerate(row['evidence']):
            for key in evidence:
                if key not in {"field_path", "locator", "source_url", "source_text"}:
                    paths.append(f"/{index}/evidence/{number}/" + escape(key))
        for key, item in row['facts'].items():
            if isinstance(item, (dict, list)):
                paths.append(f"/{index}/facts/{escape(key)}/**")
    return sorted(set(paths))


def observe_d_canonical(reader: ReadOnlyCache, *, scope: dict, expected_scope: dict,
                        limits: ExportLimits = ExportLimits()) -> dict[str, Any]:
    """Read a bounded, fixed d plan twice through an explicitly get-only facade.

    None means UNINITIALIZED/UNAVAILABLE (cache eviction is indistinguishable).
    [] means PRESENT_EMPTY. No fallback, normalization or clock inference occurs.
    Caller must not treat the reader's asserted scope as verified provenance.
    """
    if type(scope) is not dict or type(expected_scope) is not dict or (
        scope != _D_SCOPE or expected_scope != _D_SCOPE
    ):
        raise ExportRejected("EXPORT_SCOPE_REJECTED")
    # Validate before any read; limits may only tighten the fixed hard ceilings.
    if type(limits) is not ExportLimits or any(
        type(getattr(limits, name)) is not int or not 0 < getattr(limits, name) <= ceiling
        for name, ceiling in vars(ExportLimits()).items()
    ):
        raise ExportRejected("EXPORT_LIMITS_INVALID")
    if not callable(getattr(reader, "get", None)) or any(
        hasattr(reader, name) for name in ("set", "delete", "expire", "expire_tag", "expireTag", "clear")
    ):
        raise ExportRejected("EXPORT_GET_ONLY_REQUIRED")
    plan = _plan()
    first = {}
    hashes = {}
    total_bytes = 0
    for pass_index in range(2):
        for key in plan:
            physical_key = epoch_key(key, _D_SCOPE["preview_epoch"])
            try:
                value = reader.get(physical_key)
                encoded = _encode(value, limits)
            except ExportRejected:
                raise
            except Exception:
                raise ExportRejected("EXPORT_READ_FAILED") from None
            total_bytes += len(encoded)
            if total_bytes > limits.max_total_bytes:
                raise ExportRejected("EXPORT_TOTAL_SIZE_LIMIT")
            digest = _sha(encoded)
            if pass_index == 0:
                # Detach now, even when an injected reader returns mutable references.
                first[key] = json.loads(encoded)
                hashes[key] = digest
            elif digest != hashes[key]:
                raise ExportRejected("EXPORT_VERSION_OR_OWNER_CHANGED")
    _validate_values(first, plan, limits)
    shards = {}
    for key, spec in plan.items():
        value = first[key]
        shards[key] = {
            **spec, "physical_key": epoch_key(key, _D_SCOPE["preview_epoch"]),
            "state": "UNINITIALIZED_OR_UNAVAILABLE" if value is None else (
                "PRESENT_EMPTY" if value == [] or value == {} else "PRESENT"),
            "sha256": hashes[key], "value": value,
            # Structural observation does not validate metadata/event ownership semantics.
            "semantic_coverage": "CANONICAL_SCHEMA_ONLY" if spec["kind"] in (
                "canonical", "pending") else "OPAQUE_NOT_SEMANTICALLY_COVERED",
            "uncovered_paths": _uncovered_paths(value, spec["kind"]),
        }
    committed = first["medicalchannelai:collector-ccgp-committed:v2"]
    effective_ccgp = "medicalchannelai:collector-ccgp-committed:v2" if committed is not None else ns.CCGP_RECORDS_KEY
    missing = [key for key, spec in plan.items() if spec["kind"] in ("canonical", "events") and first[key] is None]
    return {
        "schema_version": "0.1", "input_kind": "OFFLINE_READONLY_CACHE_OBSERVATION",
        "scope": dict(_D_SCOPE), "scope_provenance_verified": False,
        "status": "OBSERVED_STABLE", "read_plan_complete": True,
        "key_count": len(plan), "read_count": 2 * len(plan), "observed_bytes": total_bytes,
        "observed_state_sha256": _sha(json.dumps(hashes, sort_keys=True).encode()),
        "shards": shards, "effective_ccgp_key": effective_ccgp,
        "missing_canonical_or_event_keys": missing,
        "coverage": {
            "complete": False,
            "uncovered": ["GLOBAL_ATOMIC_REVISION_OR_FENCE", "READER_PROVENANCE",
                "UNKNOWN_CANONICAL_EXTENSION_FIELDS_AND_NESTED_VALUE_SEMANTICS",
                "OPAQUE_METADATA_FIELDS_AND_OWNER_VERSION_SEMANTICS",
                "EVENT_TO_RECORD_AND_PENDING_BARRIER_RELATIONSHIPS",
                "NON_CCGP_EVENT_STORES_NOT_DEFINED_BY_CURRENT_PRODUCER",
                "REGIONAL_INCREMENTAL_STATE_NOT_DEFINED_BY_CURRENT_PRODUCER"],
            "consistency": "TWO_EQUAL_OBSERVATION_PASSES; ABA_AND_CROSS_KEY_RACES_NOT_EXCLUDED",
        },
        "apply_allowed": False, "migration_usable": False,
        "atomic_snapshot_guaranteed": False, "runtime_cas_implemented": False,
    }
