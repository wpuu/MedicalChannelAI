from __future__ import annotations

import re
from dataclasses import dataclass, replace
from urllib.parse import urlparse

from .adapters import MEDICAL_HINTS
from .ccgp_lifecycle_adapter import CcgpLifecycleAdapter, ParsedCcgpLifecycleNotice
from .collector_core import DiscoveredLink, Snapshot, extract_anchors, normalize_space, parse_cn_datetime, strip_tags


@dataclass(frozen=True)
class TianjinGovernmentProcurementAdapter(CcgpLifecycleAdapter):
    """Partial adapter for the Tianjin Government Procurement primary publication site.

    Verified scope in Pilot v0.1:
    - canonical host: tjgp.cz.tj.gov.cn
    - detail route family: /portal/documentView.do?method=view&id=<digits>&ver=2
    - evidence-backed parsing of a supplied detail page

    Listing/search discovery and every notice category on the live 2026 site are not yet
    independently verified, so Coverage must remain PARTIAL_IMPLEMENTATION.
    """

    source_id: str = "tj_government_procurement"
    base_url: str = "http://tjgp.cz.tj.gov.cn/"

    @property
    def allowed_hosts(self) -> set[str]:
        return {"tjgp.cz.tj.gov.cn"}

    @staticmethod
    def is_verified_detail_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.hostname != "tjgp.cz.tj.gov.cn":
            return False
        if parsed.path != "/portal/documentView.do":
            return False
        query = parsed.query
        return bool(
            re.search(r"(?:^|&)method=view(?:&|$)", query)
            and re.search(r"(?:^|&)id=\d+(?:&|$)", query)
            and re.search(r"(?:^|&)ver=2(?:&|$)", query)
        )

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
        if parsed.published_at:
            return replace(parsed, published_at_precision="MINUTE")

        text = strip_tags(snapshot.text)
        match = re.search(r"发布日期\s*[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日)", text)
        if not match:
            return parsed

        published_raw = normalize_space(match.group(1))
        published_at = parse_cn_datetime(published_raw)
        evidence = dict(parsed.evidence_fragments)
        if published_at and published_raw in normalize_space(text):
            evidence["published_at"] = published_raw

        missing = [
            name
            for name, value in (
                ("project_name", parsed.project_name),
                ("buyer_name", parsed.buyer_name),
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
            published_at=published_at or "",
            published_at_precision="DAY",
            evidence_fragments=evidence,
            verification_reason=reason,
        )
