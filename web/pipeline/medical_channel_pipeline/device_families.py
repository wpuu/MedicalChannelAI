"""Coarse medical-device families for grouping award line items.

The taxonomy lives in ``data/device_families.json`` (ordered; first match
wins) and is shipped inside the public snapshot so the web client classifies
opportunity 标的 with exactly the same table (``web/src/utils/deviceFamily.ts``
mirrors :func:`device_family_for_name`). Classification is a display aid for
"成交价参考" only — it never feeds scope, ranking or actionability.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DEVICE_FAMILIES_PATH = Path(__file__).resolve().parents[1] / "data" / "device_families.json"

_FULLWIDTH_ASCII = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}
_FULLWIDTH_ASCII[0x3000] = 0x20


def normalize_device_name(value: Any) -> str:
    """Full-width → ASCII, upper-case, whitespace collapsed to single spaces."""
    text = str(value or "").translate(_FULLWIDTH_ASCII).upper()
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def load_device_families(path: Path = DEVICE_FAMILIES_PATH) -> tuple[dict[str, Any], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    families = payload.get("families")
    if not isinstance(families, list) or not families:
        raise ValueError("DEVICE_FAMILIES_INVALID")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for family in families:
        code = str(family.get("code") or "").strip()
        label = str(family.get("label") or "").strip()
        if not code or not label or code in seen:
            raise ValueError(f"DEVICE_FAMILY_INVALID:{code or '?'}")
        seen.add(code)
        keywords = [normalize_device_name(item) for item in family.get("keywords") or [] if str(item).strip()]
        acronyms = [normalize_device_name(item) for item in family.get("acronyms") or [] if str(item).strip()]
        normalized.append({"code": code, "label": label, "keywords": keywords, "acronyms": acronyms})
    return tuple(normalized)


def load_device_family_parity_vectors(path: Path = DEVICE_FAMILIES_PATH) -> list[tuple[str, str | None]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [(str(name), code) for name, code in payload.get("parity_vectors") or []]


def _acronym_present(name: str, acronym: str) -> bool:
    # Whole Latin/digit token: ``CT`` must not match inside ``CBCT``; ``MR`` not inside ``MRI``.
    pattern = r"(?<![A-Z0-9])" + re.escape(acronym) + r"(?![A-Z0-9])"
    return re.search(pattern, name) is not None


def device_family_for_name(value: Any, families: tuple[dict[str, Any], ...] | None = None) -> str | None:
    """First family whose keyword is contained in the name or whose acronym
    appears as a whole token; ``None`` when nothing matches."""
    name = normalize_device_name(value)
    if not name:
        return None
    for family in families or load_device_families():
        if any(keyword and keyword in name for keyword in family["keywords"]):
            return family["code"]
        if any(acronym and _acronym_present(name, acronym) for acronym in family["acronyms"]):
            return family["code"]
    return None


def device_families_payload(families: tuple[dict[str, Any], ...] | None = None) -> list[dict[str, Any]]:
    """Snapshot projection of the taxonomy (what the web client classifies with)."""
    return [
        {
            "code": family["code"],
            "label": family["label"],
            "keywords": list(family["keywords"]),
            "acronyms": list(family["acronyms"]),
        }
        for family in (families or load_device_families())
    ]
