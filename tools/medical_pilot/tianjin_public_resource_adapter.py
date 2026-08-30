from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .adapters import MEDICAL_HINTS, _extract_project_number, _notice_type_from_title
from .ccgp_lifecycle_adapter import (
    CcgpLifecycleAdapter,
    ParsedCcgpLifecycleNotice,
)
from .collector_core import (
    DiscoveredLink,
    Snapshot,
    extract_anchors,
    normalize_space,
    parse_cn_datetime,
    parse_money_to_cny,
    strip_tags,
)


@dataclass(frozen=True)
class TianjinPublicResourceAdapter(CcgpLifecycleAdapter):
    """Tianjin Public Resource Exchange government-procurement mirror adapter.

    Pilot v0.1 intentionally supports only verified procurement result detail pages
    under /jyxxcgjg/. Other government-procurement notice categories remain outside
    the declared coverage until their live URL structures are independently checked.
    """

    source_id: str = "tj_public_resource_exchange"
    base_url: str = "https://ggzy.zwfwb.tj.gov.cn/"

    @property
    def allowed_hosts(self) -> set[str]:
        return {"ggzy.zwfwb.tj.gov.cn"}

    def discover(self, listing_html: str, listing_url: str) -> list[DiscoveredLink]:
        result: list[DiscoveredLink] = []
        for link in extract_anchors(listing_html, listing_url):
            parsed = urlparse(link.url)
            if parsed.hostname not in self.allowed_hosts:
                continue
            if not re.fullmatch(r"/jyxxcgjg/[^/]+\.jhtml", parsed.path):
                continue
            if not any(hint in link.title for hint in MEDICAL_HINTS):
                continue
            result.append(link)
        return result

    def parse_notice(self, snapshot: Snapshot) -> ParsedCcgpLifecycleNotice:
        text = strip_tags(snapshot.text)
        page_title = self._extract_page_title(snapshot.text, text)
        notice_type = _notice_type_from_title(page_title)

        project_number = _extract_project_number(text, page_title)
        project_name = self._extract_project_name(text, page_title)
        buyer_name = self._extract_buyer_name(text)
        published_raw = self._extract_published_raw(text)
        published_at = parse_cn_datetime(published_raw)

        budget_raw = self._extract_budget_raw(text)
        budget_cny = parse_money_to_cny(budget_raw)

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

        normalized_text = normalize_space(text)
        evidence: dict[str, str] = {}
        for field_name, raw in (
            ("project_name", project_name),
            ("buyer_name", buyer_name),
            ("published_at", published_raw),
            ("project_number", project_number),
            ("budget_cny", budget_raw),
        ):
            if raw and normalize_space(raw) in normalized_text:
                evidence[field_name] = normalize_space(raw)
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

        missing = [
            name
            for name, value in (
                ("project_name", project_name),
                ("buyer_name", buyer_name),
                ("published_at", published_at),
            )
            if not value
        ]
        reason = "missing required Tianjin public-resource fields: " + ", ".join(missing) if missing else None

        return ParsedCcgpLifecycleNotice(
            source_id=self.source_id,
            source_url=snapshot.source_url,
            source_authority="OFFICIAL_GOVERNMENT",
            notice_type=notice_type,
            project_name=project_name,
            buyer_name=buyer_name,
            published_at=published_at or "",
            published_at_precision="DAY",
            project_number=project_number,
            budget_cny=budget_cny,
            registration_deadline=None,
            bid_deadline=None,
            procurement_method=None,
            product_items=(),
            evidence_fragments=evidence,
            verification_reason=reason,
            page_title=page_title,
            termination_reason=termination_reason,
            amendment_subject=amendment_subject,
            amendment_summary=amendment_summary,
            award_total_cny=award_total_cny,
            award_packages=award_packages,
        )

    @staticmethod
    def _extract_project_name(text: str, title: str) -> str:
        patterns = (
            r"(?:二[、.]|二、)\s*项目名称\s*[:：]\s*([^\n]+)",
            r"项目名称\s*[:：]\s*([^\n]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return normalize_space(match.group(1))
        cleaned = re.sub(r"\s*\(项目编号[:：][^\)）]+[\)）].*$", "", title)
        cleaned = re.sub(r"(中标公告|成交公告|终止公告|更正公告|公开招标公告)$", "", cleaned)
        return normalize_space(cleaned)

    @staticmethod
    def _extract_buyer_name(text: str) -> str:
        patterns = (
            r"采购人信息\s*.*?名称\s*[:：]\s*([^\n]+)",
            r"发布来源\s*[:：]\s*([^\n]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.S)
            if match:
                value = normalize_space(match.group(1))
                value = re.split(r"\s+(?:地址|联系方式|发布日期)\s*[:：]", value)[0]
                if value:
                    return value
        return ""

    @staticmethod
    def _extract_published_raw(text: str) -> str | None:
        patterns = (
            r"发布日期\s*[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日)",
            r"(?m)^\s*(20\d{2}\.\d{1,2}\.\d{1,2})\s+信息来源",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return normalize_space(match.group(1))
        return None

    @staticmethod
    def _extract_budget_raw(text: str) -> str | None:
        match = re.search(r"预算金额\s*[:：]\s*([^\n]+)", text)
        return normalize_space(match.group(1)) if match else None
