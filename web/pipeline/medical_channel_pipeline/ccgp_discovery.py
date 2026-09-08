from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

CCGP_SEARCH_URL = "https://search.ccgp.gov.cn/bxsearch"
CCGP_DETAIL_BASE = "https://www.ccgp.gov.cn/"
CCGP_DETAIL_HOSTS = {"ccgp.gov.cn", "www.ccgp.gov.cn"}
RATE_LIMIT_MARKERS = ("您的访问过于频繁", "频繁访问")
PRIMARY_OPPORTUNITY_EXCLUSION_MARKERS = (
    "中标公告",
    "中标结果公告",
    "成交公告",
    "成交结果公告",
    "结果公告",
    "终止公告",
    "废标公告",
    "更正公告",
    "变更公告",
)
PRIMARY_OPPORTUNITY_EXCLUSION_PATHS = (
    "/zbgg/",
    "/cjgg/",
    "/zzgg/",
    "/fbgg/",
    "/gzgg/",
)

BID_TYPE_CODES = {
    "全部": "0",
    "公开招标": "1",
    "询价公告": "2",
    "竞争性谈判": "3",
    "单一来源": "4",
    "资格预审": "5",
    "更正公告": "6",
    "竞争性磋商": "7",
    "中标公告": "8",
    "成交公告": "9",
    "终止公告": "10",
}

NOTICE_TYPE_MARKERS = (
    "公开招标公告",
    "竞争性磋商公告",
    "竞争性谈判公告",
    "询价公告",
    "资格预审公告",
    "单一来源公告",
    "更正公告",
    "中标公告",
    "成交公告",
    "终止公告",
    "公开招标",
    "竞争性磋商",
    "竞争性谈判",
    "单一来源",
    "资格预审",
)

# CCGP's province-level zone ids follow the first two digits of the official
# county-and-above administrative code. The business market remains an explicit
# field on verified records; detail-page region text is never used to infer it.
REGION_ZONE_IDS = {
    "北京": "11",
    "天津": "12",
    "河北": "13",
    "辽宁": "21",
    "吉林": "22",
    "黑龙江": "23",
}


@dataclass(frozen=True)
class DiscoveryCandidate:
    title: str
    detail_url: str
    published_at: str | None
    buyer_name: str | None
    region: str | None
    notice_type: str | None
    search_keyword: str
    evidence_status: str = "DISCOVERY_ONLY"

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def is_primary_opportunity_candidate(candidate: DiscoveryCandidate) -> bool:
    """Keep formal opportunity notices out of result/correction event pages."""
    title = str(candidate.title or "").strip()
    notice_type = str(candidate.notice_type or "").strip()
    if any(marker in title or marker in notice_type for marker in PRIMARY_OPPORTUNITY_EXCLUSION_MARKERS):
        return False
    path = urlsplit(candidate.detail_url).path.lower()
    return not any(marker in path for marker in PRIMARY_OPPORTUNITY_EXCLUSION_PATHS)


def _ccgp_date(value: str) -> str:
    return value.strip().replace("-", ":")


def build_search_url(
    *,
    keyword: str,
    notice_type: str = "全部",
    page_index: int = 1,
    start_date: str,
    end_date: str,
    region: str | None = None,
) -> str:
    if page_index < 1:
        raise ValueError("page_index must be >= 1")
    if notice_type not in BID_TYPE_CODES:
        raise ValueError(f"unsupported notice_type: {notice_type}")
    if region is not None and region not in REGION_ZONE_IDS:
        raise ValueError(f"unsupported region: {region}")

    params = {
        "searchtype": "1",
        "page_index": str(page_index),
        "bidSort": "0",
        "buyerName": "",
        "projectId": "",
        "pinMu": "0",
        "bidType": BID_TYPE_CODES[notice_type],
        "dbselect": "bidx",
        "kw": keyword,
        "start_time": _ccgp_date(start_date),
        "end_time": _ccgp_date(end_date),
        "timeType": "6",
        "displayZone": region or "",
        "zoneId": REGION_ZONE_IDS.get(region, "") if region else "",
        "pppStatus": "0",
        "agentName": "",
    }
    return f"{CCGP_SEARCH_URL}?{urlencode(params)}"


class _SearchListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._list_depth = 0
        self._li_depth = 0
        self._capture_anchor = False
        self._current_href: str | None = None
        self._anchor_text: list[str] = []
        self._meta_text: list[str] = []
        self.rows: list[tuple[str, str, str]] = []

    @staticmethod
    def _class_tokens(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = next((v for k, v in attrs if k == "class"), None) or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._class_tokens(attrs)
        if tag in {"ul", "div"} and "vT-srch-result-list-bid" in classes:
            self._list_depth += 1
            return
        if self._list_depth and tag == "li":
            self._li_depth += 1
            if self._li_depth == 1:
                self._current_href = None
                self._anchor_text = []
                self._meta_text = []
            return
        if self._li_depth == 1 and tag == "a" and self._current_href is None:
            self._current_href = next((v for k, v in attrs if k == "href"), None)
            self._capture_anchor = True

    def handle_endtag(self, tag: str) -> None:
        if self._li_depth == 1 and tag == "a":
            self._capture_anchor = False
        elif self._list_depth and tag == "li" and self._li_depth:
            if self._li_depth == 1:
                title = "".join(self._anchor_text).strip()
                meta = " ".join(self._meta_text).strip()
                href = (self._current_href or "").strip()
                if title and href:
                    self.rows.append((title, href, meta))
            self._li_depth -= 1
        elif tag in {"ul", "div"} and self._list_depth and self._li_depth == 0:
            self._list_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._li_depth != 1:
            return
        if self._capture_anchor:
            self._anchor_text.append(data)
            return
        text = data.strip()
        if text:
            # CCGP currently renders date, notice type, region and buyer across
            # several sibling tags/text nodes. Capture the whole visible row
            # outside the title link instead of assuming everything is <span>.
            self._meta_text.append(text)


def _normalize_date(meta: str) -> str | None:
    match = re.search(r"\b(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})\b", meta)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _parse_meta(meta: str) -> tuple[str | None, str | None, str | None, str | None]:
    published_at = _normalize_date(meta)
    buyer_name = None
    region = None
    notice_type = None
    normalized_meta = re.sub(
        r"\s+",
        " ",
        meta.replace("\r", " ").replace("\n", " ").replace("：", ":"),
    ).strip()

    # The search request's zoneId is discovery-only. Geography must be proven by
    # the official result row itself (currently "地域:北京"; some pages use
    # "行政区域:北京市").
    region_match = re.search(
        r"(?:地域|行政区域)\s*:\s*([^|\s]+)",
        normalized_meta,
    )
    if region_match:
        region = region_match.group(1).strip(" ,，;；") or None

    for marker in NOTICE_TYPE_MARKERS:
        if marker in normalized_meta:
            notice_type = marker
            break

    parts = [part.strip() for part in normalized_meta.split("|") if part.strip()]
    for part in parts:
        normalized = part.strip()
        if normalized.startswith("采购人") and ":" in normalized:
            buyer_name = normalized.split(":", 1)[1].strip() or None
            continue
        if region is None and any(token in part for token in ("北京市", "天津市", "上海市", "重庆市", "省", "自治区", "特别行政区")):
            if not re.match(r"^20\d{2}[.\-/]", part) and len(part) <= 24:
                region = part
    return published_at, buyer_name, region, notice_type


def _canonical_detail_url(href: str) -> str:
    detail_url = urljoin(CCGP_DETAIL_BASE, href)
    parsed = urlsplit(detail_url)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme == "http"
        and hostname in CCGP_DETAIL_HOSTS
        and parsed.username is None
        and parsed.password is None
        and parsed.port in (None, 80)
    ):
        return urlunsplit(("https", hostname, parsed.path, parsed.query, parsed.fragment))
    return detail_url


def parse_search_html(html: str, *, keyword: str) -> list[DiscoveryCandidate]:
    if any(marker in html for marker in RATE_LIMIT_MARKERS):
        raise RuntimeError("CCGP_RATE_LIMITED")
    parser = _SearchListParser()
    parser.feed(html)
    candidates: list[DiscoveryCandidate] = []
    seen_urls: set[str] = set()
    for title, href, meta in parser.rows:
        detail_url = _canonical_detail_url(href)
        if detail_url in seen_urls:
            continue
        seen_urls.add(detail_url)
        published_at, buyer_name, region, notice_type = _parse_meta(meta)
        candidates.append(
            DiscoveryCandidate(
                title=title,
                detail_url=detail_url,
                published_at=published_at,
                buyer_name=buyer_name,
                region=region,
                notice_type=notice_type,
                search_keyword=keyword,
            )
        )
    return candidates


def fetch_search_page(search_url: str, *, timeout_seconds: int = 30) -> str:
    if not search_url.startswith(CCGP_SEARCH_URL):
        raise ValueError("search_url must target the CCGP public search endpoint")
    request = Request(
        search_url,
        headers={
            "User-Agent": "MedicalChannelAI/0.1 (+evidence-first public procurement discovery)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    html = body.decode(charset, errors="replace")
    if any(marker in html for marker in RATE_LIMIT_MARKERS):
        raise RuntimeError("CCGP_RATE_LIMITED")
    return html
