from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from vercel.functions import RuntimeCache

WEB_ROOT = Path(__file__).resolve().parent
PIPELINE_ROOT = WEB_ROOT / "pipeline"
SCRIPT_DIR = PIPELINE_ROOT / "scripts"
DATA_ROOT = PIPELINE_ROOT / "data"
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from collector_namespace import CCGP_EVENTS_KEY, CCGP_RECORDS_KEY  # noqa: E402
from medical_channel_pipeline import build_public_snapshot  # noqa: E402
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

SCHEMA_VERSION = "0.1"
SHANGHAI = ZoneInfo("Asia/Shanghai")
QUEUE_TOPIC_NAME = "medicalchannelai-backfill-v1"

META_KEY = "medicalchannelai:backfill:v1:meta"
ACTIVE_CYCLE_KEY = "medicalchannelai:backfill:v1:active-cycle"
CANDIDATES_KEY = "medicalchannelai:backfill:v1:candidates"
RECORDS_KEY = "medicalchannelai:backfill:v1:records"
EVENTS_KEY = "medicalchannelai:backfill:v1:events"
WATCH_KEY = "medicalchannelai:backfill:v1:watch"
FAILURES_KEY = "medicalchannelai:backfill:v1:failures"
REPORT_KEY = "medicalchannelai:backfill:v1:report"

STATE_TTL_SECONDS = 7 * 24 * 60 * 60
ACTIVE_TTL_SECONDS = 2 * 24 * 60 * 60
LOOKBACK_DAYS = 30
CHUNK_DAYS = 7
DETAIL_BATCH_SIZE = 8
EVENT_BATCH_SIZE = 4
MAX_CANDIDATES = 200
MAX_EVENT_WATCH_PROJECTS = 100
MAX_STAGE_ATTEMPTS = 3


class BackfillError(RuntimeError):
    pass


class BackfillConflict(BackfillError):
    pass


def _cache_set(cache: RuntimeCache, key: str, value: Any, *, tag: str, ttl: int = STATE_TTL_SECONDS) -> None:
    cache.set(key, value, {"ttl": ttl, "tags": [tag]})


def _load_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"BACKFILL_BOOTSTRAP_ARRAY_REQUIRED:{path.name}")
    return value


def _bootstrap_records() -> list[dict[str, Any]]:
    return merge_canonical_records(
        _load_array(DATA_ROOT / "tianjin_verified_seed.json"),
        _load_array(DATA_ROOT / "tianjin_live_ccgp_records.json"),
    )


def _bootstrap_events() -> list[dict[str, Any]]:
    return merge_notice_events([], _load_array(DATA_ROOT / "tianjin_notice_events.json"))


def _current_records(cache: RuntimeCache) -> list[dict[str, Any]]:
    value = cache.get(CCGP_RECORDS_KEY)
    if isinstance(value, list):
        return merge_canonical_records([], value)
    return _bootstrap_records()


def _current_events(cache: RuntimeCache) -> list[dict[str, Any]]:
    value = cache.get(CCGP_EVENTS_KEY)
    if isinstance(value, list):
        return merge_notice_events([], value)
    return _bootstrap_events()


def build_date_windows(end_date: date, *, lookback_days: int = LOOKBACK_DAYS, chunk_days: int = CHUNK_DAYS) -> list[tuple[date, date]]:
    if not 1 <= lookback_days <= 60:
        raise ValueError("BACKFILL_LOOKBACK_OUT_OF_RANGE")
    if not 1 <= chunk_days <= 14:
        raise ValueError("BACKFILL_CHUNK_OUT_OF_RANGE")
    first = end_date - timedelta(days=lookback_days - 1)
    windows: list[tuple[date, date]] = []
    cursor = first
    while cursor <= end_date:
        window_end = min(end_date, cursor + timedelta(days=chunk_days - 1))
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def _cycle_id(now: datetime, commit: str) -> str:
    local_date = now.astimezone(SHANGHAI).date().isoformat()
    safe_commit = (commit or "unknown")[:7]
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"backfill:{local_date}:{safe_commit}:{stamp}"


def _base_state(now: datetime, commit: str) -> dict[str, Any]:
    windows = build_date_windows(now.astimezone(SHANGHAI).date())
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "CCGP_BOOTSTRAP_BACKFILL_CANDIDATE_ONLY",
        "cycle_id": _cycle_id(now, commit),
        "cycle_as_of": now.isoformat(),
        "local_date": now.astimezone(SHANGHAI).date().isoformat(),
        "status": "QUEUED",
        "current_stage": "discover:0",
        "windows": [
            {"start_date": start.isoformat(), "end_date": end.isoformat()}
            for start, end in windows
        ],
        "attempts": {},
        "discovery_success_count": 0,
        "discovery_query_count": 0,
        "new_verified_record_count": 0,
        "new_notice_event_count": 0,
        "event_search_blocked_projects": [],
        "candidate_cap_exceeded": False,
        "event_watch_cap_exceeded": False,
        "acceptance_ready": False,
        "updated_at": now.isoformat(),
    }


def _write_state(cache: RuntimeCache, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _cache_set(cache, META_KEY, state, tag="medicalchannelai-backfill-state")


def load_status(cache: RuntimeCache | None = None) -> dict[str, Any]:
    cache = cache or RuntimeCache()
    value = cache.get(META_KEY)
    if isinstance(value, dict):
        return value
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "CCGP_BOOTSTRAP_BACKFILL_CANDIDATE_ONLY",
        "cycle_id": None,
        "status": "IDLE",
        "current_stage": None,
        "acceptance_ready": False,
        "updated_at": None,
    }


def load_report(cache: RuntimeCache | None = None) -> dict[str, Any] | None:
    cache = cache or RuntimeCache()
    value = cache.get(REPORT_KEY)
    return value if isinstance(value, dict) else None


def mark_start_failed(error: str, cache: RuntimeCache | None = None) -> None:
    cache = cache or RuntimeCache()
    state = load_status(cache)
    if isinstance(state, dict):
        state["status"] = "FAILED"
        state["last_error"] = str(error)[:240]
        _write_state(cache, state)
    cache.delete(ACTIVE_CYCLE_KEY)


def active_cycle_id(cache: RuntimeCache | None = None) -> str | None:
    cache = cache or RuntimeCache()
    value = cache.get(ACTIVE_CYCLE_KEY)
    if not isinstance(value, dict):
        return None
    cycle_id = str(value.get("cycle_id") or "").strip()
    return cycle_id or None


def start_cycle(*, now: datetime, commit: str, cache: RuntimeCache | None = None) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ValueError("BACKFILL_AS_OF_TIMEZONE_REQUIRED")
    cache = cache or RuntimeCache()
    existing = load_status(cache)
    if existing.get("status") in {"QUEUED", "RUNNING"}:
        raise BackfillConflict("BACKFILL_ALREADY_RUNNING")

    state = _base_state(now, commit)
    records = _current_records(cache)
    events = _current_events(cache)
    state["base_record_count"] = len(records)
    state["base_event_count"] = len(events)

    _cache_set(cache, CANDIDATES_KEY, [], tag="medicalchannelai-backfill-candidates")
    _cache_set(cache, RECORDS_KEY, records, tag="medicalchannelai-backfill-records")
    _cache_set(cache, EVENTS_KEY, events, tag="medicalchannelai-backfill-events")
    _cache_set(cache, WATCH_KEY, [], tag="medicalchannelai-backfill-watch")
    _cache_set(cache, FAILURES_KEY, [], tag="medicalchannelai-backfill-failures")
    _cache_set(cache, REPORT_KEY, {}, tag="medicalchannelai-backfill-report")

    active = {
        "schema_version": SCHEMA_VERSION,
        "cycle_id": state["cycle_id"],
        "cycle_as_of": state["cycle_as_of"],
        "local_date": state["local_date"],
    }
    _cache_set(
        cache,
        ACTIVE_CYCLE_KEY,
        active,
        tag="medicalchannelai-backfill-active-cycle",
        ttl=ACTIVE_TTL_SECONDS,
    )
    if active_cycle_id(cache) != state["cycle_id"]:
        raise RuntimeError("BACKFILL_ACTIVE_CYCLE_READBACK_FAILED")

    _write_state(cache, state)
    return state


def _list(cache: RuntimeCache, key: str) -> list[Any]:
    value = cache.get(key)
    return list(value) if isinstance(value, list) else []


def _append_failures(cache: RuntimeCache, new_failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures = _list(cache, FAILURES_KEY)
    failures.extend(new_failures)
    failures = failures[-500:]
    _cache_set(cache, FAILURES_KEY, failures, tag="medicalchannelai-backfill-failures")
    return failures


def _candidate_key(item: dict[str, Any]) -> str:
    return str(item.get("detail_url") or "").strip()


def _merge_candidates(existing: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in [*existing, *new_items]:
        key = _candidate_key(item)
        if not key:
            continue
        current = merged.get(key)
        if current is None:
            merged[key] = item
            continue
        keywords = sorted(set((current.get("search_keywords") or []) + (item.get("search_keywords") or [])))
        current["search_keywords"] = keywords
    values = list(merged.values())
    values.sort(key=lambda item: (str(item.get("published_at") or ""), str(item.get("detail_url") or "")), reverse=True)
    return values


def _candidate_dict(notice_type: str, candidate: object, keyword: str) -> dict[str, Any]:
    return {
        "notice_type": notice_type,
        "title": str(getattr(candidate, "title", "") or "").strip(),
        "detail_url": str(getattr(candidate, "detail_url", "") or "").strip(),
        "published_at": getattr(candidate, "published_at", None),
        "buyer_name": getattr(candidate, "buyer_name", None),
        "region": getattr(candidate, "region", None),
        "search_keywords": [keyword],
    }


def _stage_attempt(state: dict[str, Any], stage: str) -> int:
    attempts = state.setdefault("attempts", {})
    current = int(attempts.get(stage) or 0) + 1
    attempts[stage] = current
    return current


def _mark_running(cache: RuntimeCache, state: dict[str, Any], stage: str) -> int:
    attempt = _stage_attempt(state, stage)
    if attempt > MAX_STAGE_ATTEMPTS:
        state["status"] = "FAILED"
        state["current_stage"] = stage
        _write_state(cache, state)
        raise BackfillError(f"BACKFILL_STAGE_RETRY_LIMIT:{stage}")
    state["status"] = "RUNNING"
    state["current_stage"] = stage
    _write_state(cache, state)
    return attempt


def _finish_stage(cache: RuntimeCache, state: dict[str, Any], stage: str, next_stage: str | None) -> dict[str, Any]:
    state["status"] = "COMPLETED" if next_stage is None else "RUNNING"
    state["current_stage"] = next_stage
    _write_state(cache, state)
    return {
        "action": "COMPLETED",
        "stage": stage,
        "next_stage": next_stage,
        "cycle_id": state["cycle_id"],
    }


def _fail_stage(cache: RuntimeCache, state: dict[str, Any], stage: str, error: str) -> dict[str, Any]:
    state["status"] = "FAILED"
    state["current_stage"] = stage
    state["last_error"] = error[:240]
    _write_state(cache, state)
    return {
        "action": "FAILED",
        "stage": stage,
        "error": error[:240],
        "cycle_id": state["cycle_id"],
    }


def _windows(state: dict[str, Any]) -> list[dict[str, str]]:
    value = state.get("windows")
    return value if isinstance(value, list) else []


def _run_discovery(cache: RuntimeCache, state: dict[str, Any], index: int) -> dict[str, Any]:
    windows = _windows(state)
    if not 0 <= index < len(windows):
        return _fail_stage(cache, state, f"discover:{index}", "BACKFILL_DISCOVERY_WINDOW_INVALID")

    plan = load_plan(DATA_ROOT / "tianjin_query_plan.json")
    window = windows[index]
    failures: list[dict[str, Any]] = []
    discovered_items: list[dict[str, Any]] = []
    planned_queries = len(plan["keywords"]) * len(plan["notice_types"])

    for keyword_index, keyword in enumerate(plan["keywords"]):
        candidates = discover_candidates(
            keyword=keyword,
            region=plan["region"],
            notice_types=plan["notice_types"],
            start_date=window["start_date"],
            end_date=window["end_date"],
            delay_seconds=float(plan["delay_seconds"]),
            failures=failures,
        )
        for notice_type, candidate in candidates:
            discovered_items.append(_candidate_dict(notice_type, candidate, keyword))
        if keyword_index + 1 < len(plan["keywords"]):
            time.sleep(float(plan["delay_seconds"]))

    stage_failures = [item for item in failures if item.get("stage") == "discovery_search"]
    success_count = max(0, planned_queries - len(stage_failures))
    state["discovery_query_count"] = int(state.get("discovery_query_count") or 0) + planned_queries
    state["discovery_success_count"] = int(state.get("discovery_success_count") or 0) + success_count
    _append_failures(cache, failures)

    if success_count == 0:
        return _fail_stage(cache, state, f"discover:{index}", "BACKFILL_DISCOVERY_ALL_QUERIES_FAILED")

    candidates = _merge_candidates(_list(cache, CANDIDATES_KEY), discovered_items)
    _cache_set(cache, CANDIDATES_KEY, candidates, tag="medicalchannelai-backfill-candidates")
    state["unique_discovered_candidate_count"] = len(candidates)

    if len(candidates) > MAX_CANDIDATES:
        state["candidate_cap_exceeded"] = True
        return _fail_stage(cache, state, f"discover:{index}", "BACKFILL_CANDIDATE_CAP_EXCEEDED")

    if index + 1 < len(windows):
        next_stage = f"discover:{index + 1}"
    elif candidates:
        next_stage = "detail:0"
    else:
        next_stage = "report"
    return _finish_stage(cache, state, f"discover:{index}", next_stage)


def _run_detail(cache: RuntimeCache, state: dict[str, Any], index: int) -> dict[str, Any]:
    candidates = _list(cache, CANDIDATES_KEY)
    start = index * DETAIL_BATCH_SIZE
    batch = candidates[start : start + DETAIL_BATCH_SIZE]
    if not batch:
        return _fail_stage(cache, state, f"detail:{index}", "BACKFILL_DETAIL_BATCH_INVALID")

    plan = load_plan(DATA_ROOT / "tianjin_query_plan.json")
    delay_seconds = float(plan["delay_seconds"])
    observed_at = str(state.get("cycle_as_of") or "")
    failures: list[dict[str, Any]] = []
    new_records: list[dict[str, Any]] = []

    for item in batch:
        notice_type = str(item.get("notice_type") or "")
        detail_url = str(item.get("detail_url") or "")
        adapter = VERIFIED_NOTICE_ADAPTERS.get(notice_type)
        if adapter is None or not detail_url:
            failures.append({
                "stage": "verified_detail",
                "notice_type": notice_type,
                "url": detail_url,
                "error": "BACKFILL_CANDIDATE_INVALID",
            })
            continue
        try:
            time.sleep(delay_seconds)
            html = fetch_ccgp_detail_html(detail_url)
            new_records.append(
                adapter(
                    html,
                    source_url=detail_url,
                    observed_at=observed_at,
                    opportunity_id=stable_id("ccgp", detail_url),
                )
            )
        except Exception as exc:
            failures.append({
                "stage": "verified_detail",
                "notice_type": notice_type,
                "keywords": item.get("search_keywords") or [],
                "title": str(item.get("title") or "")[:300],
                "url": detail_url,
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            })

    _append_failures(cache, failures)
    records = merge_canonical_records(_list(cache, RECORDS_KEY), new_records)
    _cache_set(cache, RECORDS_KEY, records, tag="medicalchannelai-backfill-records")
    state["new_verified_record_count"] = int(state.get("new_verified_record_count") or 0) + len(new_records)
    state["merged_record_count"] = len(records)

    next_start = start + DETAIL_BATCH_SIZE
    if next_start < len(candidates):
        return _finish_stage(cache, state, f"detail:{index}", f"detail:{index + 1}")

    if candidates and int(state.get("new_verified_record_count") or 0) == 0:
        return _fail_stage(cache, state, f"detail:{index}", "BACKFILL_ALL_DETAILS_FAILED_VERIFICATION")

    cycle_as_of = datetime.fromisoformat(str(state["cycle_as_of"]).replace("Z", "+00:00"))
    watch = active_ccgp_project_numbers(records, cycle_as_of)
    state["event_watch_project_count"] = len(watch)
    if len(watch) > MAX_EVENT_WATCH_PROJECTS:
        state["event_watch_cap_exceeded"] = True
        return _fail_stage(cache, state, f"detail:{index}", "BACKFILL_EVENT_WATCH_CAP_EXCEEDED")
    _cache_set(cache, WATCH_KEY, watch, tag="medicalchannelai-backfill-watch")
    next_stage = "event:0" if watch else "report"
    return _finish_stage(cache, state, f"detail:{index}", next_stage)


def _run_event(cache: RuntimeCache, state: dict[str, Any], index: int) -> dict[str, Any]:
    watch = _list(cache, WATCH_KEY)
    start = index * EVENT_BATCH_SIZE
    batch = watch[start : start + EVENT_BATCH_SIZE]
    if not batch:
        return _fail_stage(cache, state, f"event:{index}", "BACKFILL_EVENT_BATCH_INVALID")

    plan = load_plan(DATA_ROOT / "tianjin_query_plan.json")
    windows = _windows(state)
    failures: list[dict[str, Any]] = []
    new_events: list[dict[str, Any]] = []
    blocked: list[str] = []

    for project_number in batch:
        before = len(failures)
        new_events.extend(
            scan_events(
                str(project_number),
                region=plan["region"],
                start_date=windows[0]["start_date"],
                end_date=windows[-1]["end_date"],
                delay_seconds=float(plan["delay_seconds"]),
                observed_at=str(state.get("cycle_as_of") or ""),
                failures=failures,
            )
        )
        project_failures = [
            item for item in failures[before:]
            if item.get("stage") == "event_search"
            and item.get("project_number") == project_number
        ]
        if len(project_failures) >= 2:
            blocked.append(str(project_number))

    _append_failures(cache, failures)
    if blocked:
        state["event_search_blocked_projects"] = sorted(
            set((state.get("event_search_blocked_projects") or []) + blocked)
        )
        return _fail_stage(
            cache,
            state,
            f"event:{index}",
            f"BACKFILL_EVENT_SEARCH_BLOCKED:{','.join(blocked)[:160]}",
        )

    prior_blocked = set(state.get("event_search_blocked_projects") or [])
    prior_blocked.difference_update(str(project) for project in batch)
    state["event_search_blocked_projects"] = sorted(prior_blocked)

    events = merge_notice_events(_list(cache, EVENTS_KEY), new_events)
    _cache_set(cache, EVENTS_KEY, events, tag="medicalchannelai-backfill-events")
    state["new_notice_event_count"] = int(state.get("new_notice_event_count") or 0) + len(new_events)
    state["merged_event_count"] = len(events)

    next_start = start + EVENT_BATCH_SIZE
    next_stage = f"event:{index + 1}" if next_start < len(watch) else "report"
    return _finish_stage(cache, state, f"event:{index}", next_stage)


def _run_report(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    records = _list(cache, RECORDS_KEY)
    events = _list(cache, EVENTS_KEY)
    failures = _list(cache, FAILURES_KEY)
    as_of = datetime.fromisoformat(str(state["cycle_as_of"]).replace("Z", "+00:00"))
    snapshot = build_public_snapshot(records, as_of, events)
    pool = snapshot.get("opportunity_pool") if isinstance(snapshot, dict) else []
    if not isinstance(pool, list):
        pool = []

    acceptance_ready = bool(
        int(state.get("discovery_success_count") or 0) > 0
        and not state.get("candidate_cap_exceeded")
        and not state.get("event_watch_cap_exceeded")
        and not state.get("event_search_blocked_projects")
        and (
            int(state.get("unique_discovered_candidate_count") or 0) == 0
            or int(state.get("new_verified_record_count") or 0) > 0
        )
    )
    candidate_opportunities = []
    for card in pool[:100]:
        facts = card.get("facts") if isinstance(card, dict) else None
        if not isinstance(facts, dict):
            continue
        candidate_opportunities.append({
            "opportunity_id": card.get("opportunity_id"),
            "project_number": facts.get("project_number"),
            "project_name": facts.get("project_name"),
            "buyer_name": facts.get("buyer_name"),
            "published_at": facts.get("published_at"),
            "registration_deadline": facts.get("registration_deadline"),
            "bid_deadline": facts.get("bid_deadline"),
            "budget_cny": (facts.get("budget") or {}).get("amount_cny") if isinstance(facts.get("budget"), dict) else None,
        })

    report = {
        "schema_version": SCHEMA_VERSION,
        "mode": "CCGP_BOOTSTRAP_BACKFILL_CANDIDATE_ONLY",
        "cycle_id": state.get("cycle_id"),
        "as_of": state.get("cycle_as_of"),
        "lookback_days": LOOKBACK_DAYS,
        "chunk_days": CHUNK_DAYS,
        "base_record_count": state.get("base_record_count", 0),
        "base_event_count": state.get("base_event_count", 0),
        "discovery_query_count": state.get("discovery_query_count", 0),
        "discovery_success_count": state.get("discovery_success_count", 0),
        "unique_discovered_candidate_count": state.get("unique_discovered_candidate_count", 0),
        "new_verified_record_count": state.get("new_verified_record_count", 0),
        "merged_record_count": len(records),
        "event_watch_project_count": state.get("event_watch_project_count", 0),
        "new_notice_event_count": state.get("new_notice_event_count", 0),
        "merged_event_count": len(events),
        "failure_count": len(failures),
        "candidate_public_opportunity_count": len(pool),
        "candidate_opportunities": candidate_opportunities,
        "acceptance_ready": acceptance_ready,
        "policy": {
            "publishes_public_snapshot": False,
            "writes_daily_collector_state": False,
            "writes_verified_snapshot_cache": False,
            "official_detail_verification_required": True,
            "medical_channel_scope_required": True,
            "manual_acceptance_required_before_any_promotion": True,
        },
    }
    _cache_set(cache, REPORT_KEY, report, tag="medicalchannelai-backfill-report")
    state["acceptance_ready"] = acceptance_ready
    state["status"] = "COMPLETED" if acceptance_ready else "FAILED"
    state["current_stage"] = None
    _write_state(cache, state)
    return {
        "action": "COMPLETED" if acceptance_ready else "FAILED",
        "stage": "report",
        "next_stage": None,
        "cycle_id": state["cycle_id"],
        "acceptance_ready": acceptance_ready,
    }


def run_stage(stage: str, *, cycle_id: str, cache: RuntimeCache | None = None) -> tuple[int, dict[str, Any]]:
    cache = cache or RuntimeCache()
    state = load_status(cache)
    if str(state.get("cycle_id") or "") != cycle_id or active_cycle_id(cache) != cycle_id:
        return 200, {"action": "STALE_CYCLE_IGNORED", "stage": stage, "cycle_id": cycle_id}

    attempt = _mark_running(cache, state, stage)
    try:
        if stage.startswith("discover:"):
            result = _run_discovery(cache, state, int(stage.split(":", 1)[1]))
        elif stage.startswith("detail:"):
            result = _run_detail(cache, state, int(stage.split(":", 1)[1]))
        elif stage.startswith("event:"):
            result = _run_event(cache, state, int(stage.split(":", 1)[1]))
        elif stage == "report":
            result = _run_report(cache, state)
        else:
            result = _fail_stage(cache, state, stage, "BACKFILL_STAGE_INVALID")
    except Exception as exc:
        result = _fail_stage(cache, state, stage, f"{type(exc).__name__}:{str(exc)[:180]}")

    if result.get("action") == "FAILED":
        if stage == "report" or attempt >= MAX_STAGE_ATTEMPTS:
            result["final"] = True
            return 409, result
        return 503, result
    return 200, result
