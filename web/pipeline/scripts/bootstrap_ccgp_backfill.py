#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medical_channel_pipeline.ccgp_detail import fetch_ccgp_detail_html  # noqa: E402
from medical_channel_pipeline.state import (  # noqa: E402
    active_ccgp_project_numbers,
    merge_canonical_records,
    merge_notice_events,
)
from sync_ccgp_query import (  # noqa: E402
    VERIFIED_NOTICE_ADAPTERS,
    discover_candidates,
    scan_events,
    stable_id,
)
from sync_tianjin_plan import load_plan  # noqa: E402

DATA_ROOT = ROOT / "data"
SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_CHUNK_DAYS = 7
DEFAULT_MAX_CANDIDATES = 120
DEFAULT_MAX_EVENT_WATCH_PROJECTS = 100


def build_date_windows(end_date: date, *, lookback_days: int, chunk_days: int) -> list[tuple[date, date]]:
    if not 1 <= lookback_days <= 60:
        raise ValueError("lookback_days must be between 1 and 60")
    if not 1 <= chunk_days <= 14:
        raise ValueError("chunk_days must be between 1 and 14")

    first = end_date - timedelta(days=lookback_days - 1)
    windows: list[tuple[date, date]] = []
    cursor = first
    while cursor <= end_date:
        window_end = min(end_date, cursor + timedelta(days=chunk_days - 1))
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--as-of must include a timezone offset")
    return parsed


def load_array(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"expected JSON array: {path}")
    return payload


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-time fail-closed Tianjin CCGP history backfill. Produces candidate canonical "
            "state only; it never publishes a public snapshot or writes Vercel Runtime Cache."
        )
    )
    parser.add_argument("--as-of", help="timezone-aware ISO timestamp; defaults to now")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--chunk-days", type=int, default=DEFAULT_CHUNK_DAYS)
    parser.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--max-event-watch-projects", type=int, default=DEFAULT_MAX_EVENT_WATCH_PROJECTS)
    parser.add_argument("--records-output", required=True, type=Path)
    parser.add_argument("--events-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    args = parser.parse_args()

    if not 1 <= args.max_candidates <= 200:
        raise ValueError("--max-candidates must be between 1 and 200")
    if not 1 <= args.max_event_watch_projects <= 200:
        raise ValueError("--max-event-watch-projects must be between 1 and 200")

    as_of = parse_as_of(args.as_of)
    local_end = as_of.astimezone(SHANGHAI).date()
    windows = build_date_windows(local_end, lookback_days=args.lookback_days, chunk_days=args.chunk_days)
    plan = load_plan(DATA_ROOT / "tianjin_query_plan.json")
    delay_seconds = float(plan["delay_seconds"])
    observed_at = as_of.astimezone(timezone.utc).isoformat()

    existing_records = merge_canonical_records(
        load_array(DATA_ROOT / "tianjin_verified_seed.json"),
        load_array(DATA_ROOT / "tianjin_live_ccgp_records.json"),
    )
    existing_events = merge_notice_events([], load_array(DATA_ROOT / "tianjin_notice_events.json"))

    failures: list[dict[str, Any]] = []
    discovered_by_url: dict[str, tuple[str, object]] = {}
    discovered_keywords: dict[str, set[str]] = {}
    planned_query_count = len(windows) * len(plan["keywords"]) * len(plan["notice_types"])

    for window_start, window_end in windows:
        for keyword_index, keyword in enumerate(plan["keywords"]):
            candidates = discover_candidates(
                keyword=keyword,
                region=plan["region"],
                notice_types=plan["notice_types"],
                start_date=window_start.isoformat(),
                end_date=window_end.isoformat(),
                delay_seconds=delay_seconds,
                failures=failures,
            )
            for notice_type, candidate in candidates:
                detail_url = str(getattr(candidate, "detail_url", "") or "").strip()
                if not detail_url:
                    continue
                discovered_by_url.setdefault(detail_url, (notice_type, candidate))
                discovered_keywords.setdefault(detail_url, set()).add(keyword)
            if keyword_index + 1 < len(plan["keywords"]):
                time.sleep(delay_seconds)

    discovery_failures = [item for item in failures if item.get("stage") == "discovery_search"]
    discovery_success_count = max(0, planned_query_count - len(discovery_failures))
    discovered = list(discovered_by_url.values())
    discovered.sort(
        key=lambda item: (
            getattr(item[1], "published_at", None) or "",
            getattr(item[1], "detail_url", ""),
        ),
        reverse=True,
    )

    cap_exceeded = len(discovered) > args.max_candidates
    selected = discovered[: args.max_candidates]
    new_records: list[dict[str, Any]] = []
    for notice_type, candidate in selected:
        adapter = VERIFIED_NOTICE_ADAPTERS[notice_type]
        try:
            time.sleep(delay_seconds)
            detail_html = fetch_ccgp_detail_html(candidate.detail_url)
            new_records.append(
                adapter(
                    detail_html,
                    source_url=candidate.detail_url,
                    observed_at=observed_at,
                    opportunity_id=stable_id("ccgp", candidate.detail_url),
                )
            )
        except Exception as exc:
            failures.append(
                {
                    "stage": "verified_detail",
                    "notice_type": notice_type,
                    "keywords": sorted(discovered_keywords.get(candidate.detail_url, set())),
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    merged_records = merge_canonical_records(existing_records, new_records)
    watch_projects = active_ccgp_project_numbers(merged_records, as_of)
    watch_cap_exceeded = len(watch_projects) > args.max_event_watch_projects
    event_projects = watch_projects[: args.max_event_watch_projects]
    new_events: list[dict[str, Any]] = []
    event_search_blocked_projects: list[str] = []
    full_start = windows[0][0].isoformat()
    full_end = windows[-1][1].isoformat()

    for project_number in event_projects:
        before = len(failures)
        new_events.extend(
            scan_events(
                project_number,
                region=plan["region"],
                start_date=full_start,
                end_date=full_end,
                delay_seconds=delay_seconds,
                observed_at=observed_at,
                failures=failures,
            )
        )
        project_event_search_failures = [
            item
            for item in failures[before:]
            if item.get("stage") == "event_search" and item.get("project_number") == project_number
        ]
        if len(project_event_search_failures) >= 2:
            event_search_blocked_projects.append(project_number)

    merged_events = merge_notice_events(existing_events, new_events)
    detail_failures = [item for item in failures if item.get("stage") == "verified_detail"]
    acceptance_ready = (
        discovery_success_count > 0
        and not cap_exceeded
        and not watch_cap_exceeded
        and (not selected or bool(new_records))
        and not event_search_blocked_projects
    )

    report = {
        "schema_version": "0.1",
        "mode": "CCGP_BOOTSTRAP_BACKFILL_CANDIDATE_ONLY",
        "as_of": as_of.isoformat(),
        "region": plan["region"],
        "lookback_days": args.lookback_days,
        "chunk_days": args.chunk_days,
        "windows": [
            {"start_date": start.isoformat(), "end_date": end.isoformat()}
            for start, end in windows
        ],
        "planned_discovery_query_count": planned_query_count,
        "discovery_success_count": discovery_success_count,
        "unique_discovered_candidate_count": len(discovered),
        "selected_candidate_count": len(selected),
        "candidate_cap_exceeded": cap_exceeded,
        "existing_record_count": len(existing_records),
        "new_verified_record_count": len(new_records),
        "merged_record_count": len(merged_records),
        "verified_detail_failure_count": len(detail_failures),
        "event_watch_project_count": len(watch_projects),
        "event_watch_cap_exceeded": watch_cap_exceeded,
        "event_search_blocked_projects": event_search_blocked_projects,
        "existing_event_count": len(existing_events),
        "new_notice_event_count": len(new_events),
        "merged_event_count": len(merged_events),
        "failure_count": len(failures),
        "failures": failures,
        "acceptance_ready": acceptance_ready,
        "policy": {
            "publishes_public_snapshot": False,
            "writes_runtime_cache": False,
            "discovery_only_never_becomes_verified": True,
            "official_detail_verification_required": True,
            "history_is_chunked_to_avoid_first_page_recency_bias": True,
            "active_projects_receive_correction_and_termination_scan": True,
            "candidate_or_event_watch_caps_fail_acceptance_closed": True,
            "minimum_request_delay_seconds": delay_seconds,
            "rate_limit_bypass": False,
        },
    }

    write_json(args.records_output, merged_records)
    write_json(args.events_output, merged_events)
    write_json(args.report_output, report)
    print(
        f"windows={len(windows)} discovered={len(discovered)} selected={len(selected)} "
        f"new_verified={len(new_records)} watched={len(watch_projects)} "
        f"new_events={len(new_events)} acceptance_ready={acceptance_ready}"
    )
    return 0 if acceptance_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
