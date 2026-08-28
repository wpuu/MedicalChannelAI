from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Iterable


SCHEMA_VERSION = "0.1"
ID_NAMESPACE = uuid.UUID("4477294d-f38e-4adc-bfde-b50609249088")


class FetchError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Snapshot:
    source_url: str
    fetched_at: str
    status_code: int
    content_type: str
    body: bytes
    text: str
    sha256: str

    @property
    def snapshot_id(self) -> str:
        value = uuid.uuid5(ID_NAMESPACE, f"snapshot|{self.source_url}|{self.sha256}")
        return f"snap_{value}"


@dataclass(frozen=True)
class DiscoveredLink:
    url: str
    title: str


@dataclass(frozen=True)
class ParsedNotice:
    source_id: str
    source_url: str
    source_authority: str
    notice_type: str
    project_name: str
    buyer_name: str
    published_at: str
    project_number: str | None = None
    budget_cny: str | None = None
    registration_deadline: str | None = None
    bid_deadline: str | None = None
    procurement_method: str | None = None
    product_items: tuple[str, ...] = ()
    evidence_fragments: dict[str, str] = field(default_factory=dict)
    verification_reason: str | None = None

    @property
    def eligible_for_verified(self) -> bool:
        required = (
            self.source_url,
            self.project_name,
            self.buyer_name,
            self.published_at,
            self.evidence_fragments.get("project_name"),
            self.evidence_fragments.get("buyer_name"),
            self.evidence_fragments.get("published_at"),
        )
        return self.source_authority.startswith("OFFICIAL_") and all(required)


class HostBoundFetcher:
    """Small fail-closed fetcher for the pilot.

    This is deliberately not a general browser. It accepts only exact hosts supplied
    by a registered source definition, limits response size, does not follow a
    cross-host redirect, and never attempts challenge bypass.
    """

    def __init__(
        self,
        allowed_hosts: Iterable[str],
        *,
        timeout_seconds: int = 15,
        max_bytes: int = 8 * 1024 * 1024,
        user_agent: str = "HermesMedicalPilot/0.1 (+public-data-research)",
    ) -> None:
        self.allowed_hosts = {host.lower().strip(".") for host in allowed_hosts}
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.user_agent = user_agent

    def _validate_url(self, url: str) -> urllib.parse.ParseResult:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower().strip(".")
        if parsed.scheme not in {"http", "https"}:
            raise FetchError("UNSUPPORTED_SCHEME", f"unsupported scheme: {parsed.scheme}")
        if host not in self.allowed_hosts:
            raise FetchError("HOST_NOT_ALLOWED", f"host is not registered: {host}")
        return parsed

    def fetch(self, url: str) -> Snapshot:
        self._validate_url(url)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
            },
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as exc:
            raise FetchError(f"HTTP_{exc.code}", f"HTTP error for {url}: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise FetchError("NETWORK_ERROR", f"network error for {url}: {exc.reason}") from exc

        final_url = response.geturl()
        self._validate_url(final_url)
        status = int(getattr(response, "status", 200))
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        body = response.read(self.max_bytes + 1)
        if len(body) > self.max_bytes:
            raise FetchError("RESPONSE_TOO_LARGE", f"response exceeds {self.max_bytes} bytes")

        charset = response.headers.get_content_charset() or "utf-8"
        try:
            text = body.decode(charset, errors="strict")
        except (LookupError, UnicodeDecodeError):
            text = body.decode("utf-8", errors="replace")

        normalized = normalize_space(strip_tags(text)).lower()
        challenge_markers = (
            "captcha",
            "验证码",
            "访问过于频繁",
            "安全验证",
            "access denied",
            "cloudflare ray id",
        )
        if any(marker in normalized for marker in challenge_markers):
            raise FetchError("CHALLENGE_PAGE", "challenge/error page detected; fail closed")

        return Snapshot(
            source_url=final_url,
            fetched_at=utc_now_iso(),
            status_code=status,
            content_type=content_type,
            body=body,
            text=text,
            sha256=hashlib.sha256(body).hexdigest(),
        )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


class _TableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            value = normalize_space("".join(self._cell))
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


class _AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        self._href = attrs_dict.get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            title = normalize_space("".join(self._text))
            if self._href and title:
                self.anchors.append((self._href, title))
            self._href = None
            self._text = []


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_tags(raw_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw_html)
    return "\n".join(normalize_space(part) for part in parser.parts if normalize_space(part))


def extract_table_rows(raw_html: str) -> list[list[str]]:
    parser = _TableExtractor()
    parser.feed(raw_html)
    return parser.rows


def table_pairs(rows: list[list[str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        for index in range(0, len(row) - 1, 2):
            key = normalize_space(row[index]).rstrip("：:")
            value = normalize_space(row[index + 1])
            if key and value and key not in result:
                result[key] = value
    return result


def extract_anchors(raw_html: str, base_url: str) -> list[DiscoveredLink]:
    parser = _AnchorExtractor()
    parser.feed(raw_html)
    seen: set[str] = set()
    result: list[DiscoveredLink] = []
    for href, title in parser.anchors:
        url = urllib.parse.urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        result.append(DiscoveredLink(url=url, title=title))
    return result


def parse_cn_datetime(value: str | None) -> str | None:
    if not value:
        return None
    value = normalize_space(value)
    patterns = (
        (r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[:：](\d{2})", True),
        (r"(20\d{2})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})", True),
        (r"(20\d{2})年(\d{1,2})月(\d{1,2})日", False),
        (r"(20\d{2})-(\d{1,2})-(\d{1,2})", False),
    )
    for pattern, has_time in patterns:
        match = re.search(pattern, value)
        if not match:
            continue
        numbers = [int(part) for part in match.groups()]
        if has_time:
            year, month, day, hour, minute = numbers
        else:
            year, month, day = numbers
            hour = minute = 0
        return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+08:00"
    return None


def parse_money_to_cny(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = normalize_space(value).replace(",", "").replace("￥", "").replace("¥", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(亿元|万元|元)", cleaned)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation:
        return None
    unit = match.group(2)
    if unit == "亿元":
        amount *= Decimal("100000000")
    elif unit == "万元":
        amount *= Decimal("10000")
    return f"{amount.quantize(Decimal('0.01')):.2f}"


def deterministic_id(prefix: str, seed: str) -> str:
    return f"{prefix}_{uuid.uuid5(ID_NAMESPACE, seed)}"


def build_event_and_facts(notice: ParsedNotice, snapshot: Snapshot) -> tuple[dict, list[dict]]:
    project_seed = notice.project_number or f"{notice.buyer_name}|{notice.project_name}"
    canonical_project_id = deterministic_id("mprj", f"project|{project_seed}")
    event_id = deterministic_id(
        "evt", f"event|{notice.source_url}|{notice.published_at}|{notice.notice_type}"
    )
    opportunity_id = deterministic_id("opp", f"opportunity|{canonical_project_id}")

    verification_status = "VERIFIED" if notice.eligible_for_verified else "UNVERIFIED"
    event = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "canonical_project_id": canonical_project_id,
        "event_type": notice.notice_type,
        "source_id": notice.source_id,
        "source_url": notice.source_url,
        "source_authority": notice.source_authority,
        "project_number": notice.project_number,
        "published_at": notice.published_at,
        "fetched_at": snapshot.fetched_at,
        "effective_at": notice.published_at,
        "raw_snapshot_id": snapshot.snapshot_id,
        "content_sha256": snapshot.sha256,
        "attachment_snapshot_ids": [],
        "supersedes_event_ids": [],
        "link_confidence": 1.0 if notice.project_number else None,
        "verification_status": verification_status,
        "verification_reason": notice.verification_reason,
    }

    fact_values = {
        "project_name": notice.project_name,
        "buyer_name": notice.buyer_name,
        "published_at": notice.published_at,
        "project_number": notice.project_number,
        "budget_cny": notice.budget_cny,
        "registration_deadline": notice.registration_deadline,
        "bid_deadline": notice.bid_deadline,
        "procurement_method": notice.procurement_method,
    }
    facts: list[dict] = []
    for field_name, field_value in fact_values.items():
        if field_value is None:
            continue
        fragment = notice.evidence_fragments.get(field_name)
        if not fragment:
            continue
        fact_id = deterministic_id("fact", f"{event_id}|{field_name}|{field_value}")
        facts.append(
            {
                "schema_version": SCHEMA_VERSION,
                "fact_id": fact_id,
                "opportunity_id": opportunity_id,
                "event_id": event_id,
                "field_name": field_name,
                "field_value": field_value,
                "fact_type": "OFFICIAL_PUBLIC_FACT",
                "source_id": notice.source_id,
                "source_url": notice.source_url,
                "published_at": notice.published_at,
                "fetched_at": snapshot.fetched_at,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_sha256": snapshot.sha256,
                "parser_version": "medical-pilot-parser-0.1",
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
                "verification_status": verification_status,
                "verification_reason": notice.verification_reason,
                "verified_at": snapshot.fetched_at if verification_status == "VERIFIED" else None,
                "superseded_by_fact_id": None,
                "model_generated": False,
                "model_id": None,
            }
        )
    return event, facts
