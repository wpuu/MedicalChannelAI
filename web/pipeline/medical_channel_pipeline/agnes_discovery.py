from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse


MAX_ANCHORS_PER_PROMPT = 80
MAX_TITLE_LENGTH = 220
ALLOWED_SIGNAL_TYPES = {
    "DEMAND_RESEARCH",
    "SUPPLIER_RECRUITMENT",
    "TEST_ENTERPRISE_RECRUITMENT",
    "ARGUMENTATION_INVITATION",
    "PURCHASE_INTENTION",
    "OTHER_PREPROCUREMENT",
}


@dataclass(frozen=True)
class OfficialAnchor:
    title: str
    url: str


@dataclass(frozen=True)
class AgnesDiscoveryCandidate:
    title: str
    url: str
    signal_type: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class AgnesParseResult:
    candidates: tuple[AgnesDiscoveryCandidate, ...]
    raw_candidate_count: int
    rejected_ungrounded_count: int
    rejected_invalid_count: int


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._text: list[str] = []
        self.rows: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        title = re.sub(r"\s+", " ", "".join(self._text)).strip()
        if title:
            self.rows.append((title, self._href))
        self._href = None
        self._text = []


def canonical_https_url(value: str) -> str | None:
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    normalized = parsed._replace(
        scheme="https",
        netloc=parsed.netloc.lower(),
        fragment="",
    )
    return urlunparse(normalized)


def extract_official_anchors(
    html: str,
    *,
    base_url: str,
    allowed_hosts: set[str],
) -> list[OfficialAnchor]:
    base = canonical_https_url(base_url)
    if not base:
        raise ValueError("AGNES_DISCOVERY_BASE_URL_INVALID")
    normalized_hosts = {item.strip().lower() for item in allowed_hosts if item.strip()}
    if urlparse(base).hostname not in normalized_hosts:
        raise ValueError("AGNES_DISCOVERY_BASE_HOST_NOT_ALLOWED")

    parser = _AnchorParser()
    parser.feed(html)
    seen: set[str] = set()
    anchors: list[OfficialAnchor] = []
    for title, href in parser.rows:
        url = canonical_https_url(urljoin(base, href))
        if not url:
            continue
        if (urlparse(url).hostname or "").lower() not in normalized_hosts:
            continue
        if url in seen:
            continue
        seen.add(url)
        anchors.append(OfficialAnchor(title=title[:MAX_TITLE_LENGTH], url=url))
    return anchors


def build_agnes_discovery_messages(
    *,
    source_name: str,
    anchors: list[OfficialAnchor],
) -> list[dict[str, str]]:
    if not anchors:
        raise ValueError("AGNES_DISCOVERY_ANCHORS_EMPTY")
    if len(anchors) > MAX_ANCHORS_PER_PROMPT:
        raise ValueError("AGNES_DISCOVERY_ANCHOR_BATCH_TOO_LARGE")
    payload = [
        {"title": item.title, "url": item.url}
        for item in anchors
    ]
    system = (
        "你是医疗采购前期商机发现器。你的任务不是总结招标，而是从医院/机构官方索引页链接中"
        "找出供应商仍可能影响需求、测试、论证、方案或采购准备的前期窗口。"
        "只允许选择输入列表中真实存在的URL；禁止补全、改写或猜测URL。"
        "优先识别：需求调研、供应商征集、测试企业征集、论证邀请、采购意向及其他明确的采购前期信号。"
        "排除：正式招标公告、成交/中标结果、评分细则、招聘、人事、党建、新闻宣传、纯制度通知。"
        "不要把模型判断当作已验证事实。输出必须是严格JSON，不要Markdown。"
    )
    user = json.dumps(
        {
            "source": source_name,
            "anchors": payload,
            "output_schema": {
                "candidates": [
                    {
                        "title": "必须来自输入或忠实对应输入标题",
                        "url": "必须与输入URL完全一致",
                        "signal_type": sorted(ALLOWED_SIGNAL_TYPES),
                        "confidence": "0到1",
                        "reason": "不超过80个汉字，只说明为什么值得进入后续官方核验",
                    }
                ]
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _json_text(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_agnes_discovery_content(
    content: str,
    *,
    allowed_anchors: list[OfficialAnchor],
) -> AgnesParseResult:
    allowed_by_url = {item.url: item for item in allowed_anchors}
    try:
        payload = json.loads(_json_text(content))
    except json.JSONDecodeError as exc:
        raise ValueError("AGNES_DISCOVERY_RESPONSE_NOT_JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise ValueError("AGNES_DISCOVERY_RESPONSE_SCHEMA_INVALID")

    accepted: list[AgnesDiscoveryCandidate] = []
    seen: set[str] = set()
    rejected_ungrounded = 0
    rejected_invalid = 0
    rows = payload["candidates"]
    for row in rows:
        if not isinstance(row, dict):
            rejected_invalid += 1
            continue
        url = canonical_https_url(str(row.get("url") or ""))
        if not url or url not in allowed_by_url:
            rejected_ungrounded += 1
            continue
        signal_type = str(row.get("signal_type") or "").strip().upper()
        if signal_type not in ALLOWED_SIGNAL_TYPES:
            rejected_invalid += 1
            continue
        try:
            confidence = float(row.get("confidence"))
        except (TypeError, ValueError):
            rejected_invalid += 1
            continue
        if not 0 <= confidence <= 1:
            rejected_invalid += 1
            continue
        reason = re.sub(r"\s+", " ", str(row.get("reason") or "")).strip()
        if not reason:
            rejected_invalid += 1
            continue
        if url in seen:
            continue
        seen.add(url)
        anchor = allowed_by_url[url]
        accepted.append(
            AgnesDiscoveryCandidate(
                title=anchor.title,
                url=url,
                signal_type=signal_type,
                confidence=confidence,
                reason=reason[:160],
            )
        )

    return AgnesParseResult(
        candidates=tuple(accepted),
        raw_candidate_count=len(rows),
        rejected_ungrounded_count=rejected_ungrounded,
        rejected_invalid_count=rejected_invalid,
    )


def known_gold_urls_from_snapshot(
    snapshot: dict[str, Any],
    *,
    allowed_hosts: set[str],
) -> set[str]:
    normalized_hosts = {item.lower() for item in allowed_hosts}
    pool = snapshot.get("opportunity_pool")
    cards = snapshot.get("cards")
    rows = pool if isinstance(pool, list) and pool else cards if isinstance(cards, list) else []
    result: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        facts = row.get("facts")
        if not isinstance(facts, dict) or facts.get("verification_status") != "VERIFIED":
            continue
        for raw_url in row.get("evidence_source_urls") or []:
            if not isinstance(raw_url, str):
                continue
            url = canonical_https_url(raw_url)
            if not url:
                continue
            if (urlparse(url).hostname or "").lower() in normalized_hosts:
                result.add(url)
    return result


def discovery_benchmark_metrics(
    parse_results: list[AgnesParseResult],
    *,
    gold_urls: set[str],
) -> dict[str, Any]:
    candidate_urls: set[str] = set()
    raw_count = 0
    rejected_ungrounded = 0
    rejected_invalid = 0
    for result in parse_results:
        candidate_urls.update(item.url for item in result.candidates)
        raw_count += result.raw_candidate_count
        rejected_ungrounded += result.rejected_ungrounded_count
        rejected_invalid += result.rejected_invalid_count

    known_hits = candidate_urls & gold_urls
    recall = len(known_hits) / len(gold_urls) if gold_urls else None
    grounded_rate = (
        (raw_count - rejected_ungrounded) / raw_count
        if raw_count
        else 1.0
    )
    format_valid_rate = (
        (raw_count - rejected_ungrounded - rejected_invalid) / raw_count
        if raw_count
        else 1.0
    )
    score = None
    if recall is not None:
        score = round(100 * (0.75 * recall + 0.20 * grounded_rate + 0.05 * format_valid_rate), 1)

    return {
        "gold_known_count": len(gold_urls),
        "ai_candidate_count": len(candidate_urls),
        "known_hit_count": len(known_hits),
        "known_recall": round(recall, 4) if recall is not None else None,
        "grounded_rate": round(grounded_rate, 4),
        "format_valid_rate": round(format_valid_rate, 4),
        "rejected_ungrounded_count": rejected_ungrounded,
        "rejected_invalid_count": rejected_invalid,
        "novel_candidate_count": len(candidate_urls - gold_urls),
        "known_hit_urls": sorted(known_hits),
        "novel_candidate_urls": sorted(candidate_urls - gold_urls),
        "discovery_score": score,
        "score_definition": "75% known-set recall + 20% URL grounding + 5% response format validity",
        "score_scope": "AI_DISCOVERY_SHADOW_BENCHMARK_ONLY",
    }
