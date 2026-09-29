"""成交价参考 — brand × model × unit price evidence from official award notices.

Every row is one 标的 line of a published 中标/成交 notice that carries a
single brand and a parseable unit price; multi-valued cells (``卡尔史托斯；
其他详见附件``) are not attributable to one product and are skipped. Rows are
newest first, bounded, and grouped by the coarse device family so the client
can relate them to an opportunity's 标的. No inference is made: no averages,
no "market price", no win-probability — just the published lines with their
official source URL.
"""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .ccgp_award import effective_award_records
from .device_families import device_families_payload, device_family_for_name, load_device_families

MAX_REFERENCE_ROWS = 200
REFERENCE_LOOKBACK_DAYS = 365
_TEXT_LIMITS = {"name": 48, "brand": 24, "model": 48, "quantity": 16, "buyer_name": 48}
# A cell that lists several products/brands cannot be attributed to one price.
_MULTI_VALUE_RE = re.compile(r"[;；]|其他详见附件|详见附件|等$")
# Brand/model cells additionally use 、 as a list separator (``上海菲曼特、康钛、啄木鸟``).
_MULTI_BRAND_RE = re.compile(r"[;；、]|其他详见附件|详见附件|等$")


def _text(value: Any, key: str) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return None
    limit = _TEXT_LIMITS[key]
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _is_single_valued(name: Any, brand: Any, model: Any) -> bool:
    if _MULTI_VALUE_RE.search(str(name or "")):
        return False
    if _MULTI_BRAND_RE.search(str(brand or "")):
        return False
    return not _MULTI_VALUE_RE.search(str(model or ""))


def award_price_reference_rows(
    award_records: list[dict[str, Any]] | None,
    as_of: datetime,
    *,
    lookback_days: int = REFERENCE_LOOKBACK_DAYS,
) -> list[dict[str, Any]]:
    """All attributable priced lines of effective awards, newest first (unbounded)."""
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    families = load_device_families()
    floor = as_of.date() - timedelta(days=max(0, int(lookback_days)))
    rows: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str, str, str, int], dict[str, Any]] = {}
    for record in effective_award_records(award_records, as_of):
        facts = record["facts"]
        try:
            published = date.fromisoformat(str(facts.get("published_at")))
        except (TypeError, ValueError):
            continue
        if published < floor:
            continue
        market_code = str(facts.get("market_code") or "TJ").strip().upper()
        for item in facts.get("items") or []:
            price = item.get("unit_price_cny")
            if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
                continue
            name = _text(item.get("name"), "name")
            brand = _text(item.get("brand"), "brand")
            if not name or not brand or not _is_single_valued(item.get("name"), item.get("brand"), item.get("model")):
                continue
            row = {
                "award_id": record["award_id"],
                "market_code": market_code,
                "published_at": facts.get("published_at"),
                "buyer_name": _text(facts.get("buyer_name"), "buyer_name"),
                "project_number": facts.get("project_number"),
                "family": device_family_for_name(item.get("name"), families),
                "name": name,
                "brand": brand,
                "model": _text(item.get("model"), "model"),
                "quantity": _text(item.get("quantity"), "quantity"),
                "unit_price_cny": price,
                # Identical lines of one notice (黑龙江 lists ``1.00(台)`` per 品目号
                # three times for three units) are folded into one row.
                "line_count": 1,
                "source_url": record["source"]["url"],
            }
            key = _row_key(row)
            existing = by_key.get(key)
            if existing is not None:
                existing["line_count"] += 1
                continue
            by_key[key] = row
            rows.append(row)
    return rows


def _family_row_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("family") or "OTHER")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_award_price_reference(
    award_records: list[dict[str, Any]] | None,
    as_of: datetime,
    *,
    max_rows: int = MAX_REFERENCE_ROWS,
    lookback_days: int = REFERENCE_LOOKBACK_DAYS,
) -> dict[str, Any]:
    rows = award_price_reference_rows(award_records, as_of, lookback_days=lookback_days)
    bounded = rows[: max(0, int(max_rows))]
    return {
        "schema_version": "0.1",
        "lookback_days": int(lookback_days),
        "max_rows": int(max_rows),
        "row_count": len(bounded),
        "truncated": len(rows) > len(bounded),
        "family_row_counts": _family_row_counts(bounded),
        "families": device_families_payload(),
        "rows": bounded,
    }


def _row_key(row: dict[str, Any]) -> tuple[str, str, str, str, int]:
    return (
        str(row.get("award_id") or ""),
        str(row.get("name") or ""),
        str(row.get("brand") or ""),
        str(row.get("model") or ""),
        int(row.get("unit_price_cny") or 0),
    )


def combine_award_price_references(*references: dict[str, Any] | None, max_rows: int = MAX_REFERENCE_ROWS) -> dict[str, Any]:
    """Union of per-market references (publisher): unique rows, newest first, bounded."""
    present = [item for item in references if isinstance(item, dict)]
    seen: set[tuple[str, str, str, str, int]] = set()
    rows: list[dict[str, Any]] = []
    for reference in present:
        for row in reference.get("rows") or []:
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(deepcopy(row))
    rows.sort(key=lambda row: (str(row.get("published_at") or ""), str(row.get("award_id") or "")), reverse=True)
    bounded = rows[: max(0, int(max_rows))]
    lookback = max([int(item.get("lookback_days") or 0) for item in present] or [REFERENCE_LOOKBACK_DAYS])
    families = next((item["families"] for item in present if item.get("families")), device_families_payload())
    return {
        "schema_version": "0.1",
        "lookback_days": lookback,
        "max_rows": int(max_rows),
        "row_count": len(bounded),
        "truncated": len(rows) > len(bounded) or any(bool(item.get("truncated")) for item in present),
        "family_row_counts": _family_row_counts(bounded),
        "families": deepcopy(families),
        "rows": bounded,
    }
