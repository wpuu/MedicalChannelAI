from __future__ import annotations

import re
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlparse

from .adapters import MEDICAL_HINTS
from .ccgp_lifecycle_adapter import CcgpLifecycleAdapter, ParsedCcgpLifecycleNotice
from .collector_core import DiscoveredLink, Snapshot, extract_anchors, normalize_space, parse_cn_datetime, parse_money_to_cny, strip_tags


_UUID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


@dataclass(frozen=True)
class TianjinProcurementCenterAdapter(CcgpLifecycleAdapter):
    """Partial adapter for the official Tianjin Government Procurement Center site.

    Verified Pilot v0.1 scope:
    - official host: tjgpc.zwfwb.tj.gov.cn
    - detail route: /webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=<UUID>
    - public-tender detail pages whose indexed official content exposes project identity,
      purchaser, budget and bid/opening timing.

    Native listing class ids, pagination, all procurement methods and attachment download
    routes are not yet independently verified. This source therefore remains
    PARTIAL_IMPLEMENTATION and must not upgrade Tianjin coverage to exhaustive.
    """

    source_id: str = "tj_government_procurement_center"
    base_url: str = "https://tjgpc.zwfwb.tj.gov.cn/"

    @property
    def allowed_hosts(self) -> set[str]:
        return {"tjgpc.zwfwb.tj.gov.cn"}

    @staticmethod
    def is_verified_detail_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.hostname != "tjgpc.zwfwb.tj.gov.cn":
            return False
        if parsed.path != "/webInfo/getWebInfoByPkWebInfoId1.do":
            return False
        query = parse_qs(parsed.query, keep_blank_values=True)
        if set(query) != {"pkWebInfoId"} or len(query["pkWebInfoId"]) != 1:
            return False
        return bool(_UUID_RE.fullmatch(query["pkWebInfoId"][0]))

    def discover(self, listing_html: str, listing_url: str) -> list[DiscoveredLink]:
        # Deliberately narrow. This only accepts already-visible verified detail links;
        # it does not claim native list/search/pagination discovery is implemented.
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
            raise ValueError("URL is outside the verified Tianjin procurement-center detail route")

        parsed = super().parse_notice(snapshot)
        text = strip_tags(snapshot.text)
        normalized = normalize_space(text)
        evidence = dict(parsed.evidence_fragments)

        project_name = parsed.project_name or self._extract_project_name(text)
        buyer_name = parsed.buyer_name or self._extract_buyer(text)
        published_raw = self._extract_information_date(text)
        published_at = parse_cn_datetime(published_raw) if published_raw else parsed.published_at
        published_precision = "DAY" if published_raw and published_at else (parsed.published_at_precision if parsed.published_at else "UNKNOWN")
        budget_raw = self._extract_budget(text)
        budget_cny = parse_money_to_cny(budget_raw) if budget_raw else parsed.budget_cny
        bid_deadline = parsed.bid_deadline or self._extract_bid_deadline(text)

        if project_name and project_name in normalized:
            evidence["project_name"] = project_name
        if buyer_name and buyer_name in normalized:
            evidence["buyer_name"] = buyer_name
        if published_raw and published_raw in normalized:
            evidence["published_at"] = published_raw
        if budget_raw and budget_raw in normalized:
            evidence["budget_cny"] = budget_raw
        if bid_deadline:
            raw_deadline = self._find_deadline_fragment(text)
            if raw_deadline:
                evidence["bid_deadline"] = raw_deadline

        missing = [
            field
            for field, value in (
                ("project_name", project_name),
                ("buyer_name", buyer_name),
                ("published_at", published_at),
            )
            if not value
        ]
        reason = (
            "missing required Tianjin procurement-center fields: " + ", ".join(missing)
            if missing
            else None
        )
        return replace(
            parsed,
            source_id=self.source_id,
            source_url=snapshot.source_url,
            source_authority="OFFICIAL_GOVERNMENT",
            project_name=project_name,
            buyer_name=buyer_name,
            published_at=published_at or "",
            published_at_precision=published_precision,
            budget_cny=budget_cny,
            bid_deadline=bid_deadline,
            evidence_fragments=evidence,
            verification_reason=reason,
        )

    @staticmethod
    def _extract_project_name(text: str) -> str:
        patterns = (
            r"(?:\(一\)|（一）)\s*项目名称\s*[:：]\s*([^\n]+)",
            r"项目名称\s*[:：]\s*([^\n]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return normalize_space(match.group(1))
        for line in text.splitlines():
            line = normalize_space(line)
            if "项目编号" in line and any(marker in line for marker in ("公开招标公告", "竞争性磋商公告", "成交公告", "中标公告")):
                return re.sub(r"\s*[（(]项目编号.*$", "", line).strip()
        return ""

    @staticmethod
    def _extract_buyer(text: str) -> str:
        match = re.search(r"受\s*([^\n，,]{2,160}?)\s*委托", text)
        return normalize_space(match.group(1)) if match else ""

    @staticmethod
    def _extract_information_date(text: str) -> str | None:
        match = re.search(r"信息时间\s*[:：]\s*(20\d{2})[-年](\d{1,2})[-月](\d{1,2})日?", text)
        if not match:
            return None
        return f"{match.group(1)}年{match.group(2)}月{match.group(3)}日"

    @staticmethod
    def _extract_budget(text: str) -> str | None:
        patterns = (
            r"总预算\s*[:：]\s*([0-9,.]+\s*(?:元|万元|亿元))",
            r"项目预算\s*[:：]\s*([0-9,.]+\s*(?:元|万元|亿元))",
            r"预算金额\s*[:：]\s*([0-9,.]+\s*(?:元|万元|亿元))",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return normalize_space(match.group(1))
        return None

    @staticmethod
    def _find_deadline_fragment(text: str) -> str | None:
        patterns = (
            r"投标截止时间\s*[:：]?\s*(20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}[点:：]\d{2})",
            r"提交电子响应文件截止时间\s*[:：]?\s*(20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}[点:：]\d{2})",
            r"开标解密时间\s*[:：]?\s*(20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}[点:：]\d{2})",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return normalize_space(match.group(1))
        return None

    @classmethod
    def _extract_bid_deadline(cls, text: str) -> str | None:
        raw = cls._find_deadline_fragment(text)
        if not raw:
            return None
        return parse_cn_datetime(raw.replace("点", ":"))
