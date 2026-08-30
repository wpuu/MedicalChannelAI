from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .collector_core import (
    DiscoveredLink,
    ParsedNotice,
    Snapshot,
    extract_anchors,
    normalize_space,
    parse_cn_datetime,
    parse_money_to_cny,
    strip_tags,
)


@dataclass(frozen=True)
class FirstCentralHospitalAdapter:
    source_id: str = "tj_first_central_hospital_procurement"
    base_url: str = "https://www.tj-fch.com/ywgk/ynbx/index.shtml"

    @property
    def allowed_hosts(self) -> set[str]:
        return {"www.tj-fch.com", "tj-fch.com"}

    def discover(self, listing_html: str, listing_url: str) -> list[DiscoveredLink]:
        result: list[DiscoveredLink] = []
        for link in extract_anchors(listing_html, listing_url):
            parsed = urlparse(link.url)
            if parsed.hostname not in self.allowed_hosts:
                continue
            if not re.search(r"/system/20\d{2}/\d{2}/\d{2}/\d+\.shtml$", parsed.path):
                continue
            if not any(
                marker in link.title
                for marker in (
                    "院内比选",
                    "采购",
                    "成交公告",
                    "结果公示",
                    "测试企业征集",
                    "企业征集",
                    "项目测试",
                )
            ):
                continue
            result.append(link)
        return result

    def parse_notice(self, snapshot: Snapshot) -> ParsedNotice:
        text = strip_tags(snapshot.text)
        title = self._extract_title(snapshot.text, text)
        notice_type = self._notice_type(title)

        published_raw = self._extract_published(text)
        published_at = parse_cn_datetime(published_raw)

        project_name = self._extract_project_name(text, title)
        project_number = self._extract_project_number(text)
        budget_raw = self._extract_budget_raw(text)
        budget_cny = parse_money_to_cny(budget_raw)
        response_deadline_raw = self._extract_response_deadline(text)
        response_deadline = parse_cn_datetime(response_deadline_raw)
        evaluation_raw = self._extract_evaluation_time(text)
        evaluation_time = parse_cn_datetime(evaluation_raw)

        evidence: dict[str, str] = {}
        normalized_text = normalize_space(text)
        for field_name, raw in (
            ("project_name", project_name),
            ("published_at", published_raw),
            ("project_number", project_number),
            ("budget_cny", budget_raw),
            ("bid_deadline", response_deadline_raw),
        ):
            if raw and normalize_space(raw) in normalized_text:
                evidence[field_name] = normalize_space(raw)
        if "天津市第一中心医院" in normalized_text:
            evidence["buyer_name"] = "天津市第一中心医院"

        reason = None
        if not project_name or not published_at or "buyer_name" not in evidence:
            missing = [
                name
                for name, value in (
                    ("project_name", project_name),
                    ("published_at", published_at),
                    ("buyer_name_evidence", evidence.get("buyer_name")),
                )
                if not value
            ]
            reason = "missing required First Central Hospital fields: " + ", ".join(missing)

        procurement_method = {
            "INTERNAL_SELECTION": "HOSPITAL_INTERNAL_SELECTION",
            "MARKET_RESEARCH": "HOSPITAL_ENTERPRISE_RECRUITMENT",
            "AWARD": "HOSPITAL_INTERNAL_RESULT",
        }.get(notice_type)

        product_items = self._extract_project_content_items(text)
        if evaluation_time and response_deadline is None:
            pass

        return ParsedNotice(
            source_id=self.source_id,
            source_url=snapshot.source_url,
            source_authority="OFFICIAL_HOSPITAL",
            notice_type=notice_type,
            project_name=project_name,
            buyer_name="天津市第一中心医院",
            published_at=published_at or "",
            project_number=project_number,
            budget_cny=budget_cny,
            registration_deadline=None,
            bid_deadline=response_deadline,
            procurement_method=procurement_method,
            product_items=tuple(product_items),
            evidence_fragments=evidence,
            verification_reason=reason,
        )

    @staticmethod
    def _extract_title(raw_html: str, text: str) -> str:
        for pattern in (r"<h[1-3][^>]*>(.*?)</h[1-3]>", r"<title[^>]*>(.*?)</title>"):
            match = re.search(pattern, raw_html, re.I | re.S)
            if not match:
                continue
            value = normalize_space(re.sub(r"<[^>]+>", "", match.group(1)))
            value = re.sub(r"\s*[-_|｜]\s*天津市第一中心医院(?:官网)?\s*$", "", value).strip()
            if value and value not in {"院内比选采购信息", "院务公开"}:
                return value
        for line in text.splitlines():
            line = normalize_space(line)
            if "天津市第一中心医院" in line and any(
                marker in line for marker in ("院内比选", "征集公告", "成交公告", "结果公示")
            ):
                return line
        return ""

    @staticmethod
    def _notice_type(title: str) -> str:
        if "成交公告" in title or "结果公示" in title or "中标" in title:
            return "AWARD"
        if "测试企业征集" in title or "企业征集" in title or ("测试" in title and "征集" in title):
            return "MARKET_RESEARCH"
        return "INTERNAL_SELECTION"

    @staticmethod
    def _extract_published(text: str) -> str | None:
        match = re.search(r"20\d{2}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}", text)
        if match:
            return normalize_space(match.group(0))
        match = re.search(r"20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}", text)
        if match:
            return normalize_space(match.group(0))
        match = re.search(r"20\d{2}年\d{1,2}月\d{1,2}日", text)
        return normalize_space(match.group(0)) if match else None

    @staticmethod
    def _extract_project_name(text: str, title: str) -> str:
        match = re.search(r"项目名称\s*[:：]\s*([^\n。]+)", text)
        if match:
            return normalize_space(match.group(1)).rstrip("。.")
        cleaned = re.sub(r"(院内比选(?:招标)?公告|测试企业征集公告|成交公告|院内比选结果公示)$", "", title)
        return normalize_space(cleaned)

    @staticmethod
    def _extract_project_number(text: str) -> str | None:
        match = re.search(r"项目编号\s*[:：]\s*([A-Za-z0-9_.\-/]+)", text)
        return normalize_space(match.group(1)) if match else None

    @staticmethod
    def _extract_budget_raw(text: str) -> str | None:
        patterns = (
            r"项目预算\s*[:：]\s*([0-9,.]+\s*(?:亿元|万元|元))",
            r"预算金额\s*[:：]\s*([0-9,.]+\s*(?:亿元|万元|元))",
            r"最高限价\s*[:：]\s*([0-9,.]+\s*(?:亿元|万元|元))",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return normalize_space(match.group(1))
        return None

    @staticmethod
    def _extract_response_deadline(text: str) -> str | None:
        patterns = (
            r"院内比选响应文件递交截止时间\s*[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2})",
            r"响应文件递交截止时间\s*[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2})",
            r"提交院内比选响应文件截止时间\s*[:：]?\s*(20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2})",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return normalize_space(match.group(1))
        return None

    @staticmethod
    def _extract_evaluation_time(text: str) -> str | None:
        patterns = (
            r"现场比选时间\s*[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2})",
            r"现场比选时间\s*[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日[^\n。]{0,20})",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = normalize_space(match.group(1)).replace("下午", "").replace("上午", "")
                return value
        return None

    @staticmethod
    def _extract_project_content_items(text: str) -> list[str]:
        items: list[str] = []
        for match in re.finditer(r"(?:项目内容|设备名称|产品名称)\s*[:：]\s*([^\n。]+)", text):
            value = normalize_space(match.group(1))
            if value and len(value) <= 200:
                items.append(value)
        seen: set[str] = set()
        return [item for item in items if not (item in seen or seen.add(item))]
