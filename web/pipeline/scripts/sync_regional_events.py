#!/usr/bin/env python3
"""Multi-market CCGP 更正/终止 monitoring (北京/河北/辽宁/吉林/黑龙江).

Tianjin scans events per project (two searches per active project number).
That does not scale to the regional pool, so this sync discovers 更正公告 /
终止公告 rows with the shared keyword plan — one market at a time — and only
spends detail requests on rows whose title names a pool project (by project
number or by project name). An event is kept only when the official detail's
project number matches a pool project of that market, and every event is
stamped with the market so the publisher can key it (market, number).

Fail-closed rules: search-row geography must prove the market, official
detail required (the discovery-only fallback is used solely when the title
already quotes the project number), unknown numbers are dropped, network
conditions are reported and never raise.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from medical_channel_pipeline.ccgp_award import normalize_project_number  # noqa: E402
from medical_channel_pipeline.ccgp_detail import fetch_ccgp_detail_html  # noqa: E402
from medical_channel_pipeline.ccgp_discovery import (  # noqa: E402
    DiscoveryCandidate,
    build_search_url,
    fetch_search_page,
    parse_search_html,
)
from medical_channel_pipeline.ccgp_events import parse_ccgp_event_html  # noqa: E402
from medical_channel_pipeline.state import merge_notice_events  # noqa: E402
from medical_channel_pipeline.validation import MARKET_ADMIN_CODES  # noqa: E402
from sync_ccgp_awards import candidate_market_code, load_json_arrays, parse_as_of, plan_date_window, write_json  # noqa: E402
from sync_ccgp_query import discovery_event, stable_id  # noqa: E402

DEFAULT_PLAN = PIPELINE_ROOT / "data" / "regional_event_query_plan.json"
DEFAULT_POOL_RECORDS = PIPELINE_ROOT / "data" / "regional_live_ccgp_records.json"
EVENT_NOTICE_TYPES = {"更正公告": "CORRECTION", "终止公告": "TERMINATION"}
# Short numbers such as Beijing's "202601" would also match inside dates or
# other numbers; those projects are matched by name only.
MIN_NUMBER_MATCH_CHARS = 8
_TITLE_SUFFIX_RE = re.compile(
    r"(?:采购|招标|结果|中标|成交)?(?:更正|终止|废标|流标|变更|澄清|暂停)公告(?:[（(]第[^）)]{1,6}次[）)])?$"
)
_FULLWIDTH_ASCII = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}
_FULLWIDTH_ASCII[0x3000] = 0x20


def load_plan(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    codes: list[str] = []
    for item in payload.get("market_codes") or []:
        code = str(item or "").strip().upper()
        if code not in MARKET_ADMIN_CODES:
            raise ValueError(f"REGIONAL_EVENT_PLAN_MARKET_CODE_INVALID:{code}")
        if code == "TJ":
            raise ValueError("REGIONAL_EVENT_PLAN_TIANJIN_USES_PER_PROJECT_SCANS")
        if code not in codes:
            codes.append(code)
    if not codes:
        raise ValueError("REGIONAL_EVENT_PLAN_MARKET_CODES_INVALID")
    keywords = [str(item).strip() for item in payload.get("keywords") or [] if str(item).strip()]
    if not keywords:
        raise ValueError("REGIONAL_EVENT_PLAN_KEYWORDS_REQUIRED")
    notice_types = [str(item) for item in payload.get("notice_types") or []]
    if not notice_types or any(item not in EVENT_NOTICE_TYPES for item in notice_types):
        raise ValueError("REGIONAL_EVENT_PLAN_NOTICE_TYPES_INVALID")
    lookback_days = int(payload.get("lookback_days", 7))
    if not 1 <= lookback_days <= 31:
        raise ValueError("REGIONAL_EVENT_PLAN_LOOKBACK_INVALID")
    delay_seconds = float(payload.get("delay_seconds", 4.0))
    if delay_seconds < 3:
        raise ValueError("REGIONAL_EVENT_PLAN_DELAY_TOO_LOW")
    budget = payload.get("per_market_time_budget_seconds")
    if budget is not None:
        budget = float(budget)
        if budget < 30:
            raise ValueError("REGIONAL_EVENT_PLAN_TIME_BUDGET_TOO_LOW")
    return {
        "schema_version": payload.get("schema_version", "0.1"),
        "market_codes": codes,
        "keywords": keywords,
        "notice_types": notice_types,
        "lookback_days": lookback_days,
        "max_details": max(1, int(payload.get("max_details", 10))),
        "delay_seconds": delay_seconds,
        "per_market_time_budget_seconds": budget,
        "min_name_match_chars": max(6, int(payload.get("min_name_match_chars", 10))),
        "policy": payload.get("policy") or {},
    }


def normalize_title_text(value: object) -> str:
    """Half-width, whitespace-free, lower-cased text for title/name matching."""
    text = str(value or "").translate(_FULLWIDTH_ASCII)
    return re.sub(r"\s+", "", text).lower()


def title_core(title: object) -> str:
    """Title without the trailing 更正/终止公告 suffix (normalised)."""
    return _TITLE_SUFFIX_RE.sub("", normalize_title_text(title))


def pool_index(pool_records: list[dict], market_code: str, as_of: datetime, *, min_name_chars: int) -> list[dict]:
    """Pool projects of ``market_code`` still open at ``as_of`` (deadline unknown or future)."""
    entries: dict[str, dict] = {}
    for record in pool_records:
        facts = record.get("facts") if isinstance(record, dict) else None
        if not isinstance(facts, dict):
            continue
        if str(facts.get("market_code") or "").strip().upper() != market_code:
            continue
        number = normalize_project_number(facts.get("project_number"))
        if not number:
            continue
        deadline = facts.get("bid_deadline")
        if isinstance(deadline, str) and deadline:
            try:
                if datetime.fromisoformat(deadline) <= as_of:
                    continue
            except ValueError:
                pass
        entry = entries.setdefault(number, {"project_number": number, "names": set()})
        name = normalize_title_text(facts.get("project_name"))
        if len(name) >= min_name_chars:
            entry["names"].add(name)
    return [
        {"project_number": entry["project_number"], "names": sorted(entry["names"])}
        for entry in entries.values()
    ]


def match_candidate(candidate: DiscoveryCandidate, index: list[dict]) -> tuple[str, str] | None:
    """``("NUMBER", project_number)`` when the title quotes a pool number,
    ``("NAME", project_number)`` when it contains (or is contained in) a pool
    project name, else ``None`` — no detail request without a match."""
    title = normalize_title_text(candidate.title)
    if not title:
        return None
    for entry in index:
        number = entry["project_number"]
        if len(number) >= MIN_NUMBER_MATCH_CHARS and number in title:
            return "NUMBER", number
    core = title_core(candidate.title)
    for entry in index:
        for name in entry["names"]:
            if name in title or (len(core) >= 10 and core in name):
                return "NAME", entry["project_number"]
    return None


def candidate_event_type(candidate: DiscoveryCandidate, query_notice_type: str) -> str:
    """Event type from the row's own notice type / URL path, else the query's."""
    row_type = str(candidate.notice_type or "").strip()
    if row_type in EVENT_NOTICE_TYPES:
        return EVENT_NOTICE_TYPES[row_type]
    url = str(candidate.detail_url or "")
    if "/fblbgg/" in url or "/zzgg/" in url:
        return "TERMINATION"
    if "/gzgg/" in url:
        return "CORRECTION"
    return EVENT_NOTICE_TYPES[query_notice_type]


def selection_key(item: dict, existing_urls: set[str]) -> tuple[int, int, str, str]:
    candidate: DiscoveryCandidate = item["candidate"]
    return (
        1 if candidate.detail_url not in existing_urls else 0,
        1 if item["match_kind"] == "NUMBER" else 0,
        candidate.published_at or "",
        candidate.detail_url,
    )


def run_market_event_sync(
    *,
    plan: dict,
    market_code: str,
    as_of: datetime,
    existing_events: list[dict],
    pool_records: list[dict],
    time_budget_seconds: float | None = None,
    fetch_search=fetch_search_page,
    fetch_detail=fetch_ccgp_detail_html,
    sleep=time.sleep,
    clock=time.monotonic,
) -> tuple[list[dict], dict]:
    """Discover and verify 更正/终止 events for one market. Returns the new
    (verified, market-stamped) events and a report."""
    region = MARKET_ADMIN_CODES[market_code][0]
    start_text, end_text = plan_date_window(as_of, plan["lookback_days"])
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    started = clock()

    def budget_exhausted() -> bool:
        return time_budget_seconds is not None and (clock() - started) >= float(time_budget_seconds)

    index = pool_index(pool_records, market_code, as_of, min_name_chars=plan["min_name_match_chars"])
    existing_urls = {str(event.get("source_url") or "") for event in existing_events}
    failures: list[dict] = []
    skipped: list[dict] = []
    region_mismatches: list[dict] = []
    matched_by_url: dict[str, dict] = {}
    discovered_count = 0
    unmatched_titles = 0
    planned_queries = len(plan["keywords"]) * len(plan["notice_types"])
    query_success = 0

    for keyword in plan["keywords"]:
        for notice_type in plan["notice_types"]:
            if budget_exhausted():
                skipped.append({"stage": "event_discovery_search", "keyword": keyword, "notice_type": notice_type, "reason": "TIME_BUDGET_EXHAUSTED"})
                continue
            search_url = build_search_url(
                keyword=keyword,
                notice_type=notice_type,
                page_index=1,
                start_date=start_text,
                end_date=end_text,
                region=region,
            )
            try:
                html = fetch_search(search_url)
                candidates = parse_search_html(html, keyword=keyword)
                query_success += 1
            except Exception as exc:  # noqa: BLE001 - reported, never published
                failures.append(
                    {
                        "stage": "event_discovery_search",
                        "region": region,
                        "notice_type": notice_type,
                        "keyword": keyword,
                        "error": type(exc).__name__,
                        "message": str(exc)[:300],
                    }
                )
                candidates = []
            for candidate in candidates:
                discovered_count += 1
                if candidate_market_code(candidate.region) != market_code:
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
                match = match_candidate(candidate, index)
                if match is None:
                    unmatched_titles += 1
                    continue
                matched_by_url.setdefault(
                    candidate.detail_url,
                    {
                        "candidate": candidate,
                        "notice_type": notice_type,
                        "event_type": candidate_event_type(candidate, notice_type),
                        "match_kind": match[0],
                        "pool_project_number": match[1],
                        "keywords": set(),
                    },
                )["keywords"].add(keyword)
            sleep(plan["delay_seconds"])

    ordered = sorted(matched_by_url.values(), key=lambda item: selection_key(item, existing_urls), reverse=True)
    selected = ordered[:plan["max_details"]]
    pool_numbers = {entry["project_number"] for entry in index}

    new_events: list[dict] = []
    number_mismatches: list[dict] = []
    for item in selected:
        candidate: DiscoveryCandidate = item["candidate"]
        if budget_exhausted():
            skipped.append({"stage": "event_detail", "url": candidate.detail_url, "reason": "TIME_BUDGET_EXHAUSTED"})
            continue
        event = None
        try:
            sleep(plan["delay_seconds"])
            detail_html = fetch_detail(candidate.detail_url)
            event = parse_ccgp_event_html(
                detail_html,
                source_url=candidate.detail_url,
                observed_at=observed_at,
                event_id=stable_id(item["event_type"].lower(), candidate.detail_url),
            )
        except Exception as exc:  # noqa: BLE001 - reported, never published
            failures.append(
                {
                    "stage": "event_detail",
                    "region": region,
                    "notice_type": item["notice_type"],
                    "keywords": sorted(item["keywords"]),
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
            if item["match_kind"] == "NUMBER" and candidate.published_at:
                # The title itself quotes the pool project number: official
                # discovery is enough to suppress the stale card (never to
                # rewrite facts), exactly like the Tianjin per-project scan.
                event = discovery_event(
                    candidate,
                    project_number=item["pool_project_number"],
                    event_type=item["event_type"],
                    observed_at=observed_at,
                )
        if event is None:
            continue
        parsed_number = normalize_project_number(event["project_number"])
        if parsed_number not in pool_numbers:
            number_mismatches.append(
                {
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "detail_project_number": event["project_number"],
                    "matched_pool_project_number": item["pool_project_number"],
                    "match_kind": item["match_kind"],
                    "reason": "DETAIL_PROJECT_NUMBER_NOT_IN_POOL",
                }
            )
            continue
        event["market_code"] = market_code
        new_events.append(event)

    publish_allowed = query_success > 0
    report = {
        "schema_version": "0.1",
        "record_type": "NOTICE_EVENT",
        "observed_at": observed_at,
        "region": region,
        "market_code": market_code,
        "start_date": start_text,
        "end_date": end_text,
        "keywords": plan["keywords"],
        "notice_types": plan["notice_types"],
        "planned_discovery_query_count": planned_queries,
        "discovery_success_count": query_success,
        "open_pool_project_count": len(index),
        "discovered_row_count": discovered_count,
        "region_mismatch_count": len(region_mismatches),
        "region_mismatches": region_mismatches[:20],
        "unmatched_title_count": unmatched_titles,
        "matched_candidate_count": len(matched_by_url),
        "matched_candidates": [
            {
                "title": item["candidate"].title,
                "url": item["candidate"].detail_url,
                "published_at": item["candidate"].published_at,
                "match_kind": item["match_kind"],
                "pool_project_number": item["pool_project_number"],
            }
            for item in ordered[:40]
        ],
        "selected_detail_count": len(selected),
        "new_event_count": len(new_events),
        "new_events": [
            {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "scope": event.get("scope", "PROJECT"),
                "packages": event.get("packages") or [],
                "project_number": event["project_number"],
                "published_at": event["published_at"],
                "url": event["source_url"],
            }
            for event in new_events
        ],
        "number_mismatch_count": len(number_mismatches),
        "number_mismatches": number_mismatches,
        "failure_count": len(failures),
        "failures": failures,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "time_budget_seconds": time_budget_seconds,
        "time_budget_exhausted": budget_exhausted(),
        "elapsed_seconds": round(clock() - started, 3),
        "publish_allowed": publish_allowed,
        "publish_gate_reason": "OK" if publish_allowed else "ALL_EVENT_DISCOVERY_QUERIES_FAILED",
        "policy": {
            "keyword_discovery_not_per_project_search": True,
            "row_geography_must_prove_market": True,
            "detail_fetched_only_for_titles_matching_pool_number_or_name": True,
            "event_kept_only_when_detail_project_number_matches_pool": True,
            "discovery_only_fallback_requires_project_number_in_title": True,
            "every_event_carries_market_code": True,
            "package_scoped_notices_never_suppress_the_opportunity": True,
            "requests_stop_when_time_budget_is_exhausted": True,
            "rate_limit_bypass": False,
            "minimum_request_delay_seconds": plan["delay_seconds"],
        },
    }
    return new_events, report


def run_regional_event_sync(
    *,
    plan_path: Path,
    as_of: datetime,
    existing_events: list[dict],
    pool_records: list[dict],
    market_codes: list[str] | None = None,
    fetch_search=None,
    fetch_detail=None,
    sleep=time.sleep,
    clock=time.monotonic,
) -> tuple[list[dict], dict]:
    plan = load_plan(plan_path)
    codes = [code.strip().upper() for code in (market_codes or plan["market_codes"])]
    unknown = [code for code in codes if code not in plan["market_codes"]]
    if unknown:
        raise ValueError(f"REGIONAL_EVENT_MARKET_NOT_IN_PLAN:{unknown}")

    kwargs = {}
    if fetch_search is not None:
        kwargs["fetch_search"] = fetch_search
    if fetch_detail is not None:
        kwargs["fetch_detail"] = fetch_detail

    merged = list(existing_events)
    reports: dict[str, dict] = {}
    started = clock()
    for index, code in enumerate(codes):
        new_events, report = run_market_event_sync(
            plan=plan,
            market_code=code,
            as_of=as_of,
            existing_events=merged,
            pool_records=pool_records,
            time_budget_seconds=plan["per_market_time_budget_seconds"],
            sleep=sleep,
            clock=clock,
            **kwargs,
        )
        merged = merge_notice_events(merged, new_events)
        reports[code] = report
        if index + 1 < len(codes):
            sleep(plan["delay_seconds"])

    by_market: dict[str, int] = {}
    for event in merged:
        market = str(event.get("market_code") or "").strip().upper() or "UNKNOWN"
        by_market[market] = by_market.get(market, 0) + 1
    publish_allowed = any(item["publish_allowed"] for item in reports.values())
    combined = {
        "schema_version": "0.1",
        "record_type": "NOTICE_EVENT",
        "observed_at": as_of.astimezone(timezone.utc).isoformat(),
        "market_codes": codes,
        "per_market_time_budget_seconds": plan["per_market_time_budget_seconds"],
        "elapsed_seconds": round(clock() - started, 3),
        "new_event_count": sum(item["new_event_count"] for item in reports.values()),
        "matched_candidate_count": sum(item["matched_candidate_count"] for item in reports.values()),
        "number_mismatch_count": sum(item["number_mismatch_count"] for item in reports.values()),
        "region_mismatch_count": sum(item["region_mismatch_count"] for item in reports.values()),
        "failure_count": sum(item["failure_count"] for item in reports.values()),
        "merged_event_count": len(merged),
        "merged_event_count_by_market": dict(sorted(by_market.items())),
        "markets_publish_allowed": {code: item["publish_allowed"] for code, item in reports.items()},
        "publish_allowed": publish_allowed,
        "publish_gate_reason": "OK" if publish_allowed else "ALL_MARKETS_EVENT_DISCOVERY_FAILED",
        "markets": reports,
        "policy": {
            "one_market_at_a_time_same_keyword_plan": True,
            "row_geography_must_prove_market": True,
            "every_event_carries_market_code": True,
            "previous_event_state_is_preserved": True,
            "network_failures_never_raise": True,
        },
    }
    return merged, combined


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-market CCGP 更正/终止 monitoring -> notice events with market identity.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--as-of", default=None, help="Optional ISO-8601 timestamp with timezone; defaults to now.")
    parser.add_argument("--market-code", action="append", default=[], help="Repeatable subset of the plan's market_codes.")
    parser.add_argument("--existing-events-input", action="append", type=Path, default=[])
    parser.add_argument(
        "--records-input",
        action="append",
        type=Path,
        default=None,
        help="Opportunity records whose open projects are monitored (defaults to the regional live store).",
    )
    parser.add_argument("--events-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    args = parser.parse_args()

    as_of = parse_as_of(args.as_of)
    existing_events = load_json_arrays(args.existing_events_input, label="existing notice events")
    record_paths = args.records_input if args.records_input is not None else (
        [DEFAULT_POOL_RECORDS] if DEFAULT_POOL_RECORDS.exists() else []
    )
    pool_records = load_json_arrays(record_paths, label="opportunity records")

    merged, report = run_regional_event_sync(
        plan_path=args.plan,
        as_of=as_of,
        existing_events=existing_events,
        pool_records=pool_records,
        market_codes=args.market_code or None,
    )
    write_json(args.events_output, merged)
    write_json(args.report_output, report)
    for code, item in report["markets"].items():
        print(
            f"{code}: queries_ok={item['discovery_success_count']}/{item['planned_discovery_query_count']} "
            f"open_projects={item['open_pool_project_count']} rows={item['discovered_row_count']} "
            f"matched={item['matched_candidate_count']} selected={item['selected_detail_count']} "
            f"new_events={item['new_event_count']} number_mismatch={item['number_mismatch_count']} "
            f"failures={item['failure_count']} publish_allowed={item['publish_allowed']} elapsed={item['elapsed_seconds']}s"
        )
    print(
        f"merged={report['merged_event_count']} by_market={report['merged_event_count_by_market']} "
        f"publish_allowed={report['publish_allowed']} elapsed={report['elapsed_seconds']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
