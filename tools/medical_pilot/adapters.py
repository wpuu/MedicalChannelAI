from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from .collector_core import (
    DiscoveredLink,
    ParsedNotice,
    Snapshot,
    extract_anchors,
    extract_table_rows,
    normalize_space,
    parse_cn_datetime,
    parse_money_to_cny,
    strip_tags,
    table_pairs,
)


MEDICAL_HINTS = (
    "医院",
    "医疗",
    "医学",
    "检验",
    "设备",
    "试剂",
    "耗材",
    "血液",
    "血站",
    "疾控",
    "卫生",
    "体检",
    "实验室",
    "影像",
    "超声",
    "放射",
    "手术",
    "康复",
)


def _medical_hint(title: str) -> bool:
    return any(hint in title for hint in MEDICAL_HINTS)


def _first(mapping: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value:
            return normalize_space(value)
    return None


def _extract_project_number(text: str, title: str) -> str | None:
    patterns = (
        r"项目编号\s*[:：]\s*([A-Za-z0-9_.\-/]+)",
        r"\(项目编号\s*[:：]\s*([^\)）]+)[\)）]",
    )
    for source in (text, title):
        for pattern in patterns:
            match = re.search(pattern, source, re.I)
            if match:
                return normalize_space(match.group(1))
    return None


def _extract_cn_deadline(text: str, labels: Iterable[str]) -> str | None:
    for label in labels:
        match = re.search(
            rf"{re.escape(label)}\s*[:：]?\s*(20\d{{2}}年\d{{1,2}}月\d{{1,2}}日\s*\d{{1,2}}[点:：]\d{{2}}(?:分)?)",
            text,
        )
        if match:
            value = match.group(1).replace("点", ":").replace("分", "")
            parsed = parse_cn_datetime(value)
            if parsed:
                return parsed
    return None


def _notice_type_from_title(title: str) -> str:
    if "终止" in title or "废标" in title:
        return "TERMINATION"
    if "更正" in title or "变更" in title:
        return "AMENDMENT"
    if "中标" in title or "成交" in title:
        return "AWARD"
    if "合同" in title:
        return "CONTRACT"
    if "暂停" in title:
        return "SUSPENSION"
    return "TENDER"


@dataclass(frozen=True)
class CcgpAdapter:
    source_id: str = "ccgp_local_notices"
    base_url: str = "https://www.ccgp.gov.cn/"

    @property
    def allowed_hosts(self) -> set[str]:
        return {"www.ccgp.gov.cn", "ccgp.gov.cn"}

    def discover(self, listing_html: str, listing_url: str) -> list[DiscoveredLink]:
        links = extract_anchors(listing_html, listing_url)
        result: list[DiscoveredLink] = []
        for link in links:
            parsed = urlparse(link.url)
            if parsed.hostname not in self.allowed_hosts:
                continue
            if "/cggg/" not in parsed.path or not parsed.path.endswith(".htm"):
                continue
            if not _medical_hint(link.title):
                continue
            result.append(link)
        return result

    def parse_notice(self, snapshot: Snapshot) -> ParsedNotice:
        text = strip_tags(snapshot.text)
        rows = extract_table_rows(snapshot.text)
        pairs = table_pairs(rows)

        project_name = _first(pairs, "采购项目名称", "项目名称")
        if not project_name:
            match = re.search(r"项目名称\s*[:：]\s*([^\n]+)", text)
            project_name = normalize_space(match.group(1)) if match else ""

        buyer_name = _first(pairs, "采购单位", "采购人")
        if not buyer_name:
            match = re.search(r"采购单位\s*[:：]?\s*([^\n]+)", text)
            buyer_name = normalize_space(match.group(1)) if match else ""

        published_raw = _first(pairs, "公告时间")
        published_at = parse_cn_datetime(published_raw)
        if not published_at:
            match = re.search(r"20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}", text)
            published_raw = match.group(0) if match else None
            published_at = parse_cn_datetime(published_raw)

        title = project_name
        if not title:
            title_match = re.search(r"<title[^>]*>(.*?)</title>", snapshot.text, re.I | re.S)
            if title_match:
                title = normalize_space(re.sub(r"<[^>]+>", "", title_match.group(1)))
        notice_type = _notice_type_from_title(title or text[:200])

        project_number = _extract_project_number(text, title or "")

        budget_raw = _first(pairs, "预算金额", "预算")
        budget_cny = parse_money_to_cny(budget_raw)
        if not budget_cny:
            budget_match = re.search(r"预算金额\s*[:：]\s*([^\n]+)", text)
            if budget_match:
                budget_raw = normalize_space(budget_match.group(1))
                budget_cny = parse_money_to_cny(budget_raw)

        bid_raw = _first(pairs, "开标时间", "响应文件开启时间")
        bid_deadline = parse_cn_datetime(bid_raw)
        if not bid_deadline:
            bid_deadline = _extract_cn_deadline(
                text,
                (
                    "提交投标文件截止时间、开标时间和地点",
                    "提交投标文件截止时间",
                    "响应文件提交截止时间",
                    "响应文件开启时间",
                ),
            )

        procurement_method = None
        method_map = {
            "公开招标": "PUBLIC_TENDER",
            "竞争性磋商": "COMPETITIVE_CONSULTATION",
            "竞争性谈判": "COMPETITIVE_NEGOTIATION",
            "询价": "INQUIRY",
            "单一来源": "SINGLE_SOURCE",
        }
        for marker, normalized in method_map.items():
            if marker in text[:1500] or marker in title:
                procurement_method = normalized
                break

        evidence = {}
        if project_name and project_name in text:
            evidence["project_name"] = project_name
        if buyer_name and buyer_name in text:
            evidence["buyer_name"] = buyer_name
        if published_raw and normalize_space(published_raw) in normalize_space(text):
            evidence["published_at"] = normalize_space(published_raw)
        if project_number and project_number in text:
            evidence["project_number"] = project_number
        if budget_raw and normalize_space(budget_raw) in normalize_space(text):
            evidence["budget_cny"] = normalize_space(budget_raw)
        if bid_raw and normalize_space(bid_raw) in normalize_space(text):
            evidence["bid_deadline"] = normalize_space(bid_raw)
        elif bid_deadline:
            match = re.search(r"20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}[点:：]\d{2}", text)
            if match:
                evidence["bid_deadline"] = normalize_space(match.group(0))
        if procurement_method:
            for marker in method_map:
                if marker in text[:1500] or marker in title:
                    evidence["procurement_method"] = marker
                    break

        reason = None
        if not project_name or not buyer_name or not published_at:
            missing = [
                name
                for name, value in (
                    ("project_name", project_name),
                    ("buyer_name", buyer_name),
                    ("published_at", published_at),
                )
                if not value
            ]
            reason = "missing required official fields: " + ", ".join(missing)

        return ParsedNotice(
            source_id=self.source_id,
            source_url=snapshot.source_url,
            source_authority="OFFICIAL_GOVERNMENT",
            notice_type=notice_type,
            project_name=project_name,
            buyer_name=buyer_name,
            published_at=published_at or "",
            project_number=project_number,
            budget_cny=budget_cny,
            bid_deadline=bid_deadline,
            procurement_method=procurement_method,
            product_items=(),
            evidence_fragments=evidence,
            verification_reason=reason,
        )


@dataclass(frozen=True)
class TjmughAdapter:
    source_id: str = "tjmugh_procurement"
    base_url: str = "https://www.tjmugh.com.cn/cgxxtzgg/index.shtml"

    @property
    def allowed_hosts(self) -> set[str]:
        return {"www.tjmugh.com.cn", "tjmugh.com.cn"}

    def discover(self, listing_html: str, listing_url: str) -> list[DiscoveredLink]:
        result: list[DiscoveredLink] = []
        for link in extract_anchors(listing_html, listing_url):
            parsed = urlparse(link.url)
            if parsed.hostname not in self.allowed_hosts:
                continue
            if not re.search(r"/system/20\d{2}/\d{2}/\d{2}/\d+\.shtml$", parsed.path):
                continue
            if not any(marker in link.title for marker in ("市场调研", "论证", "比选", "采购", "设备", "仪器")):
                continue
            result.append(link)
        return result

    def parse_notice(self, snapshot: Snapshot) -> ParsedNotice:
        text = strip_tags(snapshot.text)
        title = self._extract_title(snapshot.text, text)
        published_raw = self._extract_published(text)
        published_at = parse_cn_datetime(published_raw)
        notice_type = "INTERNAL_SELECTION" if "比选" in title else "MARKET_RESEARCH"

        project_number = _extract_project_number(text, title)
        budget_match = re.search(r"预算金额\s*[:：]\s*([^\n]+)", text)
        budget_raw = normalize_space(budget_match.group(1)) if budget_match else None
        budget_cny = parse_money_to_cny(budget_raw)

        registration_raw = self._extract_registration_deadline(text)
        registration_deadline = parse_cn_datetime(registration_raw)
        product_items = tuple(self._extract_product_items(text))

        evidence = {
            "project_name": title,
            "buyer_name": "天津医科大学总医院",
        }
        if published_raw:
            evidence["published_at"] = published_raw
        if project_number:
            evidence["project_number"] = project_number
        if budget_raw:
            evidence["budget_cny"] = budget_raw
        if registration_raw:
            evidence["registration_deadline"] = registration_raw

        reason = None
        if not title or not published_at:
            reason = "missing required official title or publication timestamp"

        return ParsedNotice(
            source_id=self.source_id,
            source_url=snapshot.source_url,
            source_authority="OFFICIAL_HOSPITAL",
            notice_type=notice_type,
            project_name=title,
            buyer_name="天津医科大学总医院",
            published_at=published_at or "",
            project_number=project_number,
            budget_cny=budget_cny,
            registration_deadline=registration_deadline,
            procurement_method="HOSPITAL_MARKET_RESEARCH" if notice_type == "MARKET_RESEARCH" else "HOSPITAL_INTERNAL_SELECTION",
            product_items=product_items,
            evidence_fragments=evidence,
            verification_reason=reason,
        )

    @staticmethod
    def _extract_title(raw_html: str, text: str) -> str:
        heading_patterns = (
            r"<h[1-4][^>]*>(.*?)</h[1-4]>",
            r"<title[^>]*>(.*?)</title>",
        )
        for pattern in heading_patterns:
            match = re.search(pattern, raw_html, re.I | re.S)
            if not match:
                continue
            title = normalize_space(re.sub(r"<[^>]+>", "", match.group(1)))
            title = re.sub(r"-天津医科大学总医院.*$", "", title).strip()
            if title and title != "采购信息通知公告":
                return title
        for line in text.splitlines():
            line = normalize_space(line)
            if "天津医科大学总医院" in line and any(marker in line for marker in ("市场调研", "比选", "邀请函")):
                return line
        return ""

    @staticmethod
    def _extract_published(text: str) -> str | None:
        match = re.search(r"20\d{2}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}", text)
        if match:
            return normalize_space(match.group(0))
        match = re.search(r"20\d{2}年\d{1,2}月\d{1,2}日", text)
        return normalize_space(match.group(0)) if match else None

    @staticmethod
    def _extract_registration_deadline(text: str) -> str | None:
        patterns = (
            r"报名截止时间为\s*[:：]?\s*(20\d{2}\s*年\s*\d{1,2}月\d{1,2}日[^\n。；;]{0,24})",
            r"报名截止时间\s*[:：]\s*(20\d{2}\s*年\s*\d{1,2}月\d{1,2}日[^\n。；;]{0,24})",
            r"本次报名截止时间为\s*[:：]?\s*(20\d{2}年\d{1,2}月\d{1,2}日[^\n。；;]{0,24})",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = normalize_space(match.group(1))
                value = value.replace("下午", "").replace("上午", "")
                value = re.sub(r"(\d{1,2})\s*[：:]\s*(\d{2})", r"\1:\2", value)
                return value
        return None

    @staticmethod
    def _extract_product_items(text: str) -> list[str]:
        segment_match = re.search(
            r"(?:论证项目名称|论证项目)\s*[:：]?\s*(.*?)(?:\n二[、.]|二、|供应商参加)",
            text,
            re.S,
        )
        segment = segment_match.group(1) if segment_match else text
        items = []
        for match in re.finditer(r"（\s*\d+\s*）\s*([^（\n]+?)(?=（\s*\d+\s*）|$)", segment, re.S):
            item = normalize_space(match.group(1)).strip("；;。,.，")
            if item and len(item) <= 200:
                items.append(item)
        seen: set[str] = set()
        return [item for item in items if not (item in seen or seen.add(item))]
