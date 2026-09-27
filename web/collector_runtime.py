from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from vercel.functions import RuntimeCache

WEB_ROOT = Path(__file__).resolve().parent
PIPELINE_ROOT = WEB_ROOT / "pipeline"
SCRIPT_DIR = PIPELINE_ROOT / "scripts"
DATA_ROOT = PIPELINE_ROOT / "data"
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from medical_channel_pipeline import build_public_snapshot  # noqa: E402
from medical_channel_pipeline.ccgp_detail import fetch_ccgp_detail_html  # noqa: E402
from medical_channel_pipeline.state import (  # noqa: E402
    active_ccgp_project_numbers,
    merge_canonical_records,
    merge_notice_events,
)
from medical_channel_pipeline.tjfch_discovery import (  # noqa: E402
    INDEX_URL as TJFCH_INDEX_URL,
    fetch_tjfch_page,
    parse_tjfch_index_html,
    select_candidates_since as select_tjfch_candidates,
    stable_opportunity_id as tjfch_opportunity_id,
)
from medical_channel_pipeline.tjfch_procurement import (  # noqa: E402
    TjfchParseError,
    parse_tjfch_procurement_notice,
)
from medical_channel_pipeline.tjfch_test_discovery import (  # noqa: E402
    INDEX_URL as TJFCH_TEST_INDEX_URL,
    parse_tjfch_test_index_html,
)
from medical_channel_pipeline.tjfch_test_recruitment import (  # noqa: E402
    TjfchTestParseError,
    parse_tjfch_test_recruitment,
)
from medical_channel_pipeline.teda_discovery import stable_opportunity_id as teda_opportunity_id  # noqa: E402
from medical_channel_pipeline.teda_market_research import (  # noqa: E402
    TedaParseError,
    parse_teda_market_research,
)
from medical_channel_pipeline.tjmugh_discovery import (  # noqa: E402
    INDEX_URL as TJMUGH_INDEX_URL,
    fetch_tjmugh_page,
    parse_tjmugh_index_html,
    select_candidates_since as select_tjmugh_candidates,
    stable_opportunity_id as tjmugh_opportunity_id,
)
from medical_channel_pipeline.tjmugh_market_research import parse_tjmugh_market_research  # noqa: E402
from medical_channel_pipeline.tjnothop_discovery import (  # noqa: E402
    INDEX_URL as TJNOTHOP_INDEX_URL,
    fetch_tjnothop_page,
    parse_tjnothop_index_html,
    select_candidates_since as select_tjnothop_candidates,
    stable_opportunity_id as tjnothop_opportunity_id,
)
from medical_channel_pipeline.tjnothop_market_research import parse_tjnothop_market_research  # noqa: E402
from sync_ccgp_query import VERIFIED_NOTICE_ADAPTERS, discover_candidates, scan_events, stable_id  # noqa: E402
from sync_teda_market_research import (  # noqa: E402
    UNSUPPORTED_DETAIL_CODES as TEDA_UNSUPPORTED_DETAIL_CODES,
    discover_candidates as discover_teda_candidates,
    fetch_page_with_retry as fetch_teda_page_with_retry,
)
from sync_tianjin_plan import load_plan, plan_date_window, publish_gate as ccgp_publish_gate  # noqa: E402
from sync_regional_ccgp import (  # noqa: E402
    CcgpSearchSession as RegionalCcgpSearchSession,
    NATIONAL_FALLBACK_MAX_PAGES as REGIONAL_FALLBACK_MAX_PAGES,
    annotate_market as annotate_regional_market,
    candidate_market_code,
    date_window as regional_date_window,
    fetch_candidates_page as fetch_regional_candidates_page,
    load_plan as load_regional_plan,
)
from medical_channel_pipeline.regional_candidate import (  # noqa: E402
    regional_candidate_selection_key,
    regional_candidate_skip_reason,
)

SCHEMA_VERSION = "0.1"
SHANGHAI = ZoneInfo("Asia/Shanghai")
STATE_TTL_SECONDS = 14 * 24 * 60 * 60
SNAPSHOT_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_STAGE_ATTEMPTS_PER_DAY = 2
EVENT_BATCH_SIZE = 5
TEDA_LOOKBACK_DAYS = 90
TEDA_INDEX_PAGES = 4
TEDA_MAX_CANDIDATES = 20
TEDA_REQUEST_DELAY_SECONDS = 3.0
TJFCH_LOOKBACK_DAYS = 45
TJFCH_MAX_CANDIDATES = 20
TJFCH_TEST_LOOKBACK_DAYS = 14
TJFCH_TEST_MAX_CANDIDATES = 30
TJFCH_REQUEST_DELAY_SECONDS = 3.0

META_KEY = "medicalchannelai:collector-runtime-state:v1"
CCGP_RECORDS_KEY = "medicalchannelai:collector-ccgp-records:v1"
CCGP_EVENTS_KEY = "medicalchannelai:collector-ccgp-events:v1"
CCGP_WATCH_KEY = "medicalchannelai:collector-ccgp-watch-projects:v1"
TJMUGH_RECORDS_KEY = "medicalchannelai:collector-tjmugh-records:v1"
TJNOTHOP_RECORDS_KEY = "medicalchannelai:collector-tjnothop-records:v1"
TEDA_RECORDS_KEY = "medicalchannelai:collector-teda-records:v1"
TJFCH_RECORDS_KEY = "medicalchannelai:collector-tjfch-records:v1"
REGIONAL_RECORDS_KEY_PREFIX = "medicalchannelai:collector-regional-records:v3"
LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v1"
PUBLISHED_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:published:v2"
DURABLE_PUBLISH_URL = "https://medicalchannelai.vercel.app/api/public-snapshot"
DURABLE_PUBLISH_TIMEOUT_SECONDS = 30

REGIONAL_STAGE_MARKET_CODES = {
    "regional_bj": "BJ",
    "regional_he": "HE",
    "regional_ln": "LN",
    "regional_jl": "JL",
    "regional_hl": "HL",
}

STAGE_ORDER = (
    "ccgp",
    "event1",
    "event2",
    "event3",
    "event4",
    "event5",
    "event6",
    "tjmugh",
    "tjnothop",
    "teda",
    "tjfch",
    "regional_bj",
    "regional_he",
    "regional_ln",
    "regional_jl",
    "regional_hl",
    "publish",
)
EXPECTED_SCHEDULES = {
    "ccgp": "20 0 * * *",
    "event1": "35 0 * * *",
    "event2": "50 0 * * *",
    "event3": "5 1 * * *",
    "event4": "20 1 * * *",
    "event5": "35 1 * * *",
    "event6": "50 1 * * *",
    "tjmugh": "5 2 * * *",
    "tjnothop": "20 2 * * *",
    "teda": "35 2 * * *",
    "tjfch": "50 2 * * *",
    "publish": "5 3 * * *",
}


class CollectorError(RuntimeError):
    code = "COLLECTOR_ERROR"


class CollectorPrecondition(CollectorError):
    code = "COLLECTOR_PRECONDITION_FAILED"


class CollectorStageBlocked(CollectorError):
    code = "COLLECTOR_STAGE_BLOCKED"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cache_set(cache: RuntimeCache, key: str, value: Any, *, tag: str, ttl: int = STATE_TTL_SECONDS) -> None:
    cache.set(key, value, {"ttl": ttl, "tags": [tag]})


def _load_array(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"COLLECTOR_BOOTSTRAP_ARRAY_REQUIRED:{path.name}")
    return payload


def _bootstrap_ccgp_records() -> list[dict[str, Any]]:
    return merge_canonical_records(
        _load_array(DATA_ROOT / "tianjin_verified_seed.json"),
        _load_array(DATA_ROOT / "tianjin_live_ccgp_records.json"),
    )


def _bootstrap_ccgp_events() -> list[dict[str, Any]]:
    return merge_notice_events([], _load_array(DATA_ROOT / "tianjin_notice_events.json"))


def _bootstrap_tjmugh_records() -> list[dict[str, Any]]:
    return merge_canonical_records(
        _load_array(DATA_ROOT / "tianjin_official_institution_seed.json"),
        _load_array(DATA_ROOT / "tianjin_live_tjmugh_records.json"),
    )


def _bootstrap_tjnothop_records() -> list[dict[str, Any]]:
    return merge_canonical_records([], _load_array(DATA_ROOT / "tianjin_live_tjnothop_records.json"))


def _bootstrap_teda_records() -> list[dict[str, Any]]:
    return merge_canonical_records([], _load_array(DATA_ROOT / "tianjin_live_teda_records.json"))


def _bootstrap_tjfch_records() -> list[dict[str, Any]]:
    return merge_canonical_records([], _load_array(DATA_ROOT / "tianjin_live_tjfch_records.json"))


def _regional_records_key(market_code: str) -> str:
    normalized = str(market_code or "").strip().upper()
    if normalized not in set(REGIONAL_STAGE_MARKET_CODES.values()):
        raise CollectorPrecondition(f"REGIONAL_MARKET_KEY_INVALID:{normalized}")
    return f"{REGIONAL_RECORDS_KEY_PREFIX}:{normalized}"


def _bootstrap_regional_records(market_code: str) -> list[dict[str, Any]]:
    normalized = str(market_code or "").strip().upper()
    records = _load_array(DATA_ROOT / "regional_live_ccgp_records.json")
    scoped = [
        record
        for record in records
        if isinstance(record, dict)
        and str((record.get("facts") or {}).get("market_code") or "").strip().upper() == normalized
    ]
    return merge_canonical_records([], scoped)


def _cached_list(cache: RuntimeCache, key: str, bootstrap) -> tuple[list[dict[str, Any]], bool]:
    value = cache.get(key)
    if isinstance(value, list):
        return value, False
    records = bootstrap()
    _cache_set(cache, key, records, tag="medicalchannelai-collector-canonical")
    return records, True


def _new_cycle(now: datetime) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "local_date": now.astimezone(SHANGHAI).date().isoformat(),
        "cycle_as_of": now.astimezone(SHANGHAI).isoformat(),
        "stages": {},
        "updated_at": now.isoformat(),
    }


def load_status(cache: RuntimeCache | None = None) -> dict[str, Any]:
    cache = cache or RuntimeCache()
    value = cache.get(META_KEY)
    if isinstance(value, dict):
        return value
    return {
        "schema_version": SCHEMA_VERSION,
        "local_date": None,
        "cycle_as_of": None,
        "stages": {},
        "updated_at": None,
    }


def _write_status(cache: RuntimeCache, state: dict[str, Any]) -> None:
    state["updated_at"] = _now_utc().isoformat()
    _cache_set(cache, META_KEY, state, tag="medicalchannelai-collector-state")


def _stage_index(stage: str) -> int:
    try:
        return STAGE_ORDER.index(stage)
    except ValueError as exc:
        raise CollectorPrecondition(f"COLLECTOR_STAGE_INVALID:{stage}") from exc


def _prepare_stage(cache: RuntimeCache, stage: str, now: datetime) -> tuple[dict[str, Any], dict[str, Any] | None]:
    index = _stage_index(stage)
    local_date = now.astimezone(SHANGHAI).date().isoformat()
    state = load_status(cache)

    if stage == "ccgp" and state.get("local_date") != local_date:
        state = _new_cycle(now)
        _write_status(cache, state)
    elif state.get("local_date") != local_date:
        raise CollectorPrecondition("COLLECTOR_CYCLE_NOT_STARTED_TODAY")

    stages = state.setdefault("stages", {})
    previous = stages.get(stage)
    regional_cache_replay = False
    regional_stale_migration_replay = False
    if isinstance(previous, dict) and previous.get("status") == "COMPLETED":
        if stage in REGIONAL_STAGE_MARKET_CODES:
            market_code = REGIONAL_STAGE_MARKET_CODES[stage]
            regional_cache_replay = not isinstance(
                cache.get(_regional_records_key(market_code)),
                list,
            )
        if not regional_cache_replay:
            return state, previous
    elif (
        isinstance(previous, dict)
        and previous.get("status") == "RUNNING"
        and stage in REGIONAL_STAGE_MARKET_CODES
    ):
        publish_state = stages.get("publish")
        market_code = REGIONAL_STAGE_MARKET_CODES[stage]
        started_raw = str(previous.get("started_at") or "")
        try:
            started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
        except ValueError:
            started = None
        regional_stale_migration_replay = bool(
            isinstance(publish_state, dict)
            and publish_state.get("status") == "FAILED"
            and str(publish_state.get("error_message") or "").startswith("COLLECTOR_CANONICAL_STATE_INCOMPLETE")
            and int(previous.get("attempt_count", 0)) == MAX_STAGE_ATTEMPTS_PER_DAY
            and started is not None
            and started.tzinfo is not None
            and now - started.astimezone(timezone.utc) >= timedelta(minutes=15)
        )

    if index > 0:
        required = STAGE_ORDER[index - 1]
        required_state = stages.get(required)
        if not isinstance(required_state, dict) or required_state.get("status") != "COMPLETED":
            raise CollectorPrecondition(f"COLLECTOR_PREVIOUS_STAGE_INCOMPLETE:{required}")

    attempts = int(previous.get("attempt_count", 0)) if isinstance(previous, dict) else 0
    tjfch_policy_recovery_retry = (
        stage == "tjfch"
        and attempts == MAX_STAGE_ATTEMPTS_PER_DAY
        and isinstance(previous, dict)
        and previous.get("status") == "FAILED"
        and "TJFCH_NOTICE_TYPE_UNSUPPORTED" in str(previous.get("error_message") or "")
    )
    publish_cache_migration_retry = (
        stage == "publish"
        and attempts == MAX_STAGE_ATTEMPTS_PER_DAY
        and isinstance(previous, dict)
        and previous.get("status") == "FAILED"
        and str(previous.get("error_message") or "").startswith("COLLECTOR_CANONICAL_STATE_INCOMPLETE")
    )
    if (
        attempts >= MAX_STAGE_ATTEMPTS_PER_DAY
        and not tjfch_policy_recovery_retry
        and not regional_cache_replay
        and not regional_stale_migration_replay
        and not publish_cache_migration_retry
    ):
        raise CollectorPrecondition(f"COLLECTOR_STAGE_RETRY_LIMIT:{stage}")

    stages[stage] = {
        "status": "RUNNING",
        "attempt_count": attempts + 1,
        "started_at": now.isoformat(),
        "completed_at": None,
        "error_code": None,
        "error_message": None,
        "result": None,
    }
    _write_status(cache, state)
    return state, None


def _mark_completed(cache: RuntimeCache, state: dict[str, Any], stage: str, result: dict[str, Any]) -> None:
    current = state["stages"][stage]
    current["status"] = "COMPLETED"
    current["completed_at"] = _now_utc().isoformat()
    current["result"] = result
    current["error_code"] = None
    current["error_message"] = None
    _write_status(cache, state)


def _mark_failed(cache: RuntimeCache, state: dict[str, Any], stage: str, exc: Exception) -> None:
    current = state["stages"][stage]
    current["status"] = "FAILED"
    current["completed_at"] = _now_utc().isoformat()
    current["error_code"] = getattr(exc, "code", type(exc).__name__)
    current["error_message"] = str(exc)[:300]
    _write_status(cache, state)


def _cycle_as_of(state: dict[str, Any]) -> datetime:
    raw = str(state.get("cycle_as_of") or "")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CollectorPrecondition("COLLECTOR_CYCLE_AS_OF_INVALID")
    return parsed


def _run_ccgp(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    plan = load_plan(DATA_ROOT / "tianjin_query_plan.json")
    as_of = _cycle_as_of(state)
    start_text, end_text = plan_date_window(as_of, plan["lookback_days"])
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records, bootstrapped_records = _cached_list(cache, CCGP_RECORDS_KEY, _bootstrap_ccgp_records)
    existing_events, bootstrapped_events = _cached_list(cache, CCGP_EVENTS_KEY, _bootstrap_ccgp_events)

    failures: list[dict[str, Any]] = []
    discovered_by_url: dict[str, tuple[str, object]] = {}
    discovered_keywords: dict[str, set[str]] = {}
    planned_queries = len(plan["keywords"]) * len(plan["notice_types"])

    for keyword_index, keyword in enumerate(plan["keywords"]):
        candidates = discover_candidates(
            keyword=keyword,
            region=plan["region"],
            notice_types=plan["notice_types"],
            start_date=start_text,
            end_date=end_text,
            delay_seconds=plan["delay_seconds"],
            failures=failures,
        )
        for notice_type, candidate in candidates:
            detail_url = str(getattr(candidate, "detail_url", "") or "").strip()
            if not detail_url:
                continue
            discovered_by_url.setdefault(detail_url, (notice_type, candidate))
            discovered_keywords.setdefault(detail_url, set()).add(keyword)
        if keyword_index + 1 < len(plan["keywords"]):
            time.sleep(plan["delay_seconds"])

    discovery_failures = [item for item in failures if item.get("stage") == "discovery_search"]
    discovery_success_count = max(0, planned_queries - len(discovery_failures))
    discovered = list(discovered_by_url.values())
    discovered.sort(
        key=lambda item: (
            getattr(item[1], "published_at", None) or "",
            getattr(item[1], "detail_url", ""),
        ),
        reverse=True,
    )
    selected = discovered[: plan["max_candidates"]]

    new_records: list[dict[str, Any]] = []
    for notice_type, candidate in selected:
        adapter = VERIFIED_NOTICE_ADAPTERS[notice_type]
        try:
            time.sleep(plan["delay_seconds"])
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

    allowed, reason = ccgp_publish_gate(
        discovery_success_count=discovery_success_count,
        selected_candidate_count=len(selected),
        new_verified_record_count=len(new_records),
    )
    if not allowed:
        detail_failures = [item for item in failures if item.get("stage") == "verified_detail"]
        diagnostic = ";".join(
            f"{item.get('error')}:{item.get('message')}"
            for item in detail_failures[:3]
        )
        suffix = f";DETAIL_FAILURES:{diagnostic}" if diagnostic else ""
        raise CollectorStageBlocked(f"CCGP_PUBLISH_GATE:{reason}{suffix}")

    merged_records = merge_canonical_records(existing_records, new_records)
    watch_projects = active_ccgp_project_numbers(merged_records, as_of)
    if len(watch_projects) > plan["max_event_watch_projects"]:
        raise CollectorStageBlocked(
            f"ACTIVE_EVENT_WATCH_CAP_EXCEEDED:{len(watch_projects)}>{plan['max_event_watch_projects']}"
        )

    _cache_set(cache, CCGP_RECORDS_KEY, merged_records, tag="medicalchannelai-collector-canonical")
    _cache_set(cache, CCGP_EVENTS_KEY, existing_events, tag="medicalchannelai-collector-events")
    _cache_set(cache, CCGP_WATCH_KEY, watch_projects, tag="medicalchannelai-collector-watch")

    return {
        "start_date": start_text,
        "end_date": end_text,
        "planned_discovery_query_count": planned_queries,
        "discovery_success_count": discovery_success_count,
        "unique_discovered_candidate_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "merged_record_count": len(merged_records),
        "event_watch_project_count": len(watch_projects),
        "failure_count": len(failures),
        "publish_gate_reason": reason,
        "bootstrapped_records": bootstrapped_records,
        "bootstrapped_events": bootstrapped_events,
    }


def _run_event_batch(cache: RuntimeCache, state: dict[str, Any], stage: str) -> dict[str, Any]:
    batch_index = int(stage.removeprefix("event")) - 1
    watch_projects = cache.get(CCGP_WATCH_KEY)
    if not isinstance(watch_projects, list):
        raise CollectorPrecondition("COLLECTOR_WATCH_PROJECTS_MISSING")
    projects = [str(item) for item in watch_projects][
        batch_index * EVENT_BATCH_SIZE : (batch_index + 1) * EVENT_BATCH_SIZE
    ]
    existing_events, _ = _cached_list(cache, CCGP_EVENTS_KEY, _bootstrap_ccgp_events)
    ccgp_result = state.get("stages", {}).get("ccgp", {}).get("result") or {}
    start_text = str(ccgp_result.get("start_date") or "")
    end_text = str(ccgp_result.get("end_date") or "")
    if not start_text or not end_text:
        raise CollectorPrecondition("COLLECTOR_CCGP_WINDOW_MISSING")

    plan = load_plan(DATA_ROOT / "tianjin_query_plan.json")
    observed_at = _cycle_as_of(state).astimezone(timezone.utc).isoformat()
    failures: list[dict[str, Any]] = []
    new_events: list[dict[str, Any]] = []

    for project_number in projects:
        before = len(failures)
        new_events.extend(
            scan_events(
                project_number,
                region=plan["region"],
                start_date=start_text,
                end_date=end_text,
                delay_seconds=plan["delay_seconds"],
                observed_at=observed_at,
                failures=failures,
            )
        )
        project_search_failures = [
            item
            for item in failures[before:]
            if item.get("stage") == "event_search" and item.get("project_number") == project_number
        ]
        if len(project_search_failures) >= 2:
            raise CollectorStageBlocked(f"EVENT_WATCH_ALL_SEARCHES_FAILED:{project_number}")

    merged_events = merge_notice_events(existing_events, new_events)
    _cache_set(cache, CCGP_EVENTS_KEY, merged_events, tag="medicalchannelai-collector-events")
    return {
        "batch_index": batch_index + 1,
        "project_count": len(projects),
        "projects": projects,
        "new_notice_event_count": len(new_events),
        "merged_event_count": len(merged_events),
        "failure_count": len(failures),
    }


def _run_tjmugh(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    as_of = _cycle_as_of(state)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=6)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records, bootstrapped = _cached_list(cache, TJMUGH_RECORDS_KEY, _bootstrap_tjmugh_records)
    failures: list[dict[str, Any]] = []

    try:
        index_html = fetch_tjmugh_page(TJMUGH_INDEX_URL)
        discovered = parse_tjmugh_index_html(index_html)
    except Exception as exc:
        raise CollectorStageBlocked(f"TJMUGH_INDEX_DISCOVERY_FAILED:{type(exc).__name__}") from exc

    selected = select_tjmugh_candidates(
        discovered,
        start_date=start_date,
        end_date=local_date,
        max_candidates=15,
    )
    new_records: list[dict[str, Any]] = []
    for candidate in selected:
        time.sleep(3.0)
        try:
            detail_html = fetch_tjmugh_page(candidate.detail_url)
            new_records.append(
                parse_tjmugh_market_research(
                    detail_html,
                    source_url=candidate.detail_url,
                    observed_at=observed_at,
                    opportunity_id=tjmugh_opportunity_id(candidate.detail_url),
                )
            )
        except Exception as exc:
            failures.append(
                {
                    "stage": "verified_detail",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
    if selected and not new_records:
        raise CollectorStageBlocked("TJMUGH_ALL_SELECTED_DETAILS_FAILED_VERIFICATION")

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TJMUGH_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "merged_record_count": len(merged),
        "failure_count": len(failures),
        "bootstrapped_records": bootstrapped,
        "publish_gate_reason": "PASS",
    }


def _run_tjnothop(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    as_of = _cycle_as_of(state)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=20)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records, bootstrapped = _cached_list(cache, TJNOTHOP_RECORDS_KEY, _bootstrap_tjnothop_records)
    failures: list[dict[str, Any]] = []

    try:
        index_html = fetch_tjnothop_page(TJNOTHOP_INDEX_URL)
        discovered = parse_tjnothop_index_html(index_html)
    except Exception as exc:
        raise CollectorStageBlocked(f"TJNOTHOP_INDEX_DISCOVERY_FAILED:{type(exc).__name__}") from exc

    selected = select_tjnothop_candidates(
        discovered,
        start_date=start_date,
        end_date=local_date,
        max_candidates=15,
    )
    new_records: list[dict[str, Any]] = []
    for candidate in selected:
        time.sleep(3.0)
        try:
            if not candidate.published_at:
                raise ValueError("TJNOTHOP_INDEX_PUBLISHED_DATE_REQUIRED")
            detail_html = fetch_tjnothop_page(candidate.detail_url)
            new_records.append(
                parse_tjnothop_market_research(
                    detail_html,
                    source_url=candidate.detail_url,
                    index_url=TJNOTHOP_INDEX_URL,
                    index_published_at=candidate.published_at,
                    expected_title=candidate.title,
                    observed_at=observed_at,
                    opportunity_id=tjnothop_opportunity_id(candidate.detail_url),
                )
            )
        except Exception as exc:
            failures.append(
                {
                    "stage": "verified_detail",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
    if selected and not new_records:
        raise CollectorStageBlocked("TJNOTHOP_ALL_SELECTED_DETAILS_FAILED_VERIFICATION")

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TJNOTHOP_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "merged_record_count": len(merged),
        "failure_count": len(failures),
        "bootstrapped_records": bootstrapped,
        "publish_gate_reason": "PASS",
    }


def _run_teda(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    as_of = _cycle_as_of(state)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=TEDA_LOOKBACK_DAYS - 1)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records, bootstrapped = _cached_list(cache, TEDA_RECORDS_KEY, _bootstrap_teda_records)

    try:
        discovered = discover_teda_candidates(
            index_pages=TEDA_INDEX_PAGES,
            delay_seconds=TEDA_REQUEST_DELAY_SECONDS,
        )
    except Exception as exc:
        message = str(exc)[:180]
        raise CollectorStageBlocked(
            f"TEDA_INDEX_DISCOVERY_FAILED:{type(exc).__name__}:{message}"
        ) from exc

    new_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    out_of_window_count = 0
    considered = discovered[:TEDA_MAX_CANDIDATES]

    for candidate in considered:
        time.sleep(TEDA_REQUEST_DELAY_SECONDS)
        try:
            detail_html = fetch_teda_page_with_retry(
                candidate.detail_url,
                delay_seconds=TEDA_REQUEST_DELAY_SECONDS,
            )
            record = parse_teda_market_research(
                detail_html,
                source_url=candidate.detail_url,
                index_url=candidate.index_url,
                index_published_at=candidate.published_at,
                expected_title=candidate.title,
                observed_at=observed_at,
                opportunity_id=teda_opportunity_id(candidate.detail_url),
            )
            published_at = datetime.fromisoformat(record["facts"]["published_at"]).date()
            if not start_date <= published_at <= local_date:
                out_of_window_count += 1
                continue
            new_records.append(record)
        except TedaParseError as exc:
            if str(exc) in TEDA_UNSUPPORTED_DETAIL_CODES:
                unsupported.append(
                    {
                        "title": candidate.title,
                        "url": candidate.detail_url,
                        "reason": str(exc),
                    }
                )
                continue
            failures.append(
                {
                    "stage": "verified_detail",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "stage": "verified_detail",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    # Match the verified GitHub refresh policy: an unsupported candidate is an
    # explicit non-fact, but any true parse/fetch failure blocks this stage. Do
    # not update TEDA canonical state when the current verification is partial.
    if failures:
        diagnostic = ";".join(
            f"{item.get('error')}:{item.get('message')}"
            for item in failures[:3]
        )
        raise CollectorStageBlocked(
            f"TEDA_CANDIDATE_VERIFICATION_INCOMPLETE:{len(failures)}:{diagnostic}"
        )

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TEDA_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_early_title_count": len(discovered),
        "considered_candidate_count": len(considered),
        "new_verified_record_count": len(new_records),
        "out_of_window_count": out_of_window_count,
        "unsupported_candidate_count": len(unsupported),
        "merged_record_count": len(merged),
        "failure_count": 0,
        "bootstrapped_records": bootstrapped,
        "publish_gate_reason": "PASS",
    }



def _run_tjfch(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    as_of = _cycle_as_of(state)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=TJFCH_LOOKBACK_DAYS - 1)
    early_start_date = local_date - timedelta(days=TJFCH_TEST_LOOKBACK_DAYS - 1)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records, bootstrapped = _cached_list(cache, TJFCH_RECORDS_KEY, _bootstrap_tjfch_records)

    try:
        index_html = fetch_tjfch_page(TJFCH_INDEX_URL)
        discovered = parse_tjfch_index_html(index_html)
    except Exception as exc:
        raise CollectorStageBlocked(f"TJFCH_INDEX_DISCOVERY_FAILED:{type(exc).__name__}") from exc

    selected = select_tjfch_candidates(
        discovered,
        start_date=start_date,
        end_date=local_date,
        max_candidates=TJFCH_MAX_CANDIDATES,
    )
    new_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    for candidate in selected:
        time.sleep(TJFCH_REQUEST_DELAY_SECONDS)
        try:
            detail_html = fetch_tjfch_page(candidate.detail_url)
            new_records.append(
                parse_tjfch_procurement_notice(
                    detail_html,
                    source_url=candidate.detail_url,
                    index_url=TJFCH_INDEX_URL,
                    index_published_at=candidate.published_at,
                    expected_title=candidate.title,
                    observed_at=observed_at,
                    opportunity_id=tjfch_opportunity_id(candidate.detail_url),
                )
            )
        except TjfchParseError as exc:
            if str(exc) in {"TJFCH_BID_DEADLINE_NOT_EXACT", "TJFCH_NOTICE_TYPE_UNSUPPORTED"}:
                unsupported.append(
                    {
                        "feed": "in_hospital_procurement",
                        "title": candidate.title,
                        "url": candidate.detail_url,
                        "reason": str(exc),
                    }
                )
                continue
            failures.append(
                {
                    "stage": "verified_detail",
                    "feed": "in_hospital_procurement",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "stage": "verified_detail",
                    "feed": "in_hospital_procurement",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    try:
        early_index_html = fetch_tjfch_page(TJFCH_TEST_INDEX_URL)
        early_discovered = parse_tjfch_test_index_html(
            early_index_html,
            max_candidates=TJFCH_TEST_MAX_CANDIDATES,
        )
    except Exception as exc:
        raise CollectorStageBlocked(f"TJFCH_TEST_INDEX_DISCOVERY_FAILED:{type(exc).__name__}") from exc

    early_new_verified_record_count = 0
    early_out_of_window_count = 0
    for candidate in early_discovered:
        time.sleep(TJFCH_REQUEST_DELAY_SECONDS)
        try:
            detail_html = fetch_tjfch_page(candidate.detail_url)
            record = parse_tjfch_test_recruitment(
                detail_html,
                source_url=candidate.detail_url,
                index_url=TJFCH_TEST_INDEX_URL,
                expected_title=candidate.title,
                observed_at=observed_at,
                opportunity_id=tjfch_opportunity_id(candidate.detail_url),
            )
            published_at = datetime.fromisoformat(record["facts"]["published_at"]).date()
            if not early_start_date <= published_at <= local_date:
                early_out_of_window_count += 1
                continue
            new_records.append(record)
            early_new_verified_record_count += 1
        except TjfchTestParseError as exc:
            if str(exc) == "TJFCH_TEST_REGISTRATION_WINDOW_UNSUPPORTED":
                unsupported.append(
                    {
                        "feed": "pre_procurement_test_recruitment",
                        "title": candidate.title,
                        "url": candidate.detail_url,
                        "reason": str(exc),
                    }
                )
                continue
            failures.append(
                {
                    "stage": "verified_detail",
                    "feed": "pre_procurement_test_recruitment",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "stage": "verified_detail",
                    "feed": "pre_procurement_test_recruitment",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    # The two First Central Hospital feeds share one canonical cache state. Any
    # true fetch/parse inconsistency in either feed blocks the stage before the
    # combined state is written. Unsupported relative/exact-deadline formats are
    # explicit non-facts and never become invented public deadlines.
    if failures:
        diagnostic = ";".join(
            f"{item.get('feed')}:{item.get('error')}:{item.get('message')}"
            for item in failures[:3]
        )
        raise CollectorStageBlocked(
            f"TJFCH_CANDIDATE_VERIFICATION_INCOMPLETE:{len(failures)}:{diagnostic}"
        )

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TJFCH_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records) - early_new_verified_record_count,
        "early_discovered": len(early_discovered),
        "early_new_verified_record_count": early_new_verified_record_count,
        "early_out_of_window_count": early_out_of_window_count,
        "unsupported_candidate_count": len(unsupported),
        "merged_record_count": len(merged),
        "failure_count": 0,
        "bootstrapped_records": bootstrapped,
        "publish_gate_reason": "PASS",
    }


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _run_regional_market(
    cache: RuntimeCache,
    state: dict[str, Any],
    stage: str,
) -> dict[str, Any]:
    market_code = REGIONAL_STAGE_MARKET_CODES.get(stage)
    if not market_code:
        raise CollectorPrecondition(f"REGIONAL_STAGE_INVALID:{stage}")

    plan = load_regional_plan(DATA_ROOT / "multi_region_query_plan.json")
    market_by_code = {
        str(item["market_code"]).strip().upper(): item
        for item in plan["markets"]
    }
    market = market_by_code.get(market_code)
    if not market:
        raise CollectorPrecondition(f"REGIONAL_MARKET_NOT_CONFIGURED:{market_code}")

    as_of = _cycle_as_of(state)
    start_date, end_date = regional_date_window(as_of, plan["lookback_days"])
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    regional_records_key = _regional_records_key(market_code)
    existing_records, bootstrapped = _cached_list(
        cache,
        regional_records_key,
        lambda: _bootstrap_regional_records(market_code),
    )
    existing_source_urls = {
        str((record.get("source") or {}).get("url") or "")
        for record in existing_records
        if isinstance(record, dict) and str((record.get("source") or {}).get("url") or "")
    }

    session = RegionalCcgpSearchSession()
    discovered_by_url: dict[str, tuple[str, object]] = {}
    failures: list[dict[str, Any]] = []
    scoped_query_success_count = 0
    scoped_region_mismatch_count = 0

    for keyword in plan["keywords"]:
        for notice_type in plan["notice_types"]:
            try:
                items = fetch_regional_candidates_page(
                    session,
                    keyword=keyword,
                    notice_type=notice_type,
                    start_date=start_date,
                    end_date=end_date,
                    region=str(market["name"]),
                    page_index=1,
                )
                scoped_query_success_count += 1
                for item_notice_type, candidate in items:
                    actual_code = candidate_market_code(
                        getattr(candidate, "region", None),
                        plan["markets"],
                    )
                    if actual_code != market_code:
                        scoped_region_mismatch_count += 1
                        continue
                    if regional_candidate_skip_reason(candidate):
                        continue
                    discovered_by_url.setdefault(
                        str(candidate.detail_url),
                        (item_notice_type, candidate),
                    )
            except Exception as exc:
                failures.append({
                    "stage": "scoped_discovery",
                    "market_code": market_code,
                    "keyword": keyword,
                    "notice_type": notice_type,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                })
            time.sleep(plan["delay_seconds"])

    fallback_query_success_count = 0
    national_fallback_used = not bool(discovered_by_url)
    if national_fallback_used:
        for keyword in plan["keywords"]:
            for notice_type in plan["notice_types"]:
                for page_index in range(1, REGIONAL_FALLBACK_MAX_PAGES + 1):
                    try:
                        items = fetch_regional_candidates_page(
                            session,
                            keyword=keyword,
                            notice_type=notice_type,
                            start_date=start_date,
                            end_date=end_date,
                            region=None,
                            page_index=page_index,
                        )
                        fallback_query_success_count += 1
                    except Exception as exc:
                        failures.append({
                            "stage": "national_fallback_discovery",
                            "market_code": market_code,
                            "keyword": keyword,
                            "notice_type": notice_type,
                            "page_index": page_index,
                            "error": type(exc).__name__,
                            "message": str(exc)[:300],
                        })
                        break
                    if not items:
                        break
                    for item_notice_type, candidate in items:
                        actual_code = candidate_market_code(
                            getattr(candidate, "region", None),
                            plan["markets"],
                        )
                        if actual_code != market_code:
                            continue
                        if regional_candidate_skip_reason(candidate):
                            continue
                        discovered_by_url.setdefault(
                            str(candidate.detail_url),
                            (item_notice_type, candidate),
                        )
                    time.sleep(plan["delay_seconds"])
                time.sleep(plan["delay_seconds"])

    if scoped_query_success_count + fallback_query_success_count <= 0:
        raise CollectorStageBlocked(f"REGIONAL_ALL_DISCOVERY_QUERIES_FAILED:{market_code}")

    discovered = sorted(
        discovered_by_url.values(),
        key=lambda item: regional_candidate_selection_key(item[1], existing_source_urls),
        reverse=True,
    )
    selected = discovered[: plan["max_candidates_per_market"]]
    new_records: list[dict[str, Any]] = []

    for notice_type, candidate in selected:
        if candidate_market_code(getattr(candidate, "region", None), plan["markets"]) != market_code:
            failures.append({
                "stage": "pre_detail_market_guard",
                "market_code": market_code,
                "url": getattr(candidate, "detail_url", None),
            })
            continue
        try:
            time.sleep(plan["delay_seconds"])
            html = fetch_ccgp_detail_html(candidate.detail_url)
            record = VERIFIED_NOTICE_ADAPTERS[notice_type](
                html,
                source_url=candidate.detail_url,
                observed_at=observed_at,
                opportunity_id=stable_id(
                    f"ccgp_{market_code.lower()}",
                    candidate.detail_url,
                ),
            )
            new_records.append(annotate_regional_market(record, market))
        except Exception as exc:
            failures.append({
                "stage": "verified_detail",
                "market_code": market_code,
                "notice_type": notice_type,
                "title": getattr(candidate, "title", None),
                "url": getattr(candidate, "detail_url", None),
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            })

    if selected and not new_records:
        raise CollectorStageBlocked(
            f"REGIONAL_ALL_SELECTED_DETAILS_FAILED_VERIFICATION:{market_code}"
        )

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(
        cache,
        regional_records_key,
        merged,
        tag=f"medicalchannelai-collector-regional-{market_code.lower()}",
    )
    return {
        "market_code": market_code,
        "market_name": market["name"],
        "start_date": start_date,
        "end_date": end_date,
        "scoped_query_success_count": scoped_query_success_count,
        "scoped_region_mismatch_count": scoped_region_mismatch_count,
        "national_fallback_used": national_fallback_used,
        "national_fallback_query_success_count": fallback_query_success_count,
        "unique_candidate_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "merged_record_count": len(merged),
        "failure_count": len(failures),
        "bootstrapped_records": bootstrapped,
    }


def _persist_verified_snapshot_durably(snapshot: dict[str, Any]) -> dict[str, Any]:
    token = str(os.environ.get("VERIFIED_SNAPSHOT_PUBLISH_TOKEN") or "").strip()
    if len(token) < 24:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_TOKEN_MISSING")

    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        DURABLE_PUBLISH_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "MedicalChannelAI-VercelCollector/0.1",
        },
        method="PUT",
    )
    try:
        with urlopen(request, timeout=DURABLE_PUBLISH_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 0) or 0)
            body = response.read()
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:180]
        except Exception:
            detail = ""
        raise CollectorStageBlocked(
            f"DURABLE_SNAPSHOT_PUBLISH_HTTP_{exc.code}:{detail}"
        ) from exc
    except URLError as exc:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_NETWORK_FAILED") from exc

    if status != 200:
        raise CollectorStageBlocked(f"DURABLE_SNAPSHOT_PUBLISH_HTTP_{status}")
    try:
        result = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_RESPONSE_INVALID") from exc
    if result.get("ok") is not True:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_NOT_ACKNOWLEDGED")
    if result.get("snapshot_as_of") != snapshot.get("snapshot_as_of"):
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_AS_OF_MISMATCH")
    expected_pool = snapshot.get("opportunity_pool")
    expected_count = len(expected_pool) if isinstance(expected_pool, list) else len(snapshot.get("cards") or [])
    if int(result.get("opportunity_pool_count") or -1) != expected_count:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_POOL_MISMATCH")
    return result


def _run_publish(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    ccgp_records = cache.get(CCGP_RECORDS_KEY)
    events = cache.get(CCGP_EVENTS_KEY)
    tjmugh_records = cache.get(TJMUGH_RECORDS_KEY)
    tjnothop_records = cache.get(TJNOTHOP_RECORDS_KEY)
    teda_records = cache.get(TEDA_RECORDS_KEY)
    tjfch_records = cache.get(TJFCH_RECORDS_KEY)
    regional_records_by_market = {
        market_code: cache.get(_regional_records_key(market_code))
        for market_code in REGIONAL_STAGE_MARKET_CODES.values()
    }
    canonical_by_name = {
        "ccgp": ccgp_records,
        "events": events,
        "tjmugh": tjmugh_records,
        "tjnothop": tjnothop_records,
        "teda": teda_records,
        "tjfch": tjfch_records,
        **{
            f"regional_{market_code.lower()}": value
            for market_code, value in regional_records_by_market.items()
        },
    }
    missing_canonical = [
        name
        for name, value in canonical_by_name.items()
        if not isinstance(value, list)
    ]
    if missing_canonical:
        raise CollectorPrecondition(
            "COLLECTOR_CANONICAL_STATE_INCOMPLETE:" + ",".join(sorted(missing_canonical))
        )

    regional_records = [
        record
        for market_code in REGIONAL_STAGE_MARKET_CODES.values()
        for record in regional_records_by_market[market_code]
    ]
    records = (
        list(ccgp_records)
        + list(tjmugh_records)
        + list(tjnothop_records)
        + list(teda_records)
        + list(tjfch_records)
        + regional_records
    )
    as_of = _cycle_as_of(state)
    snapshot = build_public_snapshot(records, as_of, list(events))
    digest = _digest(snapshot)
    _cache_set(
        cache,
        LATEST_RUNTIME_SNAPSHOT_KEY,
        snapshot,
        tag="medicalchannelai-verified-snapshot",
        ttl=SNAPSHOT_TTL_SECONDS,
    )
    read_back = cache.get(LATEST_RUNTIME_SNAPSHOT_KEY)
    if not isinstance(read_back, dict) or _digest(read_back) != digest:
        raise CollectorStageBlocked("RUNTIME_SNAPSHOT_READBACK_MISMATCH")

    # Node public serving reads this exact stable key. It is intentionally written
    # without TTL/tags so the collector cannot expire the serving snapshot merely
    # because the short-lived collector state ages out.
    durable_result = _persist_verified_snapshot_durably(snapshot)

    cache.set(PUBLISHED_RUNTIME_SNAPSHOT_KEY, snapshot, {})
    serving_read_back = cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
    if not isinstance(serving_read_back, dict) or _digest(serving_read_back) != digest:
        raise CollectorStageBlocked("SERVING_SNAPSHOT_READBACK_MISMATCH")

    pool = read_back.get("opportunity_pool")
    return {
        "snapshot_as_of": read_back.get("snapshot_as_of"),
        "today_card_count": len(read_back.get("cards") or []),
        "opportunity_pool_count": len(pool) if isinstance(pool, list) else len(read_back.get("cards") or []),
        "canonical_record_count": len(records),
        "notice_event_count": len(events),
        "sha256": digest,
        "durable_snapshot_persisted": True,
        "durable_snapshot_as_of": durable_result.get("snapshot_as_of"),
    }


def run_stage(stage: str, *, now: datetime | None = None) -> tuple[int, dict[str, Any]]:
    now = now or _now_utc()
    cache = RuntimeCache()
    try:
        state, previous = _prepare_stage(cache, stage, now)
    except CollectorPrecondition as exc:
        return 409, {"action": "REJECTED", "stage": stage, "error": str(exc), "error_code": exc.code}

    if previous is not None:
        return 200, {
            "action": "ALREADY_COMPLETED_TODAY",
            "stage": stage,
            "local_date": state.get("local_date"),
            "completed_at": previous.get("completed_at"),
            "result": previous.get("result"),
        }

    try:
        if stage == "ccgp":
            result = _run_ccgp(cache, state)
        elif stage.startswith("event"):
            result = _run_event_batch(cache, state, stage)
        elif stage == "tjmugh":
            result = _run_tjmugh(cache, state)
        elif stage == "tjnothop":
            result = _run_tjnothop(cache, state)
        elif stage == "teda":
            result = _run_teda(cache, state)
        elif stage == "tjfch":
            result = _run_tjfch(cache, state)
        elif stage in REGIONAL_STAGE_MARKET_CODES:
            result = _run_regional_market(cache, state, stage)
        elif stage == "publish":
            result = _run_publish(cache, state)
        else:
            raise CollectorPrecondition(f"COLLECTOR_STAGE_INVALID:{stage}")
    except Exception as exc:
        _mark_failed(cache, state, stage, exc)
        return 503, {
            "action": "FAILED",
            "stage": stage,
            "local_date": state.get("local_date"),
            "error_code": getattr(exc, "code", type(exc).__name__),
            "error": str(exc)[:300],
        }

    _mark_completed(cache, state, stage, result)
    return 200, {
        "action": "COMPLETED",
        "stage": stage,
        "local_date": state.get("local_date"),
        "result": result,
    }
