from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .collector_core import normalize_space


DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "research"
    / "fixtures"
    / "tianjin-institution-evidence-v0.1.json"
)


@dataclass(frozen=True)
class InstitutionEvidence:
    institution_id: str
    canonical_name: str
    institution_type: str
    hospital_grade: str | None
    match_customer_type: str
    region: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "institution_id": self.institution_id,
            "canonical_name": self.canonical_name,
            "institution_type": self.institution_type,
            "hospital_grade": self.hospital_grade,
            "match_customer_type": self.match_customer_type,
            "region": self.region,
            "evidence": list(self.evidence),
        }


def _norm_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return normalize_space(value)


def _load_records(path: Path = DEFAULT_REGISTRY_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload.get("institutions")
    if not isinstance(records, list):
        raise ValueError("institution fixture must contain an institutions array")
    return [item for item in records if isinstance(item, dict)]


def resolve_institution_evidence(
    institution_name: str,
    *,
    path: Path = DEFAULT_REGISTRY_PATH,
) -> InstitutionEvidence | None:
    target = _norm_name(institution_name)
    if not target:
        return None

    for record in _load_records(path):
        if record.get("verification_status") != "VERIFIED":
            continue
        canonical = _norm_name(record.get("canonical_name"))
        aliases = {_norm_name(item) for item in record.get("aliases") or [] if _norm_name(item)}
        if target != canonical and target not in aliases:
            continue
        evidence = tuple(
            item
            for item in record.get("evidence") or []
            if isinstance(item, dict) and item.get("verification_status") == "VERIFIED"
        )
        if not evidence:
            return None
        return InstitutionEvidence(
            institution_id=str(record.get("institution_id")),
            canonical_name=canonical,
            institution_type=str(record.get("institution_type")),
            hospital_grade=record.get("hospital_grade"),
            match_customer_type=str(record.get("match_customer_type")),
            region=copy.deepcopy(record.get("region") or {}),
            evidence=evidence,
        )
    return None


def enrich_opportunity_customer_type(
    opportunity: dict[str, Any],
    *,
    institution_name: str | None = None,
    path: Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    """Fill customer_type only from exact VERIFIED institution evidence.

    Existing validated customer_type values are preserved. Fuzzy matching, title
    inference, and LLM guesses are deliberately excluded from this layer.
    """

    result = copy.deepcopy(opportunity)
    current_type = result.get("customer_type")
    current_validation = result.get("customer_type_validation_status")
    if current_type not in {None, "", "UNKNOWN"} and current_validation == "VALIDATED":
        return result

    name = institution_name or result.get("hospital_name") or result.get("buyer_name")
    evidence = resolve_institution_evidence(str(name or ""), path=path)
    if evidence is None:
        result["customer_type"] = "UNKNOWN"
        result["customer_type_provenance"] = "UNRESOLVED"
        result["customer_type_validation_status"] = "UNVERIFIED"
        result["institution_evidence_id"] = None
        return result

    result["customer_type"] = evidence.match_customer_type
    result["customer_type_provenance"] = "OFFICIAL_INSTITUTION_EVIDENCE"
    result["customer_type_validation_status"] = "VALIDATED"
    result["institution_evidence_id"] = evidence.institution_id
    return result
