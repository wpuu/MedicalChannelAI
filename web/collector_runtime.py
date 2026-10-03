from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from vercel.functions import RuntimeCache

WEB_ROOT = Path(__file__).resolve().parent
PIPELINE_ROOT = WEB_ROOT / "pipeline"
SCRIPT_DIR = PIPELINE_ROOT / "scripts"
DATA_ROOT = PIPELINE_ROOT / "data"
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from medical_channel_pipeline import build_public_snapshot  # noqa: E402
from medical_channel_pipeline.validation import validate_records  # noqa: E402
from publish_web_snapshot import combine_snapshots  # noqa: E402
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
_SCHEDULED_CYCLE = ContextVar("scheduled_collector_cycle", default=None)
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
# Historical stores already included in static publication. No acquisition
# stage or bootstrap is added: verified restoration must provide these arrays.
PRESERVED_SOURCE_RECORDS_KEYS = {
    "tjzxfc": "medicalchannelai:collector-tjzxfc-records:v2",
    "tjzyefy": "medicalchannelai:collector-tjzyefy-records:v2",
    "tjzyefy-intent": "medicalchannelai:collector-tjzyefy-intent-records:v2",
}
DURABLE_PUBLISH_URL = "https://medicalchannelai.vercel.app/api/public-snapshot"
DURABLE_PUBLISH_TIMEOUT_SECONDS = 30

REGIONAL_STAGE_MARKET_CODES = {
    "regional_bj": "BJ",
    "regional_he": "HE",
    "regional_ln": "LN",
    "regional_jl": "JL",
    "regional_hl": "HL",
}
REGIONAL_FALLBACK_STAGE_MARKET_CODES = {
    "regional_bj_fallback": "BJ",
    "regional_he_fallback": "HE",
    "regional_ln_fallback": "LN",
    "regional_jl_fallback": "JL",
    "regional_hl_fallback": "HL",
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
    "regional_bj_fallback",
    "regional_he",
    "regional_he_fallback",
    "regional_ln",
    "regional_ln_fallback",
    "regional_jl",
    "regional_jl_fallback",
    "regional_hl",
    "regional_hl_fallback",
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

    def __init__(
        self,
        message: str,
        *,
        diagnostics: list[dict[str, Any]] | None = None,
        durable_accepted: bool = False,
        durable_snapshot_as_of: str | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or []
        self.durable_accepted = durable_accepted
        self.durable_snapshot_as_of = durable_snapshot_as_of


class CollectorPrecondition(CollectorError):
    code = "COLLECTOR_PRECONDITION_FAILED"


class CollectorStageBlocked(CollectorError):
    code = "COLLECTOR_STAGE_BLOCKED"


STAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    **{f"event{index}": ("ccgp",) for index in range(1, 7)},
    **{f"{stage}_fallback": (stage,) for stage in REGIONAL_STAGE_MARKET_CODES},
}
PUBLISH_REQUIRED_STAGES = (
    "ccgp", "event1", "event2", "event3", "event4", "event5", "event6",
    "tjmugh", "tjnothop", "teda", "tjfch",
    "regional_bj", "regional_he", "regional_ln", "regional_jl", "regional_hl",
)
DIAGNOSTIC_STAGES = {
    "index_discovery", "scoped_discovery", "national_fallback_discovery",
    "verified_detail", "event_search", "publish", "dependency",
}
DIAGNOSTIC_CATEGORIES = {
    "ACCESS_DENIED", "TRANSIENT_FETCH_ERROR", "PERMANENT_HTTP_ERROR",
    "PARSER_REJECTED", "EVIDENCE_VALIDATION_FAILED", "DEPENDENCY_BLOCKED",
    "PUBLISH_REJECTED", "UNEXPECTED_ERROR",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _assert_cycle_owned(cache: RuntimeCache) -> None:
    cycle_id = _SCHEDULED_CYCLE.get()
    if cycle_id:
        from collector_namespace import ACTIVE_CYCLE_KEY, active_cycle_id
        if active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)) != cycle_id:
            raise CollectorPrecondition("COLLECTOR_CYCLE_SUPERSEDED")


def _cache_set(cache: RuntimeCache, key: str, value: Any, *, tag: str, ttl: int = STATE_TTL_SECONDS) -> None:
    _assert_cycle_owned(cache)
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
    # Seed data can initialize a brand-new runtime. Once any confirmed public
    # snapshot exists, an evicted source shard has unknown newer history and must
    # not be replaced by an older seed array.
    if (
        _SCHEDULED_CYCLE.get() is not None
        or isinstance(cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY), dict)
        or isinstance(cache.get(LATEST_RUNTIME_SNAPSHOT_KEY), dict)
    ):
        raise CollectorPrecondition("COLLECTOR_CANONICAL_HISTORY_UNAVAILABLE")
    records = bootstrap()
    _cache_set(cache, key, records, tag="medicalchannelai-collector-canonical")
    return records, True


def _new_cycle(now: datetime) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "cycle_id": _SCHEDULED_CYCLE.get(),
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

    cycle_id = _SCHEDULED_CYCLE.get()
    different_cycle = cycle_id is not None and state.get("cycle_id") != cycle_id
    if stage == "ccgp" and (state.get("local_date") != local_date or different_cycle):
        state = _new_cycle(now)
        _write_status(cache, state)
    elif state.get("local_date") != local_date or different_cycle:
        raise CollectorPrecondition("COLLECTOR_CYCLE_NOT_STARTED_TODAY")

    stages = state.setdefault("stages", {})
    previous = stages.get(stage)
    if cycle_id and isinstance(previous, dict) and previous.get("status") == "RUNNING":
        from collector_schedule import running_stage_is_live
        if running_stage_is_live({"stages": {stage: previous}}, _now_utc()):
            raise CollectorPrecondition("COLLECTOR_STAGE_ALREADY_RUNNING")
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
    elif isinstance(previous, dict) and previous.get("status") == "BLOCKED" and previous.get("terminal") is True:
        return state, previous
    elif isinstance(previous, dict) and previous.get("status") == "FAILED" and previous.get("terminal") is True:
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
        if not isinstance(required_state, dict):
            raise CollectorPrecondition(f"COLLECTOR_PREVIOUS_STAGE_STATE_MISSING:{required}")
        if required_state.get("status") not in {"COMPLETED", "FAILED", "BLOCKED"} or (
            required_state.get("status") in {"FAILED", "BLOCKED"} and required_state.get("terminal") is not True
        ):
            raise CollectorPrecondition(f"COLLECTOR_PREVIOUS_STAGE_INCOMPLETE:{required}")

    dependencies = STAGE_DEPENDENCIES.get(stage, ())
    failed_dependencies = []
    incomplete_dependencies = []
    for dependency in dependencies:
        dependency_state = stages.get(dependency)
        if isinstance(dependency_state, dict) and dependency_state.get("status") in {"FAILED", "BLOCKED"} and dependency_state.get("terminal") is True:
            failed_dependencies.append(dependency)
        elif not isinstance(dependency_state, dict) or dependency_state.get("status") != "COMPLETED":
            incomplete_dependencies.append(dependency)
    if incomplete_dependencies:
        raise CollectorPrecondition("COLLECTOR_DEPENDENCY_INCOMPLETE:" + ",".join(incomplete_dependencies))
    if failed_dependencies:
        diagnostic = {
            "source_id": _source_id_for_stage(stage),
            "market_code": REGIONAL_STAGE_MARKET_CODES.get(stage) or REGIONAL_FALLBACK_STAGE_MARKET_CODES.get(stage),
            "stage": "dependency",
            "category": "DEPENDENCY_BLOCKED",
            "error_code": "COLLECTOR_DEPENDENCY_FAILED",
            "error_type": "CollectorPrecondition",
        }
        stages[stage] = {
            "status": "BLOCKED",
            "terminal": True,
            "attempt_count": int(previous.get("attempt_count", 0)) if isinstance(previous, dict) else 0,
            "started_at": None,
            "completed_at": now.isoformat(),
            "error_code": "COLLECTOR_DEPENDENCY_FAILED",
            "error_message": "COLLECTOR_DEPENDENCY_FAILED",
            "diagnostics": [diagnostic],
            "result": {"blocked_by": failed_dependencies},
        }
        _write_status(cache, state)
        return state, stages[stage]

    if stage == "publish":
        failed_sources, incomplete_sources = _publish_stage_requirements(stages)
        if incomplete_sources:
            raise CollectorPrecondition("COLLECTOR_PUBLISH_SOURCE_STATE_INCOMPLETE:" + ",".join(incomplete_sources))
        if failed_sources:
            diagnostic = {
                "source_id": "publish",
                "market_code": None,
                "stage": "dependency",
                "category": "DEPENDENCY_BLOCKED",
                "error_code": "COLLECTOR_PUBLISH_SOURCE_FAILED",
                "error_type": "CollectorPrecondition",
            }
            stages[stage] = {
                "status": "BLOCKED",
                "terminal": True,
                "attempt_count": int(previous.get("attempt_count", 0)) if isinstance(previous, dict) else 0,
                "started_at": None,
                "completed_at": now.isoformat(),
                "error_code": "COLLECTOR_PUBLISH_SOURCE_FAILED",
                "error_message": "COLLECTOR_PUBLISH_SOURCE_FAILED",
                "diagnostics": [diagnostic],
                "result": {"blocked_by": failed_sources},
            }
            _write_status(cache, state)
            return state, stages[stage]

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
    regional_timeout_split_replay = (
        stage in REGIONAL_STAGE_MARKET_CODES
        and isinstance(previous, dict)
        and previous.get("status") == "RUNNING"
        and attempts in {MAX_STAGE_ATTEMPTS_PER_DAY, MAX_STAGE_ATTEMPTS_PER_DAY + 1}
        and isinstance(stages.get("publish"), dict)
        and str(stages["publish"].get("error_message") or "").startswith("COLLECTOR_CANONICAL_STATE_INCOMPLETE")
        and f"{stage}_fallback" not in stages
    )
    if (
        attempts >= MAX_STAGE_ATTEMPTS_PER_DAY
        and not tjfch_policy_recovery_retry
        and not regional_cache_replay
        and not regional_stale_migration_replay
        and not publish_cache_migration_retry
        and not regional_timeout_split_replay
    ):
        current = previous if isinstance(previous, dict) else {}
        current["status"] = "FAILED"
        current["terminal"] = True
        current["completed_at"] = current.get("completed_at") or now.isoformat()
        current["error_code"] = current.get("error_code") or "COLLECTOR_STAGE_RETRY_LIMIT"
        current["error_message"] = current.get("error_message") or "COLLECTOR_STAGE_RETRY_LIMIT"
        current.setdefault("diagnostics", [_make_diagnostic(stage, CollectorStageBlocked("COLLECTOR_STAGE_RETRY_LIMIT"), market_code=REGIONAL_STAGE_MARKET_CODES.get(stage) or REGIONAL_FALLBACK_STAGE_MARKET_CODES.get(stage))])
        stages[stage] = current
        _write_status(cache, state)
        return state, current

    stages[stage] = {
        "status": "RUNNING",
        "terminal": False,
        "attempt_count": attempts + 1,
        "started_at": (_now_utc() if cycle_id else now).isoformat(),
        "completed_at": None,
        "error_code": None,
        "error_message": None,
        "diagnostics": [],
        "result": None,
    }
    _write_status(cache, state)
    return state, None


def _latest_stage_state_for_update(
    cache: RuntimeCache,
    state: dict[str, Any],
    stage: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    latest = load_status(cache)
    if latest.get("local_date") != state.get("local_date") or latest.get("cycle_id") != state.get("cycle_id"):
        raise CollectorPrecondition("COLLECTOR_STATE_DATE_CHANGED_DURING_STAGE")
    latest_stages = latest.setdefault("stages", {})
    latest_stage = latest_stages.get(stage)
    if not isinstance(latest_stage, dict):
        original = (state.get("stages") or {}).get(stage)
        if not isinstance(original, dict):
            raise CollectorPrecondition(f"COLLECTOR_STAGE_STATE_MISSING:{stage}")
        latest_stage = dict(original)
        latest_stages[stage] = latest_stage
    return latest, latest_stage


def _mark_completed(cache: RuntimeCache, state: dict[str, Any], stage: str, result: dict[str, Any]) -> None:
    latest, current = _latest_stage_state_for_update(cache, state, stage)
    current["status"] = "COMPLETED"
    current["terminal"] = True
    current["completed_at"] = _now_utc().isoformat()
    current["result"] = result
    current["error_code"] = None
    current["error_message"] = None
    current["diagnostics"] = result.get("diagnostics", []) if isinstance(result.get("diagnostics"), list) else []
    _write_status(cache, latest)


def _mark_failed(cache: RuntimeCache, state: dict[str, Any], stage: str, exc: Exception) -> None:
    latest, current = _latest_stage_state_for_update(cache, state, stage)
    current["status"] = "FAILED"
    current["terminal"] = False
    current["completed_at"] = _now_utc().isoformat()
    current["error_code"] = _safe_error_code(exc)
    current["error_message"] = _safe_error_code(exc)
    current["diagnostics"] = _bounded_diagnostics(stage, exc)
    _write_status(cache, latest)


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
        raise CollectorStageBlocked(
            f"CCGP_PUBLISH_GATE:{reason}{suffix}",
            diagnostics=detail_failures[:5],
        )

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
        "canonical_changed": _canonical_content_digest(merged_records) != _canonical_content_digest(existing_records),
        "merged_record_count": len(merged_records),
        "event_watch_project_count": len(watch_projects),
        "failure_count": len(failures),
        "diagnostics": _diagnostics_from_items("ccgp", failures),
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
        "canonical_changed": _canonical_content_digest(merged_events) != _canonical_content_digest(existing_events),
        "merged_event_count": len(merged_events),
        "failure_count": len(failures),
        "diagnostics": _diagnostics_from_items(stage, failures),
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
        raise CollectorStageBlocked(
            f"TJMUGH_INDEX_DISCOVERY_FAILED:{type(exc).__name__}",
            diagnostics=[{"stage": "index_discovery", "error": type(exc).__name__, "message": str(exc), "url": TJMUGH_INDEX_URL}],
        ) from exc

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
        raise CollectorStageBlocked("TJMUGH_ALL_SELECTED_DETAILS_FAILED_VERIFICATION", diagnostics=failures[:5])

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TJMUGH_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "canonical_changed": _canonical_content_digest(merged) != _canonical_content_digest(existing_records),
        "merged_record_count": len(merged),
        "failure_count": len(failures),
        "diagnostics": _diagnostics_from_items("tjmugh", failures),
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
        raise CollectorStageBlocked(
            f"TJNOTHOP_INDEX_DISCOVERY_FAILED:{type(exc).__name__}",
            diagnostics=[{"stage": "index_discovery", "error": type(exc).__name__, "message": str(exc), "url": TJNOTHOP_INDEX_URL}],
        ) from exc

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
        raise CollectorStageBlocked("TJNOTHOP_ALL_SELECTED_DETAILS_FAILED_VERIFICATION", diagnostics=failures[:5])

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TJNOTHOP_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "canonical_changed": _canonical_content_digest(merged) != _canonical_content_digest(existing_records),
        "merged_record_count": len(merged),
        "failure_count": len(failures),
        "diagnostics": _diagnostics_from_items("tjnothop", failures),
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
        raise CollectorStageBlocked(
            f"TEDA_INDEX_DISCOVERY_FAILED:{type(exc).__name__}",
            diagnostics=[{"stage": "index_discovery", "error": type(exc).__name__, "message": str(exc), "url": "https://www.tedahospital.com.cn/article/plist/9"}],
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
            f"TEDA_CANDIDATE_VERIFICATION_INCOMPLETE:{len(failures)}",
            diagnostics=failures[:5],
        )

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TEDA_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_early_title_count": len(discovered),
        "considered_candidate_count": len(considered),
        "new_verified_record_count": len(new_records),
        "canonical_changed": _canonical_content_digest(merged) != _canonical_content_digest(existing_records),
        "out_of_window_count": out_of_window_count,
        "unsupported_candidate_count": len(unsupported),
        "merged_record_count": len(merged),
        "failure_count": 0,
        "diagnostics": [],
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
        raise CollectorStageBlocked(
            f"TJFCH_INDEX_DISCOVERY_FAILED:{type(exc).__name__}",
            diagnostics=[{"stage": "index_discovery", "error": type(exc).__name__, "message": str(exc), "url": TJFCH_INDEX_URL}],
        ) from exc

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
        raise CollectorStageBlocked(
            f"TJFCH_TEST_INDEX_DISCOVERY_FAILED:{type(exc).__name__}",
            diagnostics=[{"stage": "index_discovery", "error": type(exc).__name__, "message": str(exc), "url": TJFCH_TEST_INDEX_URL}],
        ) from exc

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
        raise CollectorStageBlocked(
            f"TJFCH_CANDIDATE_VERIFICATION_INCOMPLETE:{len(failures)}",
            diagnostics=failures[:5],
        )

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TJFCH_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records) - early_new_verified_record_count,
        "canonical_changed": _canonical_content_digest(merged) != _canonical_content_digest(existing_records),
        "early_discovered": len(early_discovered),
        "early_new_verified_record_count": early_new_verified_record_count,
        "early_out_of_window_count": early_out_of_window_count,
        "unsupported_candidate_count": len(unsupported),
        "merged_record_count": len(merged),
        "failure_count": 0,
        "diagnostics": [],
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
    fallback_only = stage in REGIONAL_FALLBACK_STAGE_MARKET_CODES
    market_code = (
        REGIONAL_FALLBACK_STAGE_MARKET_CODES.get(stage)
        if fallback_only
        else REGIONAL_STAGE_MARKET_CODES.get(stage)
    )
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

    if fallback_only:
        primary_stage = stage.removesuffix("_fallback")
        primary = (state.get("stages") or {}).get(primary_stage)
        primary_result = primary.get("result") if isinstance(primary, dict) else None
        if not isinstance(primary_result, dict):
            raise CollectorPrecondition(f"REGIONAL_PRIMARY_RESULT_MISSING:{market_code}")
        if primary_result.get("fallback_required") is not True:
            return {
                "market_code": market_code,
                "market_name": market["name"],
                "fallback_required": False,
                "fallback_skipped": True,
                "merged_record_count": len(_bootstrap_regional_records(market_code)),
            }

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

    if not fallback_only:
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
    scoped_found_candidates = bool(discovered_by_url)
    national_fallback_used = fallback_only
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

    if fallback_only and fallback_query_success_count <= 0:
        raise CollectorStageBlocked(
            f"REGIONAL_ALL_DISCOVERY_QUERIES_FAILED:{market_code}",
            diagnostics=failures[:5],
        )

    if stage == "regional_bj" and not scoped_found_candidates:
        _cache_set(
            cache,
            regional_records_key,
            existing_records,
            tag="medicalchannelai-collector-regional-bj",
        )
        return {
            "market_code": market_code,
            "market_name": market["name"],
            "start_date": start_date,
            "end_date": end_date,
            "scoped_query_success_count": scoped_query_success_count,
            "scoped_region_mismatch_count": scoped_region_mismatch_count,
            "national_fallback_used": False,
            "fallback_required": True,
            "national_fallback_query_success_count": 0,
            "unique_candidate_count": 0,
            "selected_candidate_count": 0,
            "new_verified_record_count": 0,
            "canonical_changed": False,
            "merged_record_count": len(existing_records),
            "failure_count": len(failures),
            "diagnostics": _diagnostics_from_items(stage, failures),
            "bootstrapped_records": bootstrapped,
        }

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
            f"REGIONAL_ALL_SELECTED_DETAILS_FAILED_VERIFICATION:{market_code}",
            diagnostics=failures[:5],
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
        "fallback_required": (not fallback_only and not scoped_found_candidates),
        "national_fallback_query_success_count": fallback_query_success_count,
        "unique_candidate_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "canonical_changed": _canonical_content_digest(merged) != _canonical_content_digest(existing_records),
        "merged_record_count": len(merged),
        "failure_count": len(failures),
        "diagnostics": _diagnostics_from_items(stage, failures),
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
        durable_receipt: Any = None
        try:
            body = exc.read(16_384)
            durable_receipt = json.loads(body.decode("utf-8"))
        except Exception:
            durable_receipt = None
        durable_accepted = (
            isinstance(durable_receipt, dict)
            and durable_receipt.get("durable_accepted") is True
            and durable_receipt.get("snapshot_as_of") == snapshot.get("snapshot_as_of")
        )
        raise CollectorStageBlocked(
            f"DURABLE_SNAPSHOT_PUBLISH_HTTP_{exc.code}",
            durable_accepted=durable_accepted,
            durable_snapshot_as_of=(
                str(durable_receipt.get("snapshot_as_of")) if durable_accepted else None
            ),
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
    acknowledged_count = result.get("opportunity_pool_count")
    if type(acknowledged_count) is not int or acknowledged_count < 0 or acknowledged_count != expected_count:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_POOL_MISMATCH")
    return result


def _require_published_canonical_history(
    cache: RuntimeCache,
    records: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> None:
    if _SCHEDULED_CYCLE.get() is None:
        return
    # The full, read-back published baseline is a recovery prerequisite. Public
    # cards are only a projection: never fabricate canonical rows from them.
    baseline = cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
    if not isinstance(baseline, dict):
        raise CollectorPrecondition("COLLECTOR_PUBLISHED_BASELINE_UNAVAILABLE")
    pool = baseline.get("opportunity_pool")
    count = baseline.get("opportunity_pool_count")
    try:
        clock = datetime.fromisoformat(str(baseline.get("snapshot_as_of") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise CollectorPrecondition("COLLECTOR_PUBLISHED_BASELINE_INVALID") from exc
    if (
        clock.tzinfo is None
        or clock > as_of
        or not isinstance(pool, list)
        or type(count) is not int
        or count != len(pool)
    ):
        raise CollectorPrecondition("COLLECTOR_PUBLISHED_BASELINE_INVALID")
    published_ids: set[str] = set()
    for card in pool:
        opportunity_id = card.get("opportunity_id") if isinstance(card, dict) else None
        if (
            not isinstance(opportunity_id, str)
            or not opportunity_id.strip()
            or opportunity_id != opportunity_id.strip()
            or opportunity_id in published_ids
        ):
            raise CollectorPrecondition("COLLECTOR_PUBLISHED_BASELINE_INVALID")
        published_ids.add(opportunity_id)
    canonical_ids = {
        record.get("opportunity_id")
        for record in records
        if isinstance(record, dict) and isinstance(record.get("opportunity_id"), str)
    }
    if not published_ids.issubset(canonical_ids):
        raise CollectorPrecondition("COLLECTOR_CANONICAL_PUBLISHED_HISTORY_MISSING")


def _preserved_source_history(cache: RuntimeCache) -> list[dict[str, Any]]:
    if _SCHEDULED_CYCLE.get() is None:
        return []
    history = []
    for source, key in PRESERVED_SOURCE_RECORDS_KEYS.items():
        rows = cache.get(key)
        if not isinstance(rows, list):
            raise CollectorPrecondition("COLLECTOR_PRESERVED_HISTORY_UNAVAILABLE:" + source)
        try:
            validate_records(rows)
            for row in rows:
                if not str(row["source"]["source_id"]).startswith(source + ":"):
                    raise ValueError("WRONG_HISTORICAL_SOURCE")
                if str(row["facts"].get("market_code") or "TJ").upper() != "TJ":
                    raise ValueError("WRONG_HISTORICAL_MARKET")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise CollectorPrecondition("COLLECTOR_PRESERVED_HISTORY_INVALID:" + source) from exc
        history.extend(rows)
    return history


def _build_scheduled_public_snapshot(
    tianjin_records: list[dict[str, Any]],
    regional_records: list[dict[str, Any]],
    as_of: datetime,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    ids = [row.get("opportunity_id") for row in tianjin_records + regional_records]
    if len(ids) != len(set(ids)):
        raise CollectorPrecondition("COLLECTOR_CANONICAL_ID_CONFLICT")
    # Keep canonical immutable and follow the existing static publication
    # transform, including market metadata and Tianjin-only event isolation.
    local = json.loads(json.dumps(tianjin_records))
    for row in local:
        facts = row["facts"]
        if (str(facts.get("market_code") or "").strip().upper() or "TJ") != "TJ":
            raise CollectorPrecondition("COLLECTOR_CANONICAL_MARKET_MISMATCH")
        facts["market_code"] = "TJ"
        for field, value in (("market_name", "天津"), ("market_admin_code", "120000")):
            if not str(facts.get(field) or "").strip():
                facts[field] = value
    for row in regional_records:
        facts = row.get("facts") or {}
        if (
            facts.get("market_code") not in REGIONAL_STAGE_MARKET_CODES.values()
            or not facts.get("market_name")
            or not facts.get("market_admin_code")
        ):
            raise CollectorPrecondition("COLLECTOR_CANONICAL_MARKET_MISMATCH")
    return combine_snapshots(
        build_public_snapshot(local, as_of, events),
        build_public_snapshot(regional_records, as_of, []),
        local + regional_records, as_of,
    )


def _run_publish(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    stages = state.get("stages")
    if isinstance(stages, dict):
        failed_sources, incomplete_sources = _publish_stage_requirements(stages)
        if incomplete_sources:
            raise CollectorPrecondition("COLLECTOR_PUBLISH_SOURCE_STATE_INCOMPLETE:" + ",".join(incomplete_sources))
        if failed_sources:
            raise CollectorStageBlocked("COLLECTOR_PUBLISH_SOURCE_FAILED:" + ",".join(failed_sources))
    ccgp_records, _ = _cached_list(cache, CCGP_RECORDS_KEY, _bootstrap_ccgp_records)
    events, _ = _cached_list(cache, CCGP_EVENTS_KEY, _bootstrap_ccgp_events)
    tjmugh_records, _ = _cached_list(cache, TJMUGH_RECORDS_KEY, _bootstrap_tjmugh_records)
    tjnothop_records, _ = _cached_list(cache, TJNOTHOP_RECORDS_KEY, _bootstrap_tjnothop_records)
    teda_records, _ = _cached_list(cache, TEDA_RECORDS_KEY, _bootstrap_teda_records)
    tjfch_records, _ = _cached_list(cache, TJFCH_RECORDS_KEY, _bootstrap_tjfch_records)
    regional_records_by_market = {}
    for market_code in REGIONAL_STAGE_MARKET_CODES.values():
        regional_records_by_market[market_code], _ = _cached_list(
            cache,
            _regional_records_key(market_code),
            lambda code=market_code: _bootstrap_regional_records(code),
        )
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
    tianjin_records = (
        list(ccgp_records)
        + list(tjmugh_records)
        + list(tjnothop_records)
        + list(teda_records)
        + list(tjfch_records)
        + _preserved_source_history(cache)
    )
    records = tianjin_records + regional_records
    as_of = _cycle_as_of(state)
    _require_published_canonical_history(cache, records, as_of=as_of)
    snapshot = (
        _build_scheduled_public_snapshot(tianjin_records, regional_records, as_of, list(events))
        if _SCHEDULED_CYCLE.get() is not None
        else build_public_snapshot(records, as_of, list(events))
    )
    incremental_source = str(state.get("incremental_source") or "").strip().lower()
    if incremental_source:
        last_complete_as_of = str(state.get("last_complete_as_of") or "").strip()
        current = load_status(cache)
        prior_snapshot = cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
        prior_coverage = prior_snapshot.get("collection_coverage") if isinstance(prior_snapshot, dict) else None
        prior_failed = set(prior_coverage.get("failed_source_ids") or []) if isinstance(prior_coverage, dict) else set()
        stage_to_source = {
            **{f"event{index}": "ccgp_events" for index in range(1, 7)},
            **{stage: f"ccgp_regional:{code.lower()}" for stage, code in REGIONAL_STAGE_MARKET_CODES.items()},
            **{f"{stage}_fallback": f"ccgp_regional:{code.lower()}" for stage, code in REGIONAL_STAGE_MARKET_CODES.items()},
        }
        stage_to_source.update({stage: stage for stage in ("ccgp", "tjmugh", "tjnothop", "teda", "tjfch")})
        current_stages = current.get("stages") or {}
        cleared_sources = {
            stage_to_source[stage]
            for stage, item in current_stages.items()
            if stage in stage_to_source and isinstance(item, dict) and item.get("status") == "COMPLETED"
        }
        resolved_by_incremental = {incremental_source}
        failed_source_ids = prior_failed - cleared_sources
        failed_source_ids.update(
            f"ccgp_regional:{item.get('market_code', '').lower()}" if item.get("source_id") == "ccgp_regional" and item.get("market_code") else str(item.get("source_id"))
            for stage_state in current_stages.values()
            if isinstance(stage_state, dict) and stage_state.get("status") in {"FAILED", "BLOCKED"}
            for item in (stage_state.get("diagnostics") or [])
            if isinstance(item, dict) and item.get("source_id") not in {None, "publish"}
        )
        failed_source_ids.difference_update(resolved_by_incremental)
        snapshot["collection_coverage"] = {
            "complete": False,
            "last_complete_as_of": last_complete_as_of or None,
            "updated_source_ids": [incremental_source],
            "failed_source_ids": sorted(failed_source_ids),
        }
        snapshot["source_refresh"] = {
            "source_id": incremental_source,
            "observed_at": as_of.isoformat(),
            "scope": "SOURCE_ONLY",
        }
    else:
        stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
        updated_source_ids = _changed_sources_from_stages(stages)
        snapshot["collection_coverage"] = {
            "complete": True,
            "last_complete_as_of": snapshot.get("snapshot_as_of"),
            "updated_source_ids": updated_source_ids,
            "failed_source_ids": [],
        }
        if _SCHEDULED_CYCLE.get() is not None:
            prior = cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
            prior_coverage = prior.get("collection_coverage") if isinstance(prior, dict) else None
            snapshot["collection_coverage"].update({
                # Preserving archived sources is not a fresh collection of them.
                # Existing UI/AI and durable base-match gates honor partial scope.
                "complete": False,
                "last_complete_as_of": prior_coverage.get("last_complete_as_of") if isinstance(prior_coverage, dict) else None,
                "history_only_source_ids": list(PRESERVED_SOURCE_RECORDS_KEYS),
            })
    digest = _digest(snapshot)
    old_latest = cache.get(LATEST_RUNTIME_SNAPSHOT_KEY)
    old_published = cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
    # The public durable store is the acceptance point. Do not advance either
    # reader-facing cache before it confirms this exact candidate.
    _assert_cycle_owned(cache)
    durable_result = _persist_verified_snapshot_durably(snapshot)
    try:
        # Node public serving reads this stable key without TTL/tags.
        _assert_cycle_owned(cache)
        cache.set(PUBLISHED_RUNTIME_SNAPSHOT_KEY, snapshot, {})
        serving_read_back = cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
        if not isinstance(serving_read_back, dict) or _digest(serving_read_back) != digest:
            raise CollectorStageBlocked("SERVING_SNAPSHOT_READBACK_MISMATCH", durable_accepted=True)
        _cache_set(
            cache,
            LATEST_RUNTIME_SNAPSHOT_KEY,
            snapshot,
            tag="medicalchannelai-verified-snapshot",
            ttl=SNAPSHOT_TTL_SECONDS,
        )
        read_back = cache.get(LATEST_RUNTIME_SNAPSHOT_KEY)
        if not isinstance(read_back, dict) or _digest(read_back) != digest:
            raise CollectorStageBlocked("RUNTIME_SNAPSHOT_READBACK_MISMATCH", durable_accepted=True)
    except Exception as exc:
        # Best-effort rollback prevents failed cache commits from replacing the
        # prior cache snapshot. Cache plus durable storage has no cross-store
        # transaction; a failed rollback remains visible as an operational limit.
        for key, old_value, options in (
            (PUBLISHED_RUNTIME_SNAPSHOT_KEY, old_published, {}),
            (LATEST_RUNTIME_SNAPSHOT_KEY, old_latest, {"ttl": SNAPSHOT_TTL_SECONDS, "tags": ["medicalchannelai-verified-snapshot"]}),
        ):
            try:
                _assert_cycle_owned(cache)
                if old_value is None:
                    cache.delete(key)
                else:
                    cache.set(key, old_value, options)
            except Exception:
                pass
        if isinstance(exc, CollectorError):
            exc.durable_accepted = True
            raise
        raise CollectorStageBlocked("RUNTIME_SNAPSHOT_CACHE_COMMIT_FAILED", durable_accepted=True) from exc

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


def run_stage(stage: str, *, now: datetime | None = None, cycle_id: str | None = None) -> tuple[int, dict[str, Any]]:
    token = _SCHEDULED_CYCLE.set(cycle_id)
    try:
        _assert_cycle_owned(RuntimeCache())
        return _run_stage(stage, now=now)
    finally:
        _SCHEDULED_CYCLE.reset(token)


def _run_stage(stage: str, *, now: datetime | None = None) -> tuple[int, dict[str, Any]]:
    now = now or _now_utc()
    cache = RuntimeCache()
    try:
        state, previous = _prepare_stage(cache, stage, now)
    except CollectorPrecondition as exc:
        return 409, {"action": "REJECTED", "stage": stage, "error": str(exc), "error_code": exc.code}
    except Exception as exc:
        return 503, {
            "action": "FAILED",
            "terminal": False,
            "stage": stage,
            "error_code": "COLLECTOR_STATE_READ_FAILED",
            "diagnostics": [_make_diagnostic(stage, exc, failure_stage="publish")],
        }

    if previous is not None:
        if previous.get("status") == "BLOCKED" and previous.get("terminal") is True:
            return 409, {
                "action": "BLOCKED",
                "terminal": True,
                "stage": stage,
                "local_date": state.get("local_date"),
                "completed_at": previous.get("completed_at"),
                "error_code": previous.get("error_code"),
                "diagnostics": previous.get("diagnostics") or [],
            }
        if previous.get("status") == "FAILED" and previous.get("terminal") is True:
            return 503, {
                "action": "FAILED",
                "terminal": True,
                "stage": stage,
                "local_date": state.get("local_date"),
                "completed_at": previous.get("completed_at"),
                "error_code": previous.get("error_code"),
                "diagnostics": previous.get("diagnostics") or [],
            }
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
        elif stage in REGIONAL_STAGE_MARKET_CODES or stage in REGIONAL_FALLBACK_STAGE_MARKET_CODES:
            result = _run_regional_market(cache, state, stage)
        elif stage == "publish":
            result = _run_publish(cache, state)
        else:
            raise CollectorPrecondition(f"COLLECTOR_STAGE_INVALID:{stage}")
    except Exception as exc:
        try:
            _mark_failed(cache, state, stage, exc)
        except Exception as persist_exc:
            diagnostics = _bounded_diagnostics(stage, exc)
            # State persistence failures need a stable public code; arbitrary
            # cache exception text is intentionally not surfaced.
            diagnostics.append(_make_diagnostic(stage, RuntimeError("CACHE_WRITE_FAILED"), failure_stage="publish"))
            diagnostics = diagnostics[:5]
            return 503, {
                "action": "FAILED",
                "terminal": False,
                "state_persisted": False,
                "stage": stage,
                "local_date": state.get("local_date"),
                "error_code": "COLLECTOR_FAILURE_STATE_PERSIST_FAILED",
                "durable_snapshot_accepted": bool(getattr(exc, "durable_accepted", False)),
                "durable_snapshot_as_of": getattr(exc, "durable_snapshot_as_of", None),
                "diagnostics": diagnostics,
            }
        return 503, {
            "action": "FAILED",
            "terminal": False,
            "stage": stage,
            "local_date": state.get("local_date"),
            "error_code": _safe_error_code(exc),
            "error": _safe_error_code(exc),
            "durable_snapshot_accepted": bool(getattr(exc, "durable_accepted", False)),
            "durable_snapshot_as_of": getattr(exc, "durable_snapshot_as_of", None),
            "diagnostics": _bounded_diagnostics(stage, exc),
        }

    try:
        _mark_completed(cache, state, stage, result)
    except Exception as exc:
        return 503, {
            "action": "FAILED",
            "terminal": False,
            "state_persisted": False,
            "stage": stage,
            "local_date": state.get("local_date"),
            "error_code": "COLLECTOR_COMPLETION_STATE_PERSIST_FAILED",
            "diagnostics": [_make_diagnostic(stage, exc, failure_stage="publish")],
        }
    return 200, {
        "action": "COMPLETED",
        "stage": stage,
        "local_date": state.get("local_date"),
        "result": result,
    }


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        status = int(getattr(exc, "code", 0) or 0)
        return f"HTTP_{status}" if 100 <= status <= 599 else "HTTP_ERROR"
    message = str(exc)
    match = re.match(r"^([A-Z][A-Z0-9_]{2,79})(?::|$)", message)
    if match:
        return match.group(1)
    code = str(getattr(exc, "code", "") or "")
    return code if re.fullmatch(r"[A-Z][A-Z0-9_]{2,79}", code) else "ERROR_CODE_UNAVAILABLE"


def _source_id_for_stage(stage: str) -> str:
    if stage.startswith("event"):
        return "ccgp_events"
    if stage == "ccgp":
        return "ccgp"
    if stage.startswith("regional_"):
        return "ccgp_regional"
    return stage if stage in {"tjmugh", "tjnothop", "teda", "tjfch", "publish"} else "collector"


def _diagnostic_category(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        status = int(getattr(exc, "code", 0) or 0)
        if status in {401, 403}:
            return "ACCESS_DENIED"
        return "TRANSIENT_FETCH_ERROR" if status >= 500 or status in {408, 425, 429} else "PERMANENT_HTTP_ERROR"
    if isinstance(exc, (TimeoutError, URLError)):
        return "TRANSIENT_FETCH_ERROR"
    wrapped_http = re.search(r"(?:^|_)HTTP_(\d{3})(?:$|:)", str(exc))
    if wrapped_http:
        status = int(wrapped_http.group(1))
        if status in {401, 403}:
            return "ACCESS_DENIED"
        return "TRANSIENT_FETCH_ERROR" if status >= 500 or status in {408, 425, 429} else "PERMANENT_HTTP_ERROR"
    if "parse" in type(exc).__name__.lower() or "parser" in str(exc).lower():
        return "PARSER_REJECTED"
    if "VALIDATION" in _safe_error_code(exc):
        return "EVIDENCE_VALIDATION_FAILED"
    return "UNEXPECTED_ERROR"


def _official_url(value: Any, stage: str) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    source = _source_id_for_stage(stage)
    known_urls = [TJMUGH_INDEX_URL, TJNOTHOP_INDEX_URL, TJFCH_INDEX_URL, TJFCH_TEST_INDEX_URL]
    if source == "teda":
        known_urls.append("https://www.tedahospital.com.cn/article/plist/9")
    if source in {"ccgp", "ccgp_regional"}:
        known_urls.extend(["https://search.ccgp.gov.cn/bxsearch", "https://www.ccgp.gov.cn/"])
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
            return None
        if parsed.port not in (None, 443):
            return None
        allowed_hosts = {urlsplit(item).hostname for item in known_urls if urlsplit(item).hostname}
        if parsed.hostname not in allowed_hosts:
            return None
        if parsed.query or parsed.fragment:
            return None
        return urlunsplit(("https", parsed.hostname or "", parsed.path[:240], "", ""))
    except ValueError:
        return None


def _make_diagnostic(
    stage: str,
    exc: Exception,
    *,
    market_code: str | None = None,
    failure_stage: str | None = None,
    official_url: Any = None,
) -> dict[str, Any]:
    error_code = _safe_error_code(exc)
    inferred_stage = (
        "event_search" if stage.startswith("event") else
        "publish" if stage == "publish" else
        "index_discovery" if "INDEX" in error_code or "DISCOVERY" in error_code else
        "national_fallback_discovery" if stage.endswith("_fallback") and "DISCOVERY" in error_code else
        "scoped_discovery" if stage.startswith("regional_") and "DISCOVERY" in error_code else
        "verified_detail" if stage in {"ccgp", "tjmugh", "tjnothop", "teda", "tjfch"} else
        "publish"
    )
    safe_stage = failure_stage if failure_stage in DIAGNOSTIC_STAGES else stage if stage in DIAGNOSTIC_STAGES else inferred_stage
    result: dict[str, Any] = {
        "source_id": _source_id_for_stage(stage),
        "market_code": market_code if market_code in set(REGIONAL_STAGE_MARKET_CODES.values()) else None,
        "stage": safe_stage,
        "category": _diagnostic_category(exc),
        "error_code": error_code,
        "error_type": type(exc).__name__[:60],
    }
    safe_url = _official_url(official_url or getattr(exc, "url", None), stage)
    if safe_url:
        result["official_url"] = safe_url
    return result


def _bounded_diagnostics(stage: str, exc: Exception) -> list[dict[str, Any]]:
    provided = getattr(exc, "diagnostics", None)
    if not isinstance(provided, list) or not provided:
        market_code = REGIONAL_STAGE_MARKET_CODES.get(stage) or REGIONAL_FALLBACK_STAGE_MARKET_CODES.get(stage)
        return [_make_diagnostic(stage, exc, market_code=market_code)]
    result = []
    for item in provided[:5]:
        if not isinstance(item, dict):
            continue
        nested = RuntimeError(str(item.get("message") or item.get("error") or "ERROR_CODE_UNAVAILABLE"))
        diagnostic = _make_diagnostic(
            stage, nested,
            market_code=item.get("market_code"),
            failure_stage=item.get("stage"),
            official_url=item.get("url"),
        )
        error_type = str(item.get("error") or "")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,59}", error_type):
            diagnostic["error_type"] = error_type
        if error_type == "HTTPError":
            match = re.search(r"HTTP Error (\d{3})", str(item.get("message") or ""))
            if match:
                status = int(match.group(1))
                diagnostic["error_code"] = f"HTTP_{status}"
                diagnostic["category"] = (
                    "ACCESS_DENIED" if status in {401, 403} else
                    "TRANSIENT_FETCH_ERROR" if status >= 500 or status in {408, 425, 429} else
                    "PERMANENT_HTTP_ERROR"
                )
        elif "parse" in error_type.lower():
            diagnostic["category"] = "PARSER_REJECTED"
        result.append(diagnostic)
    return result[:5] or [_make_diagnostic(stage, exc)]


def _diagnostics_from_items(stage: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []
    return _bounded_diagnostics(stage, CollectorStageBlocked("SOURCE_PARTIAL_FAILURE", diagnostics=items))


def _publish_stage_requirements(stages: dict[str, Any]) -> tuple[list[str], list[str]]:
    required = list(PUBLISH_REQUIRED_STAGES)
    for stage in REGIONAL_STAGE_MARKET_CODES:
        primary = stages.get(stage)
        result = primary.get("result") if isinstance(primary, dict) else None
        if isinstance(result, dict) and result.get("fallback_required") is True:
            required.append(f"{stage}_fallback")
    failed: list[str] = []
    incomplete: list[str] = []
    for stage in required:
        value = stages.get(stage)
        if isinstance(value, dict) and value.get("status") in {"FAILED", "BLOCKED"} and value.get("terminal") is True:
            failed.append(stage)
        elif not isinstance(value, dict) or value.get("status") != "COMPLETED":
            incomplete.append(stage)
    return failed, incomplete


def _changed_sources_from_stages(stages: dict[str, Any]) -> list[str]:
    changed: set[str] = set()
    for stage, item in stages.items():
        if not isinstance(item, dict) or item.get("status") != "COMPLETED":
            continue
        result = item.get("result")
        if not isinstance(result, dict):
            continue
        if result.get("canonical_changed") is not True:
            continue
        if stage.startswith("event"):
            changed.add("ccgp_events")
        elif stage.startswith("regional_"):
            code = REGIONAL_STAGE_MARKET_CODES.get(stage) or REGIONAL_FALLBACK_STAGE_MARKET_CODES.get(stage)
            if code:
                changed.add(f"ccgp_regional:{code.lower()}")
        elif stage in {"ccgp", "tjmugh", "tjnothop", "teda", "tjfch"}:
            changed.add(stage)
    return sorted(changed)


def _canonical_content_digest(records: list[dict[str, Any]]) -> str:
    stable = []
    for record in records:
        if not isinstance(record, dict):
            stable.append(record)
            continue
        item = dict(record)
        source = item.get("source")
        if isinstance(source, dict):
            stable_source = dict(source)
            stable_source.pop("observed_at", None)
            item["source"] = stable_source
        stable.append(item)
    return _digest(stable)
