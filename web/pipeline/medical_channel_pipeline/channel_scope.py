from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

_SCOPE_PATH = Path(__file__).resolve().parents[1] / "data" / "medical_channel_scope.json"
_SCOPE = json.loads(_SCOPE_PATH.read_text(encoding="utf-8"))
_TERMS = tuple(str(item).casefold() for item in _SCOPE.get("terms", []) if str(item).strip())
_CONTEXTUAL_TERMS = tuple(
    str(item).casefold() for item in _SCOPE.get("contextual_terms", []) if str(item).strip()
)
_ADJACENT_TECH_TERMS = tuple(
    str(item).casefold() for item in _SCOPE.get("adjacent_tech_terms", []) if str(item).strip()
)
_MEDICAL_CONTEXT_TERMS = tuple(
    str(item).casefold() for item in _SCOPE.get("medical_context_terms", []) if str(item).strip()
)
_GENERIC_EXCLUSIONS = tuple(
    str(item).casefold() for item in _SCOPE.get("generic_exclusion_terms", []) if str(item).strip()
)
_ACRONYMS = tuple(str(item).strip() for item in _SCOPE.get("acronyms", []) if str(item).strip())
_CONTEXTUAL_ACRONYMS = tuple(
    str(item).strip() for item in _SCOPE.get("contextual_acronyms", []) if str(item).strip()
)
_ADJACENT_TECH_ACRONYMS = tuple(
    str(item).strip() for item in _SCOPE.get("adjacent_tech_acronyms", []) if str(item).strip()
)


def _acronym_regex(items: tuple[str, ...]) -> re.Pattern[str] | None:
    if not items:
        return None
    return re.compile(
        r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(item) for item in items) + r")(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


_ACRONYM_RE = _acronym_regex(_ACRONYMS)
_CONTEXTUAL_ACRONYM_RE = _acronym_regex(_CONTEXTUAL_ACRONYMS)
_ADJACENT_TECH_ACRONYM_RE = _acronym_regex(_ADJACENT_TECH_ACRONYMS)
_MAX_TODAY_CARDS = 5


def _scope_text_from_facts(facts: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("project_name", "department"):
        value = facts.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    for value in facts.get("product_categories") or []:
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    for item in facts.get("product_items") or []:
        if not isinstance(item, dict):
            continue
        for key in ("raw_name", "name", "category", "specification"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value.strip())

    return "\n".join(values)


def _context_text_from_facts(facts: dict[str, Any]) -> str:
    values = [_scope_text_from_facts(facts)]
    # Buyer/hospital identity is context only. It cannot independently make a
    # procurement relevant, but it can disambiguate generic terms such as
    # “检验”“实验室”“耗材” when those terms appear in procurement facts.
    for key in ("buyer_name", "hospital_name"):
        value = facts.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return "\n".join(value for value in values if value)


def _has_strong_signal(text: str) -> bool:
    folded = text.casefold()
    if any(term in folded for term in _TERMS):
        return True
    return bool(_ACRONYM_RE and _ACRONYM_RE.search(text))


def _has_contextual_signal(text: str) -> bool:
    folded = text.casefold()
    if any(term in folded for term in _CONTEXTUAL_TERMS):
        return True
    return bool(_CONTEXTUAL_ACRONYM_RE and _CONTEXTUAL_ACRONYM_RE.search(text))


def _has_adjacent_tech_signal(text: str) -> bool:
    folded = text.casefold()
    if any(term in folded for term in _ADJACENT_TECH_TERMS):
        return True
    return bool(_ADJACENT_TECH_ACRONYM_RE and _ADJACENT_TECH_ACRONYM_RE.search(text))


def _has_medical_context(text: str) -> bool:
    folded = text.casefold()
    return any(term in folded for term in _MEDICAL_CONTEXT_TERMS)


def _has_generic_exclusion(text: str) -> bool:
    folded = text.casefold()
    return any(term in folded for term in _GENERIC_EXCLUSIONS)


def is_medical_channel_relevant_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if _has_strong_signal(text):
        return True
    if _has_generic_exclusion(text):
        return False
    if _has_adjacent_tech_signal(text):
        return _has_medical_context(text)
    return _has_contextual_signal(text) and _has_medical_context(text)


def is_medical_channel_relevant_record(record: dict[str, Any]) -> bool:
    facts = record.get("facts") if isinstance(record, dict) else None
    if not isinstance(facts, dict):
        return False
    scope_text = _scope_text_from_facts(facts)
    if _has_strong_signal(scope_text):
        return True
    if _has_generic_exclusion(scope_text):
        return False
    if _has_adjacent_tech_signal(scope_text):
        # Adjacent AI/compute procurement must carry medical context in the
        # procurement facts themselves. Buyer identity alone must not turn a
        # generic “算力/GPU” notice into a medical-channel opportunity.
        return _has_medical_context(scope_text)
    return _has_contextual_signal(scope_text) and _has_medical_context(_context_text_from_facts(facts))


def is_medical_channel_relevant_public_card(card: dict[str, Any]) -> bool:
    return is_medical_channel_relevant_record(card)


def filter_public_snapshot_to_medical_channel(snapshot: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(snapshot)
    pool = result.get("opportunity_pool")
    if isinstance(pool, list):
        scoped_pool = [item for item in pool if is_medical_channel_relevant_public_card(item)]
        for index, item in enumerate(scoped_pool, start=1):
            item["rank"] = index
        cards = scoped_pool[:_MAX_TODAY_CARDS]
        result["opportunity_pool"] = scoped_pool
        result["opportunity_pool_count"] = len(scoped_pool)
        result["matched_count"] = len(scoped_pool)
        result["cards"] = cards
        result["card_count"] = len(cards)
        return result

    cards = result.get("cards")
    if isinstance(cards, list):
        scoped_cards = [item for item in cards if is_medical_channel_relevant_public_card(item)][:_MAX_TODAY_CARDS]
        for index, item in enumerate(scoped_cards, start=1):
            item["rank"] = index
        result["cards"] = scoped_cards
        result["card_count"] = len(scoped_cards)
        result["matched_count"] = len(scoped_cards)
    return result
