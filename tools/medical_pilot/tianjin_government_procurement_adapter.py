from __future__ import annotations

import re
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlparse

from .adapters import MEDICAL_HINTS
from .ccgp_lifecycle_adapter import CcgpLifecycleAdapter, ParsedCcgpLifecycleNotice
from .collector_core import DiscoveredLink, Snapshot, extract_anchors, normalize_space, parse_cn_datetime, strip_tags


_OFFICIAL_DETAIL_HOSTS = {
    "tjgp.cz.tj.gov.cn",
    "ccgp-tianjin.gov.cn",
    "www.ccgp-tianjin.gov.cn",
}


@dataclass(frozen=True)
class TianjinGovernmentProcurementAdapter(CcgpLifecycleAdapter):
    """Partial adapter for the Tianjin Government Procurement primary publication site.

    Verified scope in Pilot v0.1:
    - official host/alias family: tjgp.cz.tj.gov.cn and ccgp-tianjin.gov.cn (+ www)
    - detail route family: /portal/documentView.do with exact method=view, numeric id, ver=2
    - evidence-backed parsing of a supplied detail page

    Listing/search discovery and every notice category on the live 2026 site are not yet
    independently verified, so Coverage must remain PARTIAL_IMPLEMENTATION.
    """

    source_id: str = "tj_government_procurement"
    base_url: str = "https://tjgp.cz.tj.gov.cn/"

    @property
    def allowed_hosts(self) -> set[str]:
        return set(_OFFICIAL_DETAIL_HOSTS)

    @staticmethod
    def is_verified_detail_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if (parsed.hostname or "").lower() not in _OFFICIAL_DETAIL_HOSTS:
            return False
        if parsed.path != "/portal/documentView.do" or parsed.fragment:
            return False
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            return False
        if set(query) != {"method", "id", "ver"}:
            return False
        if any(len(values) != 1 for values in query.values()):
            return False
        return query["method"][0] == "view" and query["id"][0].isdigit() and query["ver"][0] == "2"

    def discover(self, listing_html: str, listing_url: str) -> list[DiscoveredLink]:
        # This helper is deliberately narrow: it only accepts already-visible native
        # detail links. It does not claim that listing pagination/search is implemented.
        result: list[DiscoveredLink] = []
        for link in extract_anchors(listing_html, listing_url):
            if not self.is_verified_detail_url(link.url):
                continue
            if not any(hint in link.title for hint in MEDICAL_HINTS):
                continue
            result.append(link)
        return result

    def parse_notice(self, snapshot: Snapshot) -> ParsedCcgpLifecycleNotice:
        if not self.is_verified_detail_url(snapshot.source_url):
            raise ValueError("URL is outside the verified Tianjin government-procurement detail route")

        parsed = super().parse_notice(snapshot)
        text = strip_tags(snapshot.text)
        normalized_text = normalize_space(text)
        evidence = dict(parsed.evidence_fragments)

        buyer_name = parsed.buyer_name or self._extract_native_buyer(text)
        if buyer_name and buyer_name in normalized_text:
            evidence["buyer_name"] = buyer_name

        published_at = parsed.published_at
        published_precision = parsed.published_at_precision if published_at else "UNKNOWN"
        if not published_at:
            published_raw = self._extract_native_published(text)
            published_at = parse_cn_datetime(published_raw)
            published_precision = "DAY" if published_at else "UNKNOWN"
            if published_raw and published_raw in normalized_text:
                evidence["published_at"] = published_raw
        else:
            # The inherited CCGP parser only recognizes source-native timestamps with
            # an explicit HH:MM clock, so a non-empty inherited value is minute-precise.
            published_precision = "MINUTE"

        missing = [
            name
            for name, value in (
                ("project_name", parsed.project_name),
                ("buyer_name", buyer_name),
                ("published_at", published_at),
            )
            if not value
        ]
        reason = (
            "missing required Tianjin government-procurement fields: " + ", ".join(missing)
            if missing
            else None
        )
        return replace(
            parsed,
            buyer_name=buyer_name,
            published_at=published_at or "",
            published_at_precision=published_precision,
            evidence_fragments=evidence,
            verification_reason=reason,
        )

    @staticmethod
    def _extract_native_buyer(text: str) -> str:
        # Fail closed to the purchaser subsection. Do not let a missing purchaser name
        # drift across the page and accidentally capture the procurement-agent name.
        section_match = re.search(
            r"采购人信息\s*(.*?)(?=采购代理机构信息|代理机构信息|项目联系方式|$)",
            text,
            re.S,
        )
        if section_match:
            section = section_match.group(1)[:1200]
            match = re.search(r"(?:^|\n)\s*名称\s*[:：]\s*([^\n]+)", section)
            if match:
                return normalize_space(match.group(1))

        for pattern in (
            r"采购人名称\s*[:：]\s*([^\n]+)",
            r"采购人\s*[:：]\s*([^\n]+)",
        ):
            match = re.search(pattern, text)
            if match:
                return normalize_space(match.group(1))
        return ""

    @staticmethod
    def _extract_native_published(text: str) -> str | None:
        patterns = (
            r"发布日期\s*[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日)",
            r"公告发布日期\s*[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return normalize_space(match.group(1))
        return None
