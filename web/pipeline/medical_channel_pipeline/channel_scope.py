from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

_SCOPE_PATH = Path(__file__).resolve().parents[1] / "data" / "medical_channel_scope.json"
_SCOPE = json.loads(_SCOPE_PATH.read_text(encoding="utf-8"))
_TERMS = tuple(str(item).casefold() for item in _SCOPE.get("terms", []) if str(item).strip())
_ACRONYMS = tuple(str(item).strip() for item in _SCOPE.get("acronyms", []) if str(item).strip())
_ACRONYM_RE = (
    re.compile(
        r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(item) for item in _ACRONYMS) + r")(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    if _ACRONYMS
    else None
)
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

    # Deliberately exclude buyer_name/hospital_name. A hospital buyer alone does
    # not make security, training, finance or other administrative procurement a
    # MedicalChannelAI opportunity.
    return "\n".join(values)


def is_medical_channel_relevant_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    folded = text.casefold()
    if any(term in folded for term in _TERMS):
        return True
    return bool(_ACRONYM_RE and _ACRONYM_RE.search(text))


def is_medical_channel_relevant_record(record: dict[str, Any]) -> bool:
    facts = record.get("facts") if isinstance(record, dict) else None
    if not isinstance(facts, dict):
        return False
    return is_medical_channel_relevant_text(_scope_text_from_facts(facts))


def is_medical_channel_relevant_public_card(card: dict[str, Any]) -> bool:
    facts = card.get("facts") if isinstance(card, dict) else None
    if not isinstance(facts, dict):
        return False
    return is_medical_channel_relevant_text(_scope_text_from_facts(facts))


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
