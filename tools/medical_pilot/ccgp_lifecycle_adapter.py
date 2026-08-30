from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .adapters import CcgpAdapter, _notice_type_from_title
from .collector_core import (
    ParsedNotice,
    Snapshot,
    build_event_and_facts,
    deterministic_id,
    extract_table_rows,
    normalize_space,
    parse_money_to_cny,
    strip_tags,
)


@dataclass(frozen=True)
class AwardPackage:
    package_name: str | None
    supplier_name: str
    award_amount_cny: str | None


@dataclass(frozen=True)
class ParsedCcgpLifecycleNotice(ParsedNotice):
    page_title: str = ""
    termination_reason: str | None = None
    amendment_subject: str | None = None
    amendment_summary: str | None = None
    award_total_cny: str | None = None
    award_packages: tuple[AwardPackage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CcgpLifecycleAdapter(CcgpAdapter):
    def parse_notice(self, snapshot: Snapshot) -> ParsedCcgpLifecycleNotice:
        base = super().parse_notice(snapshot)
        text = strip_tags(snapshot.text)
        page_title = self._extract_page_title(snapshot.text, text)
        notice_type = _notice_type_from_title(page_title)

        termination_reason = self._extract_termination_reason(text) if notice_type == "TERMINATION" else None
        amendment_subject, amendment_summary = (
            self._extract_amendment(text) if notice_type == "AMENDMENT" else (None, None)
        )
        award_total_raw = self._extract_award_total_raw(snapshot.text, text) if notice_type == "AWARD" else None
        award_total_cny = parse_money_to_cny(award_total_raw)
        award_packages = self._extract_award_packages(snapshot.text) if notice_type == "AWARD" else ()
        award_information_fragment = (
            self._extract_award_information_fragment(text) if notice_type == "AWARD" else None
        )

        evidence = dict(base.evidence_fragments)
        if page_title:
            evidence["notice_type"] = page_title
        if termination_reason:
            evidence["termination_reason"] = termination_reason
        if amendment_subject:
            evidence["amendment_subject"] = amendment_subject
        if amendment_summary:
            evidence["amendment_summary"] = amendment_summary
        if award_total_raw:
            evidence["award_total_cny"] = award_total_raw
        if award_packages and award_information_fragment:
            evidence["award_packages"] = award_information_fragment

        return ParsedCcgpLifecycleNotice(
            source_id=base.source_id,
            source_url=base.source_url,
            source_authority=base.source_authority,
            notice_type=notice_type,
            project_name=base.project_name,
            buyer_name=base.buyer_name,
            published_at=base.published_at,
            project_number=base.project_number,
            budget_cny=base.budget_cny,
            registration_deadline=base.registration_deadline,
            bid_deadline=base.bid_deadline,
            procurement_method=base.procurement_method,
            product_items=base.product_items,
            evidence_fragments=evidence,
            verification_reason=base.verification_reason,
            page_title=page_title,
            termination_reason=termination_reason,
            amendment_subject=amendment_subject,
            amendment_summary=amendment_summary,
            award_total_cny=award_total_cny,
            award_packages=award_packages,
        )

    @staticmethod
    def _extract_page_title(raw_html: str, text: str) -> str:
        for pattern in (
            r"<h[1-3][^>]*>(.*?)</h[1-3]>",
            r"<title[^>]*>(.*?)</title>",
        ):
            match = re.search(pattern, raw_html, re.I | re.S)
            if match:
                value = normalize_space(re.sub(r"<[^>]+>", "", match.group(1)))
                if value:
                    return value
        for line in text.splitlines():
            line = normalize_space(line)
            if any(marker in line for marker in ("终止公告", "更正公告", "中标公告", "成交公告", "公开招标公告")):
                return line
        return ""

    @staticmethod
    def _extract_termination_reason(text: str) -> str | None:
        match = re.search(
            r"(?:项目终止的原因|终止的原因)\s*[:：]?\s*(.*?)(?=\n\s*(?:三[、.]|三、|其他补充事宜|四[、.]|四、)|$)",
            text,
            re.S,
        )
        if not match:
            return None
        value = normalize_space(match.group(1))
        return value[:1000] if value else None

    @staticmethod
    def _extract_amendment(text: str) -> tuple[str | None, str | None]:
        subject = None
        subject_match = re.search(r"更正事项\s*[:：]\s*([^\n]+)", text)
        if subject_match:
            subject = normalize_space(subject_match.group(1))
        summary_match = re.search(
            r"更正内容\s*[:：]?\s*(.*?)(?=\n\s*(?:更正日期|三[、.]|三、|其他补充事宜)|$)",
            text,
            re.S,
        )
        summary = normalize_space(summary_match.group(1)) if summary_match else None
        if summary and len(summary) > 4000:
            summary = summary[:4000]
        return subject, summary

    @staticmethod
    def _extract_award_total_raw(raw_html: str, text: str) -> str | None:
        rows = extract_table_rows(raw_html)
        for row in rows:
            for index, cell in enumerate(row[:-1]):
                label = normalize_space(cell).replace(" ", "")
                if label in {"总中标金额", "总成交金额"}:
                    return normalize_space(row[index + 1])
        match = re.search(r"总(?:中标|成交)金额\s*[:：]?\s*([^\n]+)", text)
        return normalize_space(match.group(1)) if match else None

    @staticmethod
    def _extract_award_information_fragment(text: str) -> str | None:
        match = re.search(
            r"(?:三[、.]|三、)\s*(?:中标|成交)信息\s*(.*?)(?=\n\s*(?:四[、.]|四、)|$)",
            text,
            re.S,
        )
        if not match:
            return None
        fragment = normalize_space(match.group(0))
        return fragment[:8000] if fragment else None

    @staticmethod
    def _extract_award_packages(raw_html: str) -> tuple[AwardPackage, ...]:
        rows = extract_table_rows(raw_html)
        packages: list[AwardPackage] = []
        package_name: str | None = None
        supplier_col: int | None = None
        amount_col: int | None = None

        for row in rows:
            normalized = [normalize_space(cell) for cell in row]
            joined = " ".join(normalized)
            package_match = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*包", joined)
            if package_match and len(normalized) <= 3:
                package_name = f"第{package_match.group(1)}包"
            if "供应商名称" in normalized:
                supplier_col = normalized.index("供应商名称")
                amount_col = None
                for index, cell in enumerate(normalized):
                    if "中标金额" in cell or "成交金额" in cell:
                        amount_col = index
                        break
                continue
            if supplier_col is None or supplier_col >= len(normalized):
                continue
            supplier_name = normalized[supplier_col]
            if not supplier_name or supplier_name in {"供应商名称", "排序"}:
                continue
            if not any(token in supplier_name for token in ("公司", "集团", "医院", "中心", "研究院", "厂")):
                continue
            raw_amount = normalized[amount_col] if amount_col is not None and amount_col < len(normalized) else None
            if raw_amount and not re.search(r"元|万元|亿元", raw_amount):
                raw_amount = f"{raw_amount}万元"
            amount = parse_money_to_cny(raw_amount)
            packages.append(AwardPackage(package_name=package_name, supplier_name=supplier_name, award_amount_cny=amount))
            supplier_col = None
            amount_col = None
        return tuple(packages)


def build_ccgp_lifecycle_event_and_facts(
    notice: ParsedCcgpLifecycleNotice, snapshot: Snapshot
) -> tuple[dict, list[dict]]:
    event, facts = build_event_and_facts(notice, snapshot)
    opportunity_id = deterministic_id("opp", f"opportunity|{event['canonical_project_id']}")
    extra_values = (
        ("notice_type", notice.notice_type),
        ("termination_reason", notice.termination_reason),
        ("amendment_subject", notice.amendment_subject),
        ("amendment_summary", notice.amendment_summary),
        ("award_total_cny", notice.award_total_cny),
        ("award_packages", [
            {"package_name": item.package_name, "supplier_name": item.supplier_name, "award_amount_cny": item.award_amount_cny}
            for item in notice.award_packages
        ] if notice.award_packages else None),
    )
    for field_name, field_value in extra_values:
        if field_value is None:
            continue
        fragment = notice.evidence_fragments.get(field_name)
        if not fragment:
            continue
        fact_id = deterministic_id("fact", f"{event['event_id']}|{field_name}|{field_value}")
        facts.append({
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
            "parser_version": "ccgp-lifecycle-v0.1",
            "evidence_locator": {"kind": "HTML_TEXT", "selector": None, "page": None, "table": None, "paragraph": None, "sheet": None, "range": None, "text_hash": hashlib.sha256(fragment.encode("utf-8")).hexdigest()},
            "verification_status": event["verification_status"],
            "verification_reason": notice.verification_reason,
            "verified_at": snapshot.fetched_at if event["verification_status"] == "VERIFIED" else None,
            "superseded_by_fact_id": None,
            "model_generated": False,
            "model_id": None,
        })
    return event, facts
