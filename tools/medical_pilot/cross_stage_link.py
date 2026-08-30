from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .collector_core import ID_NAMESPACE, SCHEMA_VERSION, normalize_space


ALLOWED_STAGE_PAIRS = {
    ("PROCUREMENT_INTENT", "TENDER"),
    ("MARKET_RESEARCH", "TENDER"),
    ("INTERNAL_SELECTION", "TENDER"),
}


@dataclass(frozen=True)
class LinkableRecord:
    canonical_project_id: str
    event_id: str
    event_type: str
    buyer_name: str
    project_name: str
    published_at: str
    verification_status: str
    source_url: str
    project_number: str | None = None
    native_record_id: str | None = None


@dataclass(frozen=True)
class CrossStageLinkCandidate:
    candidate_id: str
    earlier_canonical_project_id: str
    later_canonical_project_id: str
    earlier_event_id: str
    later_event_id: str
    stage_pair: tuple[str, str]
    reasons: tuple[str, ...]
    confidence: float
    status: str = "CANDIDATE_REQUIRES_EVIDENCE"
    auto_merge_allowed: bool = False

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "earlier_canonical_project_id": self.earlier_canonical_project_id,
            "later_canonical_project_id": self.later_canonical_project_id,
            "earlier_event_id": self.earlier_event_id,
            "later_event_id": self.later_event_id,
            "stage_pair": list(self.stage_pair),
            "reasons": list(self.reasons),
            "confidence": self.confidence,
            "status": self.status,
            "auto_merge_allowed": self.auto_merge_allowed,
        }


def _normalize_title(value: str) -> str:
    # Whitespace and common punctuation normalization only. Do not remove product
    # words, quantities, package identifiers, years or semantic content.
    value = normalize_space(value)
    value = value.replace("（", "(").replace("）", ")").replace("：", ":")
    return re.sub(r"\s+", "", value).lower()


def _normalize_buyer(value: str) -> str:
    return re.sub(r"\s+", "", normalize_space(value)).lower()


def _parse_instant(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def suggest_cross_stage_link(
    earlier: LinkableRecord,
    later: LinkableRecord,
) -> CrossStageLinkCandidate | None:
    if earlier.canonical_project_id == later.canonical_project_id:
        return None
    if earlier.verification_status != "VERIFIED" or later.verification_status != "VERIFIED":
        return None
    stage_pair = (earlier.event_type, later.event_type)
    if stage_pair not in ALLOWED_STAGE_PAIRS:
        return None
    earlier_time = _parse_instant(earlier.published_at)
    later_time = _parse_instant(later.published_at)
    if earlier_time is None or later_time is None or earlier_time > later_time:
        return None
    if _normalize_buyer(earlier.buyer_name) != _normalize_buyer(later.buyer_name):
        return None
    if _normalize_title(earlier.project_name) != _normalize_title(later.project_name):
        return None

    # If both sides already have explicit but different project numbers, do not
    # suggest a bridge. That is conflicting deterministic identity evidence.
    if earlier.project_number and later.project_number and earlier.project_number != later.project_number:
        return None

    reasons = (
        "BOTH_RECORDS_VERIFIED",
        "ALLOWED_STAGE_TRANSITION",
        "EXACT_NORMALIZED_BUYER",
        "EXACT_NORMALIZED_PROJECT_TITLE",
        "FORWARD_PUBLICATION_CHRONOLOGY",
    )
    seed = "|".join(
        [
            earlier.canonical_project_id,
            later.canonical_project_id,
            earlier.event_id,
            later.event_id,
        ]
    )
    candidate_uuid = uuid.uuid5(ID_NAMESPACE, f"cross-stage-link|{seed}")
    return CrossStageLinkCandidate(
        candidate_id=f"linkcand_{candidate_uuid}",
        earlier_canonical_project_id=earlier.canonical_project_id,
        later_canonical_project_id=later.canonical_project_id,
        earlier_event_id=earlier.event_id,
        later_event_id=later.event_id,
        stage_pair=stage_pair,
        reasons=reasons,
        confidence=0.70,
    )


def suggest_cross_stage_links(records: Iterable[LinkableRecord]) -> list[CrossStageLinkCandidate]:
    # Order by parsed instant rather than raw ISO text so Z/+08:00 representations
    # cannot invert chronology. Invalid/naive timestamps sort last and fail closed.
    max_utc = datetime.max.replace(tzinfo=timezone.utc)

    def sort_key(item: LinkableRecord):
        instant = _parse_instant(item.published_at)
        return (instant is None, instant or max_utc, item.event_id)

    items = sorted(records, key=sort_key)
    result: list[CrossStageLinkCandidate] = []
    for left_index, earlier in enumerate(items):
        for later in items[left_index + 1 :]:
            candidate = suggest_cross_stage_link(earlier, later)
            if candidate is not None:
                result.append(candidate)
    return result
