#!/usr/bin/env python3
"""Low-frequency CCGP award/deal result sync (Tianjin pilot).

Discovers 中标公告 / 成交公告 for the plan keywords, fetches the newest unseen
result notices, parses them into AWARD_RESULT records and merges them into the
award store. Awards are a separate canonical record type: they never enter the
opportunity pool; the public snapshot uses them to retire awarded projects and
to publish a compact award ledger (supplier / brand / model / price evidence).

Fail-closed rules mirror the opportunity sync: no discovery-only facts, parser
failures are reported (never published), rate limits are respected via the plan
delay and no bypass exists.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medical_channel_pipeline.ccgp_award import (  # noqa: E402
    is_medical_channel_relevant_award,
    merge_award_records,
    normalize_project_number,
    parse_ccgp_award_html,
)
from medical_channel_pipeline.ccgp_detail import fetch_ccgp_detail_html  # noqa: E402
from medical_channel_pipeline.ccgp_discovery import (  # noqa: E402
    BID_TYPE_CODES,
    DiscoveryCandidate,
    build_search_url,
    fetch_search_page,
    parse_search_html,
)
from medical_channel_pipeline.validation import MARKET_ADMIN_CODES  # noqa: E402
from sync_ccgp_query import load_json_arrays, stable_id, write_json  # noqa: E402

DEFAULT_PLAN = ROOT / "data" / "tianjin_award_query_plan.json"
AWARD_NOTICE_TYPES = ("中标公告", "成交公告")
AWARD_RESULT_PATH_MARKERS = ("/zbgg/", "/cjgg/")
AWARD_RESULT_TITLE_MARKERS = ("中标公告", "中标结果公告", "中标（成交）结果公告", "成交公告", "成交结果公告", "结果公告")
NON_RESULT_TITLE_MARKERS = ("更正公告", "变更公告", "终止公告", "废标公告", "流标公告", "招标公告", "磋商公告", "谈判公告", "询价公告", "资格预审公告", "邀请公告", "单一来源")
AWARD_ID_PREFIX = "ccgpaward"


def parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("AWARD_SYNC_AS_OF_TIMEZONE_REQUIRED")
    return parsed


def load_plan(path: Path, *, market_code: str | None = None) -> dict:
    """Load and validate an award query plan.

    ``market_code`` re-targets the same keyword plan at another market (the
    regional refresh runs one plan per province); the plan's own
    ``market_code``/``region`` pair is still validated so a broken file never
    loads silently.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "0.1":
        raise ValueError("AWARD_QUERY_PLAN_INVALID")

    raw_keywords = payload.get("keywords")
    if not isinstance(raw_keywords, list) or not raw_keywords or not all(isinstance(item, str) and item.strip() for item in raw_keywords):
        raise ValueError("AWARD_QUERY_PLAN_KEYWORDS_INVALID")
    keywords: list[str] = []
    for keyword in raw_keywords:
        cleaned = keyword.strip()
        if cleaned not in keywords:
            keywords.append(cleaned)

    notice_types = payload.get("notice_types")
    if not isinstance(notice_types, list) or not notice_types:
        raise ValueError("AWARD_QUERY_PLAN_NOTICE_TYPES_INVALID")
    unsupported = [item for item in notice_types if item not in AWARD_NOTICE_TYPES or item not in BID_TYPE_CODES]
    if unsupported:
        raise ValueError(f"AWARD_QUERY_PLAN_NOTICE_TYPE_UNSUPPORTED:{unsupported}")

    plan_market_code = str(payload.get("market_code") or "").strip().upper()
    if plan_market_code not in MARKET_ADMIN_CODES:
        raise ValueError(f"AWARD_QUERY_PLAN_MARKET_CODE_INVALID:{plan_market_code}")
    plan_region = str(payload.get("region") or "").strip()
    if plan_region != MARKET_ADMIN_CODES[plan_market_code][0]:
        raise ValueError(f"AWARD_QUERY_PLAN_REGION_MARKET_MISMATCH:{plan_region}:{plan_market_code}")
    override = str(market_code or "").strip().upper()
    if override and override not in MARKET_ADMIN_CODES:
        raise ValueError(f"AWARD_QUERY_PLAN_MARKET_CODE_INVALID:{override}")
    market_code = override or plan_market_code
    region = MARKET_ADMIN_CODES[market_code][0]

    lookback_days = int(payload.get("lookback_days", 7))
    max_details = int(payload.get("max_details", 8))
    delay_seconds = float(payload.get("delay_seconds", 4.0))
    if not 1 <= lookback_days <= 31:
        raise ValueError("AWARD_QUERY_PLAN_LOOKBACK_INVALID")
    if not 1 <= max_details <= 30:
        raise ValueError("AWARD_QUERY_PLAN_MAX_DETAILS_INVALID")
    if delay_seconds < 3:
        raise ValueError("AWARD_QUERY_PLAN_DELAY_TOO_LOW")

    return {
        "region": region,
        "market_code": market_code,
        "keywords": keywords,
        "notice_types": list(notice_types),
        "lookback_days": lookback_days,
        "max_details": max_details,
        "delay_seconds": delay_seconds,
    }


def plan_date_window(as_of: datetime, lookback_days: int) -> tuple[str, str]:
    if as_of.tzinfo is None:
        raise ValueError("AWARD_SYNC_AS_OF_TIMEZONE_REQUIRED")
    end = as_of.date()
    start = end - timedelta(days=lookback_days)
    return start.isoformat(), end.isoformat()


def candidate_market_code(region: str | None) -> str | None:
    """Market code proven by the official result-row geography field, else None.

    Mirrors ``sync_regional_ccgp.candidate_market_code``: the search request's
    zoneId is discovery-only, so a row is attributed to a market only when its
    own 地域 field names that province/municipality.
    """
    normalized = "".join(str(region or "").split())
    if not normalized:
        return None
    for code, (name, _admin_code) in MARKET_ADMIN_CODES.items():
        aliases = (name, f"{name}省", f"{name}市")
        if normalized in aliases or normalized.startswith(aliases):
            return code
    return None


def is_award_result_candidate(candidate: DiscoveryCandidate) -> bool:
    """Accept only 中标/成交 result notices (by path, then by title)."""
    title = str(candidate.title or "").strip()
    if any(marker in title for marker in NON_RESULT_TITLE_MARKERS):
        return False
    url = str(candidate.detail_url or "")
    if any(marker in url for marker in AWARD_RESULT_PATH_MARKERS):
        return True
    return any(marker in title for marker in AWARD_RESULT_TITLE_MARKERS)


def existing_source_urls_of(records: list[dict]) -> set[str]:
    urls: set[str] = set()
    for record in records:
        source = record.get("source") if isinstance(record, dict) else None
        url = source.get("url") if isinstance(source, dict) else None
        if isinstance(url, str) and url:
            urls.add(url)
    return urls


def award_candidate_selection_key(candidate: DiscoveryCandidate, existing_urls: set[str] | frozenset[str]) -> tuple[int, str, str]:
    """Unseen result notices first, then newest publication, then URL (sort descending)."""
    return (
        1 if candidate.detail_url not in existing_urls else 0,
        candidate.published_at or "",
        candidate.detail_url,
    )


def select_award_candidates(
    discovered: list[tuple[str, DiscoveryCandidate]],
    existing_records: list[dict],
    max_details: int,
) -> list[tuple[str, DiscoveryCandidate]]:
    existing_urls = frozenset(existing_source_urls_of(existing_records))
    ordered = sorted(
        discovered,
        key=lambda item: award_candidate_selection_key(item[1], existing_urls),
        reverse=True,
    )
    return ordered[:max_details]


def discover_award_candidates(
    *,
    keyword: str,
    region: str,
    notice_types: list[str],
    start_date: str,
    end_date: str,
    delay_seconds: float,
    failures: list[dict],
    fetch_search=fetch_search_page,
    sleep=time.sleep,
    budget_exhausted=lambda: False,
    skipped: list[dict] | None = None,
    market_code: str | None = None,
    region_mismatches: list[dict] | None = None,
) -> list[tuple[str, DiscoveryCandidate]]:
    """Result-notice rows for one keyword. When ``market_code`` is given, rows
    whose own geography field does not prove that market are dropped and
    listed in ``region_mismatches`` (the zoneId filter is not trusted)."""
    discovered: list[tuple[str, DiscoveryCandidate]] = []
    for index, notice_type in enumerate(notice_types):
        if budget_exhausted():
            if skipped is not None:
                skipped.append({"stage": "award_discovery_search", "keyword": keyword, "notice_type": notice_type, "reason": "TIME_BUDGET_EXHAUSTED"})
            continue
        search_url = build_search_url(
            keyword=keyword,
            notice_type=notice_type,
            page_index=1,
            start_date=start_date,
            end_date=end_date,
            region=region,
        )
        try:
            html = fetch_search(search_url)
            candidates = parse_search_html(html, keyword=keyword)
        except Exception as exc:  # noqa: BLE001 - reported, never published
            failures.append(
                {
                    "stage": "award_discovery_search",
                    "region": region,
                    "notice_type": notice_type,
                    "keyword": keyword,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
            candidates = []
        for candidate in candidates:
            if not is_award_result_candidate(candidate):
                continue
            if market_code and candidate_market_code(candidate.region) != market_code:
                if region_mismatches is not None:
                    region_mismatches.append(
                        {
                            "keyword": keyword,
                            "notice_type": notice_type,
                            "title": candidate.title,
                            "url": candidate.detail_url,
                            "candidate_region": candidate.region,
                            "expected_market_code": market_code,
                        }
                    )
                continue
            discovered.append((notice_type, candidate))
        if index + 1 < len(notice_types):
            sleep(delay_seconds)
    return discovered


def merge_discovered(
    discovered_by_url: dict[str, tuple[str, DiscoveryCandidate]],
    discovered_keywords: dict[str, set[str]],
    *,
    keyword: str,
    candidates: list[tuple[str, DiscoveryCandidate]],
) -> None:
    for notice_type, candidate in candidates:
        discovered_by_url.setdefault(candidate.detail_url, (notice_type, candidate))
        discovered_keywords.setdefault(candidate.detail_url, set()).add(keyword)


def pool_project_numbers(records: list[dict]) -> set[str]:
    """Normalised (see ``normalize_project_number``) project numbers in the pool."""
    numbers: set[str] = set()
    for record in records:
        facts = record.get("facts") if isinstance(record, dict) else None
        value = facts.get("project_number") if isinstance(facts, dict) else None
        if isinstance(value, str) and value.strip():
            numbers.add(normalize_project_number(value))
    return numbers


def _directed_candidates(detail_urls: list[str]) -> list[tuple[str, DiscoveryCandidate]]:
    """Operator-supplied result URLs bypass search discovery, never the parser."""
    directed: list[tuple[str, DiscoveryCandidate]] = []
    for url in detail_urls:
        cleaned = str(url or "").strip()
        if not cleaned:
            continue
        notice_type = "成交公告" if "/cjgg/" in cleaned else "中标公告"
        directed.append(
            (
                notice_type,
                DiscoveryCandidate(
                    title="",
                    detail_url=cleaned,
                    published_at=None,
                    buyer_name=None,
                    region=None,
                    notice_type=notice_type,
                    search_keyword="",
                    evidence_status="OPERATOR_DIRECTED",
                ),
            )
        )
    return directed


def run_award_sync(
    *,
    plan: dict,
    as_of: datetime,
    existing_awards: list[dict],
    pool_records: list[dict],
    detail_urls: list[str] | None = None,
    time_budget_seconds: float | None = None,
    fetch_search=fetch_search_page,
    fetch_detail=fetch_ccgp_detail_html,
    sleep=time.sleep,
    clock=time.monotonic,
) -> tuple[list[dict], dict]:
    """Run one bounded award sync. ``time_budget_seconds`` (runtime stages run
    under a hard function timeout) stops issuing new requests once exhausted;
    whatever was verified so far is still merged and reported."""
    start_text, end_text = plan_date_window(as_of, plan["lookback_days"])
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    started = clock()

    def budget_exhausted() -> bool:
        return time_budget_seconds is not None and (clock() - started) >= float(time_budget_seconds)

    failures: list[dict] = []
    skipped: list[dict] = []
    region_mismatches: list[dict] = []
    discovered_by_url: dict[str, tuple[str, DiscoveryCandidate]] = {}
    discovered_keywords: dict[str, set[str]] = {}
    directed = _directed_candidates(list(detail_urls or []))
    discovery_keywords = [] if directed else list(plan["keywords"])
    planned_queries = len(discovery_keywords) * len(plan["notice_types"])

    for index, keyword in enumerate(discovery_keywords):
        candidates = discover_award_candidates(
            keyword=keyword,
            region=plan["region"],
            notice_types=plan["notice_types"],
            start_date=start_text,
            end_date=end_text,
            delay_seconds=plan["delay_seconds"],
            failures=failures,
            fetch_search=fetch_search,
            sleep=sleep,
            budget_exhausted=budget_exhausted,
            skipped=skipped,
            market_code=plan["market_code"],
            region_mismatches=region_mismatches,
        )
        merge_discovered(discovered_by_url, discovered_keywords, keyword=keyword, candidates=candidates)
        if index + 1 < len(discovery_keywords) and not budget_exhausted():
            sleep(plan["delay_seconds"])
    if directed:
        merge_discovered(discovered_by_url, discovered_keywords, keyword="__operator_directed__", candidates=directed)

    discovery_failures = [item for item in failures if item.get("stage") == "award_discovery_search"]
    discovery_success_count = max(0, planned_queries - len(discovery_failures) - len(skipped))
    discovered = list(discovered_by_url.values())
    selected = select_award_candidates(discovered, existing_awards, plan["max_details"])

    new_awards: list[dict] = []
    out_of_scope: list[dict] = []
    for notice_type, candidate in selected:
        if budget_exhausted():
            skipped.append({"stage": "award_detail", "url": candidate.detail_url, "reason": "TIME_BUDGET_EXHAUSTED"})
            continue
        try:
            sleep(plan["delay_seconds"])
            html = fetch_detail(candidate.detail_url)
            record = parse_ccgp_award_html(
                html,
                source_url=candidate.detail_url,
                observed_at=observed_at,
                award_id=stable_id(AWARD_ID_PREFIX, candidate.detail_url),
                market_code=plan["market_code"],
            )
        except Exception as exc:  # noqa: BLE001 - reported, never published
            failures.append(
                {
                    "stage": "award_detail",
                    "region": plan["region"],
                    "notice_type": notice_type,
                    "keywords": sorted(discovered_keywords.get(candidate.detail_url, set())),
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
            continue
        if not is_medical_channel_relevant_award(record):
            out_of_scope.append(
                {
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "project_number": record["facts"]["project_number"],
                    "reason": "MEDICAL_CHANNEL_SCOPE_EXCLUDED",
                }
            )
            continue
        new_awards.append(record)

    merged_awards = merge_award_records(existing_awards, new_awards)
    pool_numbers = pool_project_numbers(pool_records)
    matched_pool_projects = sorted(
        {
            record["facts"]["project_number"]
            for record in merged_awards
            if normalize_project_number(record["facts"]["project_number"]) in pool_numbers
        }
    )
    if directed:
        publish_allowed = bool(new_awards) or not failures
        publish_gate_reason = "OK_OPERATOR_DIRECTED" if publish_allowed else "ALL_DIRECTED_DETAILS_FAILED"
    else:
        publish_allowed = discovery_success_count > 0
        publish_gate_reason = "OK" if publish_allowed else "ALL_AWARD_DISCOVERY_QUERIES_FAILED"

    report = {
        "schema_version": "0.1",
        "record_type": "AWARD_RESULT",
        "observed_at": observed_at,
        "region": plan["region"],
        "market_code": plan["market_code"],
        "start_date": start_text,
        "end_date": end_text,
        "keywords": plan["keywords"],
        "notice_types": plan["notice_types"],
        "discovery_skipped_for_operator_directed_urls": bool(directed),
        "operator_directed_url_count": len(directed),
        "planned_discovery_query_count": planned_queries,
        "discovery_success_count": discovery_success_count,
        "unique_discovered_result_count": len(discovered),
        "region_mismatch_count": len(region_mismatches),
        "region_mismatches": region_mismatches[:20],
        "selected_detail_count": len(selected),
        "new_award_record_count": len(new_awards),
        "out_of_scope_count": len(out_of_scope),
        "out_of_scope": out_of_scope,
        "merged_award_record_count": len(merged_awards),
        "pool_record_count": len(pool_records),
        "matched_pool_project_count": len(matched_pool_projects),
        "matched_pool_project_numbers": matched_pool_projects,
        "failure_count": len(failures),
        "failures": failures,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "time_budget_seconds": time_budget_seconds,
        "time_budget_exhausted": budget_exhausted(),
        "elapsed_seconds": round(clock() - started, 3),
        "publish_allowed": publish_allowed,
        "publish_gate_reason": publish_gate_reason,
        "policy": {
            "requests_stop_when_time_budget_is_exhausted": True,
            "awards_are_a_separate_record_type": True,
            "awards_never_enter_opportunity_pool": True,
            "unseen_result_notices_verified_first": True,
            "amount_scale_requires_explicit_unit": True,
            "construction_only_awards_excluded": True,
            "previous_award_state_is_preserved": True,
            "parse_failures_are_reported_not_published": True,
            "rate_limit_bypass": False,
            "minimum_request_delay_seconds": plan["delay_seconds"],
            "row_geography_must_prove_market": True,
        },
    }
    return merged_awards, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Low-frequency CCGP 中标/成交 result sync -> AWARD_RESULT records.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--as-of", default=None, help="Optional ISO-8601 timestamp with timezone; defaults to now.")
    parser.add_argument("--existing-awards-input", action="append", type=Path, default=[])
    parser.add_argument("--records-input", action="append", type=Path, default=[], help="Opportunity records used only to report pool matches.")
    parser.add_argument(
        "--detail-url",
        action="append",
        default=[],
        help="Repeatable. Parse these CCGP result notice URLs directly instead of running search discovery (operator seeding / backfill).",
    )
    parser.add_argument(
        "--market-code",
        default=None,
        help="Re-target the plan's keywords at another market (BJ/TJ/HE/LN/JL/HL); the plan file itself must still be valid.",
    )
    parser.add_argument("--awards-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    args = parser.parse_args()

    plan = load_plan(args.plan, market_code=args.market_code)
    as_of = parse_as_of(args.as_of)
    existing_awards = load_json_arrays(args.existing_awards_input, label="existing award records")
    pool_records = load_json_arrays(args.records_input, label="opportunity records")

    merged_awards, report = run_award_sync(
        plan=plan,
        as_of=as_of,
        existing_awards=existing_awards,
        pool_records=pool_records,
        detail_urls=args.detail_url,
    )
    write_json(args.awards_output, merged_awards)
    write_json(args.report_output, report)
    print(
        f"queries_ok={report['discovery_success_count']}/{report['planned_discovery_query_count']} "
        f"discovered={report['unique_discovered_result_count']} selected={report['selected_detail_count']} "
        f"new_awards={report['new_award_record_count']} out_of_scope={report['out_of_scope_count']} "
        f"merged={report['merged_award_record_count']} pool_matches={report['matched_pool_project_count']} "
        f"failures={report['failure_count']} publish_allowed={report['publish_allowed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
