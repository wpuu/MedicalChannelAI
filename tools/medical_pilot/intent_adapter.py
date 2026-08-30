from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .adapters import MEDICAL_HINTS
from .collector_core import (
    DiscoveredLink,
    ParsedNotice,
    Snapshot,
    build_event_and_facts,
    deterministic_id,
    extract_anchors,
    extract_table_rows,
    normalize_space,
    parse_cn_datetime,
    parse_money_to_cny,
    strip_tags,
    table_pairs,
)


PROJ_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _intent_proj_id(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    if parsed.hostname != "cgyx.ccgp.gov.cn" or parsed.path != "/cgyx/pub/proJ/details":
        return None
    values = parse_qs(parsed.query).get("projId", [])
    if len(values) != 1:
        return None
    value = values[0].strip()
    return value.lower() if PROJ_ID_PATTERN.fullmatch(value) else None


@dataclass(frozen=True)
class ParsedIntentNotice(ParsedNotice):
    expected_procurement_at: str | None = None
    procurement_need: str | None = None
    native_record_id: str | None = None

    @property
    def eligible_for_verified(self) -> bool:
        # Procurement-intent titles are not unique. An exact official projId is
        # required before the record may participate in deterministic identity.
        return bool(self.native_record_id) and super().eligible_for_verified


@dataclass(frozen=True)
class CcgpIntentAdapter:
    source_id: str = "ccgp_procurement_intent"
    base_url: str = "https://cgyx.ccgp.gov.cn/"

    @property
    def allowed_hosts(self) -> set[str]:
        return {"cgyx.ccgp.gov.cn"}

    def discover(self, listing_html: str, listing_url: str) -> list[DiscoveredLink]:
        result: list[DiscoveredLink] = []
        for link in extract_anchors(listing_html, listing_url):
            parsed = urlparse(link.url)
            if parsed.hostname not in self.allowed_hosts:
                continue
            if _intent_proj_id(link.url) is None:
                continue
            if not any(hint in link.title for hint in MEDICAL_HINTS):
                continue
            result.append(link)
        return result

    def parse_notice(self, snapshot: Snapshot) -> ParsedIntentNotice:
        text = strip_tags(snapshot.text)
        pairs = table_pairs(extract_table_rows(snapshot.text))
        native_record_id = _intent_proj_id(snapshot.source_url)

        project_name = self._first(pairs, "采购项目名称")
        buyer_name = self._first(pairs, "采购单位")
        budget_raw = self._first(pairs, "预算金额")
        expected_raw = self._first(pairs, "预计采购时间", "预计采购日期")
        need_raw = self._first(pairs, "采购需求概况")

        if not project_name:
            match = re.search(r"采购项目名称\s*[:：]\s*([^\n]+)", text)
            project_name = normalize_space(match.group(1)) if match else ""
        if not buyer_name:
            match = re.search(r"采购单位\s*[:：]\s*([^\n]+)", text)
            buyer_name = normalize_space(match.group(1)) if match else ""
        if not budget_raw:
            match = re.search(r"预算金额\s*[:：]\s*([^\n]+)", text)
            budget_raw = normalize_space(match.group(1)) if match else None
        if not expected_raw:
            match = re.search(r"预计采购(?:时间|日期)\s*[:：]\s*([^\n]+)", text)
            expected_raw = normalize_space(match.group(1)) if match else None
        if not need_raw:
            match = re.search(r"采购需求概况\s*[:：]?\s*(.*?)(?:\n预计采购(?:时间|日期)|\n备注)", text, re.S)
            need_raw = normalize_space(match.group(1)) if match else None

        published_raw = None
        published_match = re.search(r"20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}", text)
        if published_match:
            published_raw = normalize_space(published_match.group(0))
        published_at = parse_cn_datetime(published_raw)

        budget_cny = parse_money_to_cny(budget_raw)
        expected_procurement_at = self._parse_expected_procurement(expected_raw)

        evidence = {}
        normalized_text = normalize_space(text)
        for key, raw in (
            ("project_name", project_name),
            ("buyer_name", buyer_name),
            ("published_at", published_raw),
            ("budget_cny", budget_raw),
            ("expected_procurement_at", expected_raw),
            ("procurement_need", need_raw),
        ):
            if raw and normalize_space(raw) in normalized_text:
                evidence[key] = normalize_space(raw)

        missing = [
            name
            for name, value in (
                ("native_record_id", native_record_id),
                ("project_name", project_name),
                ("buyer_name", buyer_name),
                ("published_at", published_at),
            )
            if not value
        ]
        reason = "missing required procurement-intent fields: " + ", ".join(missing) if missing else None

        return ParsedIntentNotice(
            source_id=self.source_id,
            source_url=snapshot.source_url,
            source_authority="OFFICIAL_GOVERNMENT",
            notice_type="PROCUREMENT_INTENT",
            project_name=project_name,
            buyer_name=buyer_name,
            published_at=published_at or "",
            project_number=None,
            budget_cny=budget_cny,
            registration_deadline=None,
            bid_deadline=None,
            procurement_method="PROCUREMENT_INTENT",
            product_items=(),
            evidence_fragments=evidence,
            verification_reason=reason,
            expected_procurement_at=expected_procurement_at,
            procurement_need=need_raw,
            native_record_id=native_record_id,
        )

    @staticmethod
    def _canonical_label(value: str) -> str:
        return normalize_space(value).rstrip("：:").strip()

    @classmethod
    def _first(cls, mapping: dict[str, str], *keys: str) -> str | None:
        wanted = {cls._canonical_label(key) for key in keys}
        for raw_key, value in mapping.items():
            if cls._canonical_label(raw_key) in wanted and value:
                return normalize_space(value)
        return None

    @staticmethod
    def _parse_expected_procurement(value: str | None) -> str | None:
        if not value:
            return None
        value = normalize_space(value)
        match = re.search(r"(20\d{2})[-年](\d{1,2})(?:月)?", value)
        if not match:
            return None
        year = int(match.group(1))
        month = int(match.group(2))
        if not 1 <= month <= 12:
            return None
        return f"{year:04d}-{month:02d}"


def _rekey_intent_identity(event: dict, facts: list[dict], notice: ParsedIntentNotice) -> str:
    """Use exact official projId to avoid over-merging same-name intentions.

    This intentionally does not auto-link a procurement intent to a later tender.
    Cross-stage linking requires a separate evidence-backed bridge because the
    tender may receive a different project number or scope.
    """

    if not notice.native_record_id:
        return deterministic_id("opp", f"opportunity|{event['canonical_project_id']}")

    canonical_project_id = deterministic_id(
        "mprj",
        f"project|native_record|{notice.source_id}|{notice.native_record_id}",
    )
    opportunity_id = deterministic_id("opp", f"opportunity|{canonical_project_id}")
    event["canonical_project_id"] = canonical_project_id
    event["link_confidence"] = 1.0
    for fact in facts:
        fact["opportunity_id"] = opportunity_id
    return opportunity_id


def build_intent_event_and_facts(
    notice: ParsedIntentNotice, snapshot: Snapshot
) -> tuple[dict, list[dict]]:
    event, facts = build_event_and_facts(notice, snapshot)
    opportunity_id = _rekey_intent_identity(event, facts, notice)

    for field_name, field_value in (
        ("expected_procurement_at", notice.expected_procurement_at),
        ("procurement_need", notice.procurement_need),
    ):
        if field_value is None:
            continue
        fragment = notice.evidence_fragments.get(field_name)
        if not fragment:
            continue
        fact_id = deterministic_id("fact", f"{event['event_id']}|{field_name}|{field_value}")
        facts.append(
            {
                "schema_version": "0.1",
                "fact_id": fact_id,
                "opportunity_id": opportunity_id,
                "event_id": event["event_id"],
                "field_name": field_name,
                "field_value": field_value,
                "fact_type": "OFFICIAL_PUBLIC_FACT",
                "source_id": notice.source_id,
                "source_url": notice.source_url,
                "published_at": notice.published_at,
                "fetched_at": snapshot.fetched_at,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_sha256": snapshot.sha256,
                "parser_version": "ccgp-intent-v0.1",
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
                "verification_status": event["verification_status"],
                "verification_reason": notice.verification_reason,
                "verified_at": snapshot.fetched_at if event["verification_status"] == "VERIFIED" else None,
                "superseded_by_fact_id": None,
                "model_generated": False,
                "model_id": None,
            }
        )
    return event, facts
