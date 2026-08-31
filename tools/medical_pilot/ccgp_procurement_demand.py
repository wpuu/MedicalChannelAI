from __future__ import annotations

import hashlib
import re
from typing import Any

from .collector_core import Snapshot, deterministic_id, extract_table_rows, normalize_space


PARSER_VERSION = "ccgp-procurement-demand-v0.1"
MAX_DEMAND_CELL_CHARS = 4000
_PACKAGE_RE = re.compile(r"^(?:第\s*)?(?:\d+|[一二三四五六七八九十]+)(?:\s*包)?$")


def extract_ccgp_procurement_demand(raw_html: str) -> tuple[str, ...]:
    """Extract only package-level cells under an explicit CCGP `采购需求` header.

    The extractor is intentionally table-structural and fail-closed. It does not scan
    arbitrary body text for product terms, so qualification/policy/contact wording is
    never promoted into product evidence merely because it mentions medical devices.
    """

    rows = [[normalize_space(cell) for cell in row] for row in extract_table_rows(raw_html)]
    result: list[str] = []
    seen: set[str] = set()

    for header_index, header in enumerate(rows):
        if "采购需求" not in header or "包号" not in header:
            continue
        demand_col = header.index("采购需求")
        package_col = header.index("包号")
        required_col = max(demand_col, package_col)

        for row in rows[header_index + 1 :]:
            # A later procurement-demand table starts a new bounded region and will be
            # processed independently by the outer loop.
            if "采购需求" in row and "包号" in row:
                break
            if len(row) <= required_col:
                continue
            package_value = normalize_space(row[package_col])
            if not _PACKAGE_RE.fullmatch(package_value):
                continue
            demand = normalize_space(row[demand_col])
            if not demand or demand == "采购需求" or len(demand) > MAX_DEMAND_CELL_CHARS:
                continue
            if demand in seen:
                continue
            seen.add(demand)
            result.append(demand)

    return tuple(result)


def build_ccgp_procurement_demand_facts(
    *,
    event: dict[str, Any],
    snapshot: Snapshot,
    source_id: str,
    source_url: str,
    published_at: str,
    verification_reason: str | None,
) -> list[dict[str, Any]]:
    items = extract_ccgp_procurement_demand(snapshot.text)
    if not items:
        return []

    event_id = event.get("event_id")
    canonical_project_id = event.get("canonical_project_id")
    verification_status = event.get("verification_status")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id is required for procurement-demand facts")
    if not isinstance(canonical_project_id, str) or not canonical_project_id:
        raise ValueError("canonical_project_id is required for procurement-demand facts")
    if verification_status not in {"VERIFIED", "UNVERIFIED"}:
        raise ValueError("unsupported event verification status")

    opportunity_id = deterministic_id("opp", f"opportunity|{canonical_project_id}")
    facts: list[dict[str, Any]] = []
    for item in items:
        fact_id = deterministic_id("fact", f"{event_id}|product_item|{item}")
        facts.append(
            {
                "schema_version": "0.1",
                "fact_id": fact_id,
                "opportunity_id": opportunity_id,
                "event_id": event_id,
                "field_name": "product_item",
                "field_value": item,
                "fact_type": "OFFICIAL_PUBLIC_FACT",
                "source_id": source_id,
                "source_url": source_url,
                "published_at": published_at,
                "fetched_at": snapshot.fetched_at,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_sha256": snapshot.sha256,
                "parser_version": PARSER_VERSION,
                "evidence_locator": {
                    "kind": "HTML_TEXT",
                    "selector": None,
                    "page": None,
                    "table": None,
                    "paragraph": None,
                    "sheet": None,
                    "range": None,
                    "text_hash": hashlib.sha256(item.encode("utf-8")).hexdigest(),
                },
                "verification_status": verification_status,
                "verification_reason": verification_reason,
                "verified_at": snapshot.fetched_at if verification_status == "VERIFIED" else None,
                "superseded_by_fact_id": None,
                "model_generated": False,
                "model_id": None,
            }
        )
    return facts
