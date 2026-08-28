from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .collector_core import (
    Snapshot,
    deterministic_id,
    extract_table_rows,
    normalize_space,
    parse_money_to_cny,
    strip_tags,
)


@dataclass(frozen=True)
class OfficialAwardItem:
    package_name: str | None
    item_type: str | None
    raw_name: str
    brand: str | None
    model: str | None
    quantity: str | None
    unit_price_cny: str | None


_HEADER_ALIASES = {
    "item_type": ("类型", "品目类型"),
    "raw_name": ("名称", "货物名称", "标的名称", "产品名称"),
    "brand": ("品牌", "品牌名称"),
    "model": ("规格型号", "型号", "规格"),
    "quantity": ("数量",),
}


def _header_index(row: list[str], aliases: tuple[str, ...]) -> int | None:
    normalized = [normalize_space(cell).replace(" ", "") for cell in row]
    for alias in aliases:
        compact = alias.replace(" ", "")
        for index, cell in enumerate(normalized):
            if cell == compact:
                return index
    return None


def _unit_price_index(row: list[str]) -> tuple[int | None, str | None]:
    for index, cell in enumerate(row):
        compact = normalize_space(cell).replace(" ", "")
        if "单价" not in compact:
            continue
        if "万元" in compact:
            return index, "万元"
        if "亿元" in compact:
            return index, "亿元"
        return index, "元"
    return None, None


def extract_main_award_information_fragment(raw_html: str) -> str | None:
    text = strip_tags(raw_html)
    match = re.search(
        r"(?:四[、.]|四、)\s*主要标的信息\s*(.*?)(?=\n\s*(?:五[、.]|五、)\s*评审专家|$)",
        text,
        re.S,
    )
    if not match:
        return None
    fragment = normalize_space(match.group(0))
    return fragment[:12000] if fragment else None


def extract_official_award_items(raw_html: str) -> tuple[OfficialAwardItem, ...]:
    rows = extract_table_rows(raw_html)
    items: list[OfficialAwardItem] = []
    package_name: str | None = None
    header: dict[str, int | None] | None = None
    unit_price_unit: str | None = None

    for row in rows:
        normalized = [normalize_space(cell) for cell in row]
        joined = " ".join(normalized)

        package_match = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*包", joined)
        if package_match and len(normalized) <= 3:
            package_name = f"第{package_match.group(1)}包"

        name_index = _header_index(normalized, _HEADER_ALIASES["raw_name"])
        brand_index = _header_index(normalized, _HEADER_ALIASES["brand"])
        model_index = _header_index(normalized, _HEADER_ALIASES["model"])
        quantity_index = _header_index(normalized, _HEADER_ALIASES["quantity"])
        price_index, price_unit = _unit_price_index(normalized)

        recognized_optional = sum(
            index is not None
            for index in (brand_index, model_index, quantity_index, price_index)
        )
        if name_index is not None and recognized_optional >= 2:
            header = {
                "item_type": _header_index(normalized, _HEADER_ALIASES["item_type"]),
                "raw_name": name_index,
                "brand": brand_index,
                "model": model_index,
                "quantity": quantity_index,
                "unit_price": price_index,
            }
            unit_price_unit = price_unit
            continue

        if header is None:
            continue

        name_col = header["raw_name"]
        if name_col is None or name_col >= len(normalized):
            header = None
            continue
        raw_name = normalize_space(normalized[name_col])
        if not raw_name or raw_name in _HEADER_ALIASES["raw_name"]:
            continue

        def cell(key: str) -> str | None:
            index = header.get(key)
            if index is None or index >= len(normalized):
                return None
            value = normalize_space(normalized[index])
            return value or None

        unit_price_raw = cell("unit_price")
        unit_price_cny = None
        if unit_price_raw:
            if not re.search(r"元|万元|亿元", unit_price_raw):
                unit_price_raw = f"{unit_price_raw}{unit_price_unit or '元'}"
            unit_price_cny = parse_money_to_cny(unit_price_raw)

        items.append(
            OfficialAwardItem(
                package_name=package_name,
                item_type=cell("item_type"),
                raw_name=raw_name,
                brand=cell("brand"),
                model=cell("model"),
                quantity=cell("quantity"),
                unit_price_cny=unit_price_cny,
            )
        )

    seen: set[OfficialAwardItem] = set()
    unique: list[OfficialAwardItem] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return tuple(unique)


def build_award_items_fact(
    *,
    event: dict,
    snapshot: Snapshot,
    source_id: str,
    source_url: str,
    published_at: str,
    items: tuple[OfficialAwardItem, ...],
) -> dict | None:
    if not items:
        return None
    fragment = extract_main_award_information_fragment(snapshot.text)
    if not fragment:
        return None

    value = [
        {
            "package_name": item.package_name,
            "item_type": item.item_type,
            "raw_name": item.raw_name,
            "brand": item.brand,
            "model": item.model,
            "quantity": item.quantity,
            "unit_price_cny": item.unit_price_cny,
        }
        for item in items
    ]
    opportunity_id = deterministic_id("opp", f"opportunity|{event['canonical_project_id']}")
    fact_id = deterministic_id("fact", f"{event['event_id']}|award_items|{value}")
    verification_status = event.get("verification_status", "UNVERIFIED")
    return {
        "schema_version": "0.1",
        "fact_id": fact_id,
        "opportunity_id": opportunity_id,
        "event_id": event["event_id"],
        "field_name": "award_items",
        "field_value": value,
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "source_id": source_id,
        "source_url": source_url,
        "published_at": published_at,
        "fetched_at": snapshot.fetched_at,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_sha256": snapshot.sha256,
        "parser_version": "ccgp-award-items-v0.1",
        "evidence_locator": {
            "kind": "HTML_TEXT",
            "selector": None,
            "page": None,
            "table": None,
            "paragraph": None,
            "sheet": None,
            "range": None,
            "text_hash": hashlib.sha256(fragment.encode("utf-8")).hexdigest(),
        },
        "verification_status": verification_status,
        "verification_reason": None,
        "verified_at": snapshot.fetched_at if verification_status == "VERIFIED" else None,
        "superseded_by_fact_id": None,
        "model_generated": False,
        "model_id": None,
    }
