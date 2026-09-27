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

from collector_namespace import (
    MAX_RECOVERY_CYCLES_PER_DAY,
    QUEUE_FUNCTION_MAX_DURATION_SECONDS,
    STAGE_LEASE_SECONDS,
    STATE_TTL_SECONDS,
    stage_lease_expires_at,
    stage_lease_is_live,
)

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
SNAPSHOT_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_STAGE_ATTEMPTS_PER_DAY = 2
# Cooperative wall-clock budget for source I/O inside one queue-worker
# invocation. It leaves headroom under QUEUE_FUNCTION_MAX_DURATION_SECONDS for
# cold start, canonical Runtime Cache writes and the durable publish round-trip,
# so a slow source degrades into a COMPLETED stage with deferred candidates
# instead of a platform kill that leaves a RUNNING marker behind.
STAGE_BUDGET_SECONDS = 240
# Per-request socket timeout for public procurement sources. The GitHub-runner
# sync scripts keep their longer defaults; inside a 300 s function a single
# 90 s hang is not affordable.
SOURCE_REQUEST_TIMEOUT_SECONDS = 20
# Publishing a snapshot whose opportunity pool shrank below this fraction of
# what production currently serves is blocked (a partially failed cycle must
# not replace a healthy snapshot). 0 disables the gate.
PUBLISH_MIN_POOL_RATIO_DEFAULT = 0.7
PUBLISH_BASELINE_TIMEOUT_SECONDS = 10
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
PRODUCTION_PUBLISH_HOST = "medicalchannelai.vercel.app"
DURABLE_PUBLISH_PATH = "/api/public-snapshot"
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


# ---------------------------------------------------------------------------
# Stage time budget (module level: one stage runs per worker invocation).
_stage_deadline_monotonic: float | None = None


def _begin_stage_budget(seconds: float | None = None) -> None:
    global _stage_deadline_monotonic
    budget = STAGE_BUDGET_SECONDS if seconds is None else float(seconds)
    _stage_deadline_monotonic = time.monotonic() + max(0.0, budget)


def _budget_remaining_seconds() -> float:
    if _stage_deadline_monotonic is None:
        return float("inf")
    return _stage_deadline_monotonic - time.monotonic()


def _budget_exhausted() -> bool:
    return _budget_remaining_seconds() <= 0.0


def _sleep(seconds: float) -> None:
    # Never sleep past the stage budget: politeness delays must not be what
    # pushes a stage into the platform kill.
    remaining = _budget_remaining_seconds()
    delay = min(float(seconds), max(0.0, remaining))
    if delay > 0:
        time.sleep(delay)


def _require_budget(phase: str) -> None:
    if _budget_exhausted():
        raise CollectorStageBlocked(f"COLLECTOR_STAGE_BUDGET_EXHAUSTED:{phase}")


def _publish_base_url() -> tuple[str, dict[str, str]]:
    """Return (base URL, extra headers) for the deployment that owns the durable store.

    Production always targets the production host so the snapshot lands in the
    production Postgres + Runtime Cache. Preview deployments target themselves
    (with the Vercel protection bypass header when available) so a preview
    collector can never overwrite production data by accident.
    """
    env = str(os.environ.get("VERCEL_ENV") or "").strip().lower()
    production_host = str(os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or "").strip() or PRODUCTION_PUBLISH_HOST
    if env == "production":
        return f"https://{production_host}", {}
    own_host = str(os.environ.get("VERCEL_URL") or "").strip()
    allow_production = str(os.environ.get("COLLECTOR_ALLOW_NON_PRODUCTION_PUBLISH") or "").strip() == "1"
    if own_host and not allow_production:
        headers = {}
        bypass = str(os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET") or "").strip()
        if bypass:
            headers["x-vercel-protection-bypass"] = bypass
        return f"https://{own_host}", headers
    if allow_production:
        return f"https://{production_host}", {}
    raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_TARGET_UNRESOLVED")


def _durable_publish_url() -> tuple[str, dict[str, str]]:
    base, headers = _publish_base_url()
    return f"{base}{DURABLE_PUBLISH_PATH}", headers


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


def _stage_output_keys(stage: str) -> tuple[str, ...]:
    """Canonical Runtime Cache keys a COMPLETED stage must have left behind.

    Runtime Cache is ephemeral (TTL + LRU eviction). When a key vanished after
    the stage completed, the COMPLETED marker is not trustworthy and the stage
    is re-run with a fresh attempt budget instead of failing publish with
    COLLECTOR_CANONICAL_STATE_INCOMPLETE. Stages without a canonical output of
    their own (fallbacks that may be skipped, publish) map to no keys.
    """
    if stage == "ccgp":
        return (CCGP_RECORDS_KEY, CCGP_EVENTS_KEY, CCGP_WATCH_KEY)
    if stage.startswith("event"):
        return (CCGP_EVENTS_KEY,)
    if stage == "tjmugh":
        return (TJMUGH_RECORDS_KEY,)
    if stage == "tjnothop":
        return (TJNOTHOP_RECORDS_KEY,)
    if stage == "teda":
        return (TEDA_RECORDS_KEY,)
    if stage == "tjfch":
        return (TJFCH_RECORDS_KEY,)
    if stage in REGIONAL_STAGE_MARKET_CODES:
        return (_regional_records_key(REGIONAL_STAGE_MARKET_CODES[stage]),)
    return ()


def _missing_stage_outputs(cache: RuntimeCache, stage: str) -> list[str]:
    return [key for key in _stage_output_keys(stage) if not isinstance(cache.get(key), list)]


def _compact_attempt(stage_state: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "attempt_count": int(stage_state.get("attempt_count") or 0),
        "status": stage_state.get("status"),
        "error_code": stage_state.get("error_code"),
        "started_at": stage_state.get("started_at"),
        "completed_at": stage_state.get("completed_at"),
        "reset_by": reason,
    }


def _prepare_stage(
    cache: RuntimeCache,
    stage: str,
    now: datetime,
    wall_now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Claim ``stage`` for this worker or explain why it must not run.

    ``now`` is the cycle clock (fixed per daily cycle, drives local_date and
    snapshot_as_of). ``wall_now`` is the real wall clock and is the only clock
    used for started_at / lease_expires_at, so lease arithmetic is meaningful
    even when a recovery cycle replays an older cycle_as_of.
    """
    wall_now = wall_now or _now_utc()
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
    if not isinstance(previous, dict):
        previous = None
    replay_reason: str | None = None

    if previous is not None and previous.get("status") == "COMPLETED":
        missing = _missing_stage_outputs(cache, stage)
        if not missing:
            return state, previous
        replay_reason = "COLLECTOR_STAGE_OUTPUT_MISSING:" + ",".join(
            key.removeprefix("medicalchannelai:") for key in missing
        )
    elif previous is not None and previous.get("status") == "RUNNING":
        if stage_lease_is_live(previous, now=wall_now):
            expires_at = stage_lease_expires_at(previous)
            raise CollectorPrecondition(
                f"COLLECTOR_STAGE_LEASE_HELD:{stage}:{expires_at.isoformat() if expires_at else 'unknown'}"
            )
        # The lease expired: the worker that owned it was terminated by the
        # platform (timeout/kill) before it could record an outcome.
        previous["status"] = "FAILED"
        previous["completed_at"] = wall_now.isoformat()
        previous["error_code"] = "COLLECTOR_STAGE_TIMEOUT"
        previous["error_message"] = f"COLLECTOR_STAGE_TIMEOUT:{stage}:lease_expired"
        _write_status(cache, state)

    if index > 0:
        required = STAGE_ORDER[index - 1]
        required_state = stages.get(required)
        if not isinstance(required_state, dict) or required_state.get("status") != "COMPLETED":
            raise CollectorPrecondition(f"COLLECTOR_PREVIOUS_STAGE_INCOMPLETE:{required}")

    attempts = int(previous.get("attempt_count", 0)) if previous is not None else 0
    history: list[dict[str, Any]] = []
    if previous is not None and isinstance(previous.get("previous_attempts"), list):
        history = list(previous["previous_attempts"])
    if replay_reason is not None:
        # Losing canonical output is a platform event, not a stage failure.
        history.append(_compact_attempt(previous, reason=replay_reason))
        attempts = 0
    if attempts >= MAX_STAGE_ATTEMPTS_PER_DAY:
        raise CollectorPrecondition(f"COLLECTOR_STAGE_RETRY_LIMIT:{stage}")

    stages[stage] = {
        "status": "RUNNING",
        "attempt_count": attempts + 1,
        "started_at": wall_now.isoformat(),
        "lease_expires_at": (wall_now + timedelta(seconds=STAGE_LEASE_SECONDS)).isoformat(),
        "completed_at": None,
        "error_code": None,
        "error_message": None,
        "result": None,
        "replay_reason": replay_reason,
        "previous_attempts": history[-6:],
    }
    _write_status(cache, state)
    return state, None


def _latest_stage_state_for_update(
    cache: RuntimeCache,
    state: dict[str, Any],
    stage: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    latest = load_status(cache)
    if latest.get("local_date") != state.get("local_date"):
        raise CollectorPrecondition("COLLECTOR_STATE_DATE_CHANGED_DURING_STAGE")
    latest_stages = latest.setdefault("stages", {})
    latest_stage = latest_stages.get(stage)
    original = (state.get("stages") or {}).get(stage)
    if not isinstance(latest_stage, dict):
        if not isinstance(original, dict):
            raise CollectorPrecondition(f"COLLECTOR_STAGE_STATE_MISSING:{stage}")
        latest_stage = dict(original)
        latest_stages[stage] = latest_stage
    elif (
        isinstance(original, dict)
        and original.get("started_at")
        and latest_stage.get("started_at") != original.get("started_at")
    ):
        # started_at doubles as the lease fencing token: another worker claimed
        # this stage after our lease expired, so its record must win and this
        # (stale) worker must not overwrite it.
        raise CollectorPrecondition(f"COLLECTOR_STAGE_LEASE_LOST:{stage}")
    return latest, latest_stage


def _mark_completed(cache: RuntimeCache, state: dict[str, Any], stage: str, result: dict[str, Any]) -> None:
    latest, current = _latest_stage_state_for_update(cache, state, stage)
    current["status"] = "COMPLETED"
    current["completed_at"] = _now_utc().isoformat()
    current["result"] = result
    current["error_code"] = None
    current["error_message"] = None
    _write_status(cache, latest)


def _mark_failed(cache: RuntimeCache, state: dict[str, Any], stage: str, exc: Exception) -> None:
    latest, current = _latest_stage_state_for_update(cache, state, stage)
    current["status"] = "FAILED"
    current["completed_at"] = _now_utc().isoformat()
    current["error_code"] = getattr(exc, "code", type(exc).__name__)
    current["error_message"] = str(exc)[:300]
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
        _require_budget("ccgp:discovery")
        candidates = discover_candidates(
            keyword=keyword,
            region=plan["region"],
            notice_types=plan["notice_types"],
            start_date=start_text,
            end_date=end_text,
            delay_seconds=plan["delay_seconds"],
            failures=failures,
            timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS,
        )
        for notice_type, candidate in candidates:
            detail_url = str(getattr(candidate, "detail_url", "") or "").strip()
            if not detail_url:
                continue
            discovered_by_url.setdefault(detail_url, (notice_type, candidate))
            discovered_keywords.setdefault(detail_url, set()).add(keyword)
        if keyword_index + 1 < len(plan["keywords"]):
            _sleep(plan["delay_seconds"])

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
    deferred_candidate_count = 0
    for position, (notice_type, candidate) in enumerate(selected):
        if _budget_exhausted():
            # Commit what was verified so far; the rest is picked up by the
            # next cycle instead of losing the whole stage to a platform kill.
            deferred_candidate_count = len(selected) - position
            break
        adapter = VERIFIED_NOTICE_ADAPTERS[notice_type]
        try:
            _sleep(plan["delay_seconds"])
            detail_html = fetch_ccgp_detail_html(candidate.detail_url, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
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

    if selected and deferred_candidate_count == len(selected):
        raise CollectorStageBlocked("COLLECTOR_STAGE_BUDGET_EXHAUSTED:ccgp:detail")
    allowed, reason = ccgp_publish_gate(
        discovery_success_count=discovery_success_count,
        selected_candidate_count=len(selected) - deferred_candidate_count,
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
        "deferred_candidate_count": deferred_candidate_count,
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

    deferred_project_count = 0
    for position, project_number in enumerate(projects):
        if _budget_exhausted():
            deferred_project_count = len(projects) - position
            break
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
                timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS,
            )
        )
        project_search_failures = [
            item
            for item in failures[before:]
            if item.get("stage") == "event_search" and item.get("project_number") == project_number
        ]
        if len(project_search_failures) >= 2:
            raise CollectorStageBlocked(f"EVENT_WATCH_ALL_SEARCHES_FAILED:{project_number}")

    if projects and deferred_project_count == len(projects):
        raise CollectorStageBlocked(f"COLLECTOR_STAGE_BUDGET_EXHAUSTED:{stage}:events")
    merged_events = merge_notice_events(existing_events, new_events)
    _cache_set(cache, CCGP_EVENTS_KEY, merged_events, tag="medicalchannelai-collector-events")
    return {
        "batch_index": batch_index + 1,
        "project_count": len(projects),
        "deferred_project_count": deferred_project_count,
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
        index_html = fetch_tjmugh_page(TJMUGH_INDEX_URL, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
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
    deferred_candidate_count = 0
    for position, candidate in enumerate(selected):
        if _budget_exhausted():
            deferred_candidate_count = len(selected) - position
            break
        _sleep(3.0)
        try:
            detail_html = fetch_tjmugh_page(candidate.detail_url, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
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
    if selected and deferred_candidate_count == len(selected):
        raise CollectorStageBlocked("COLLECTOR_STAGE_BUDGET_EXHAUSTED:tjmugh:detail")
    if selected and not new_records:
        raise CollectorStageBlocked("TJMUGH_ALL_SELECTED_DETAILS_FAILED_VERIFICATION")

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TJMUGH_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "deferred_candidate_count": deferred_candidate_count,
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
        index_html = fetch_tjnothop_page(TJNOTHOP_INDEX_URL, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
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
    deferred_candidate_count = 0
    for position, candidate in enumerate(selected):
        if _budget_exhausted():
            deferred_candidate_count = len(selected) - position
            break
        _sleep(3.0)
        try:
            if not candidate.published_at:
                raise ValueError("TJNOTHOP_INDEX_PUBLISHED_DATE_REQUIRED")
            detail_html = fetch_tjnothop_page(candidate.detail_url, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
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
    if selected and deferred_candidate_count == len(selected):
        raise CollectorStageBlocked("COLLECTOR_STAGE_BUDGET_EXHAUSTED:tjnothop:detail")
    if selected and not new_records:
        raise CollectorStageBlocked("TJNOTHOP_ALL_SELECTED_DETAILS_FAILED_VERIFICATION")

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TJNOTHOP_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "deferred_candidate_count": deferred_candidate_count,
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
            timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS,
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
    deferred_candidate_count = 0

    for position, candidate in enumerate(considered):
        if _budget_exhausted():
            deferred_candidate_count = len(considered) - position
            break
        _sleep(TEDA_REQUEST_DELAY_SECONDS)
        try:
            detail_html = fetch_teda_page_with_retry(
                candidate.detail_url,
                delay_seconds=TEDA_REQUEST_DELAY_SECONDS,
                timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS,
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

    if considered and deferred_candidate_count == len(considered):
        raise CollectorStageBlocked("COLLECTOR_STAGE_BUDGET_EXHAUSTED:teda:detail")
    # Match the verified GitHub refresh policy: an unsupported candidate is an
    # explicit non-fact, but any true parse/fetch failure blocks this stage. Do
    # not update TEDA canonical state when the current verification is partial.
    # (Candidates deferred by the time budget were not attempted, so they are
    # neither failures nor partial verifications; the next cycle observes them.)
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
        "deferred_candidate_count": deferred_candidate_count,
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
        index_html = fetch_tjfch_page(TJFCH_INDEX_URL, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
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
    deferred_candidate_count = 0

    for position, candidate in enumerate(selected):
        if _budget_exhausted():
            deferred_candidate_count = len(selected) - position
            break
        _sleep(TJFCH_REQUEST_DELAY_SECONDS)
        try:
            detail_html = fetch_tjfch_page(candidate.detail_url, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
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

    if selected and deferred_candidate_count == len(selected):
        raise CollectorStageBlocked("COLLECTOR_STAGE_BUDGET_EXHAUSTED:tjfch:detail")
    _require_budget("tjfch:test_index")
    try:
        early_index_html = fetch_tjfch_page(TJFCH_TEST_INDEX_URL, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
        early_discovered = parse_tjfch_test_index_html(
            early_index_html,
            max_candidates=TJFCH_TEST_MAX_CANDIDATES,
        )
    except Exception as exc:
        raise CollectorStageBlocked(f"TJFCH_TEST_INDEX_DISCOVERY_FAILED:{type(exc).__name__}") from exc

    early_new_verified_record_count = 0
    early_out_of_window_count = 0
    early_deferred_candidate_count = 0
    for position, candidate in enumerate(early_discovered):
        if _budget_exhausted():
            early_deferred_candidate_count = len(early_discovered) - position
            break
        _sleep(TJFCH_REQUEST_DELAY_SECONDS)
        try:
            detail_html = fetch_tjfch_page(candidate.detail_url, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
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
        "deferred_candidate_count": deferred_candidate_count,
        "new_verified_record_count": len(new_records) - early_new_verified_record_count,
        "early_discovered": len(early_discovered),
        "early_new_verified_record_count": early_new_verified_record_count,
        "early_out_of_window_count": early_out_of_window_count,
        "early_deferred_candidate_count": early_deferred_candidate_count,
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

    session = RegionalCcgpSearchSession(timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
    discovered_by_url: dict[str, tuple[str, object]] = {}
    failures: list[dict[str, Any]] = []
    scoped_query_success_count = 0
    scoped_region_mismatch_count = 0

    if not fallback_only:
        for keyword in plan["keywords"]:
            for notice_type in plan["notice_types"]:
                _require_budget(f"{stage}:scoped_discovery")
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
                _sleep(plan["delay_seconds"])

    fallback_query_success_count = 0
    scoped_found_candidates = bool(discovered_by_url)
    national_fallback_used = fallback_only
    if national_fallback_used:
        for keyword in plan["keywords"]:
            for notice_type in plan["notice_types"]:
                for page_index in range(1, REGIONAL_FALLBACK_MAX_PAGES + 1):
                    _require_budget(f"{stage}:national_fallback_discovery")
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
                    _sleep(plan["delay_seconds"])
                _sleep(plan["delay_seconds"])

    if not fallback_only and scoped_query_success_count <= 0:
        raise CollectorStageBlocked(f"REGIONAL_ALL_DISCOVERY_QUERIES_FAILED:{market_code}")
    if fallback_only and fallback_query_success_count <= 0:
        raise CollectorStageBlocked(f"REGIONAL_ALL_DISCOVERY_QUERIES_FAILED:{market_code}")

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
            "merged_record_count": len(existing_records),
            "failure_count": len(failures),
            "bootstrapped_records": bootstrapped,
        }

    discovered = sorted(
        discovered_by_url.values(),
        key=lambda item: regional_candidate_selection_key(item[1], existing_source_urls),
        reverse=True,
    )
    selected = discovered[: plan["max_candidates_per_market"]]
    new_records: list[dict[str, Any]] = []
    deferred_candidate_count = 0

    for position, (notice_type, candidate) in enumerate(selected):
        if _budget_exhausted():
            deferred_candidate_count = len(selected) - position
            break
        if candidate_market_code(getattr(candidate, "region", None), plan["markets"]) != market_code:
            failures.append({
                "stage": "pre_detail_market_guard",
                "market_code": market_code,
                "url": getattr(candidate, "detail_url", None),
            })
            continue
        try:
            _sleep(plan["delay_seconds"])
            html = fetch_ccgp_detail_html(candidate.detail_url, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)
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

    if selected and deferred_candidate_count == len(selected):
        raise CollectorStageBlocked(f"COLLECTOR_STAGE_BUDGET_EXHAUSTED:{stage}:detail")
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
        "fallback_required": (not fallback_only and not scoped_found_candidates),
        "national_fallback_query_success_count": fallback_query_success_count,
        "unique_candidate_count": len(discovered),
        "selected_candidate_count": len(selected),
        "deferred_candidate_count": deferred_candidate_count,
        "new_verified_record_count": len(new_records),
        "merged_record_count": len(merged),
        "failure_count": len(failures),
        "bootstrapped_records": bootstrapped,
    }


def _publish_min_pool_ratio() -> float:
    raw = str(os.environ.get("COLLECTOR_PUBLISH_MIN_POOL_RATIO") or "").strip()
    if not raw:
        return PUBLISH_MIN_POOL_RATIO_DEFAULT
    try:
        ratio = float(raw)
    except ValueError:
        return PUBLISH_MIN_POOL_RATIO_DEFAULT
    return min(1.0, max(0.0, ratio))


def _served_pool_baseline() -> tuple[int | None, str]:
    """Opportunity-pool size production currently serves, or the bundled fallback.

    Returns (count, source). ``/api/status`` is the same public contract the
    browser uses, so the gate compares against what users actually see.
    """
    try:
        base, headers = _publish_base_url()
        request = Request(
            f"{base}/api/status",
            headers={"Accept": "application/json", "User-Agent": "MedicalChannelAI-VercelCollector/0.1", **headers},
            method="GET",
        )
        with urlopen(request, timeout=PUBLISH_BASELINE_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
        snapshot = body.get("snapshot") if isinstance(body, dict) else None
        if isinstance(snapshot, dict) and snapshot.get("available") is True:
            count = snapshot.get("opportunity_pool_count")
            if isinstance(count, int) and count >= 0:
                return count, f"status:{snapshot.get('source_mode')}"
    except Exception:
        pass
    try:
        bundled = json.loads((WEB_ROOT / "public" / "data" / "today-actions.public.json").read_text(encoding="utf-8"))
        pool = bundled.get("opportunity_pool")
        if isinstance(pool, list):
            return len(pool), "bundled"
    except Exception:
        pass
    return None, "none"


def _publish_regression_gate(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Block a publish that would shrink the served opportunity pool sharply.

    A cycle in which several sources silently produced nothing must not
    replace a healthy production snapshot with a much smaller one. The gate is
    ratio-based and reports the contributing source hosts for diagnosis.
    """
    pool = snapshot.get("opportunity_pool")
    new_count = len(pool) if isinstance(pool, list) else len(snapshot.get("cards") or [])
    ratio = _publish_min_pool_ratio()
    hosts = Counter()
    for card in pool if isinstance(pool, list) else []:
        urls = card.get("evidence_source_urls") if isinstance(card, dict) else None
        first = urls[0] if isinstance(urls, list) and urls else ""
        host = str(first).split("//", 1)[-1].split("/", 1)[0] if first else "unknown"
        hosts[host] += 1
    report: dict[str, Any] = {
        "min_pool_ratio": ratio,
        "new_pool_count": new_count,
        "contributing_source_hosts": dict(hosts.most_common(12)),
    }
    if ratio <= 0:
        report.update({"baseline_pool_count": None, "baseline_source": "disabled", "decision": "BYPASSED"})
        return report
    baseline, baseline_source = _served_pool_baseline()
    report.update({"baseline_pool_count": baseline, "baseline_source": baseline_source})
    if baseline is None:
        report["decision"] = "NO_BASELINE"
        return report
    minimum = int(baseline * ratio)
    if new_count < minimum:
        report["decision"] = "BLOCKED"
        raise CollectorStageBlocked(
            f"PUBLISH_REGRESSION_POOL_SHRUNK:{new_count}<{minimum}(baseline={baseline},ratio={ratio})"
        )
    report["decision"] = "PASS"
    return report


def _persist_verified_snapshot_durably(snapshot: dict[str, Any]) -> dict[str, Any]:
    token = str(os.environ.get("VERIFIED_SNAPSHOT_PUBLISH_TOKEN") or "").strip()
    if len(token) < 24:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_TOKEN_MISSING")

    publish_url, extra_headers = _durable_publish_url()
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        publish_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "MedicalChannelAI-VercelCollector/0.1",
            **extra_headers,
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
    result["publish_url"] = publish_url
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

    # Refuse to replace a healthy served snapshot with a sharply smaller one.
    regression = _publish_regression_gate(snapshot)

    # The durable publish endpoint (Node /api/public-snapshot) is the single
    # owner of the serving state: it persists the revision to Postgres and then
    # applies the monotonic Runtime Cache publish. The collector no longer writes
    # the serving key itself, so no code path can bypass rollback protection.
    durable_result = _persist_verified_snapshot_durably(snapshot)

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
        "publish_url": durable_result.get("publish_url"),
        "regression_gate": regression,
    }


def run_stage(
    stage: str,
    *,
    now: datetime | None = None,
    wall_now: datetime | None = None,
    budget_seconds: float | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run one collector stage.

    ``now`` is the cycle clock shared by every stage of a daily cycle (it fixes
    local_date and snapshot_as_of). ``wall_now`` is the real clock used for
    leases; it defaults to the current time and should only be overridden by
    tests. ``budget_seconds`` overrides STAGE_BUDGET_SECONDS for tests.
    """
    now = now or _now_utc()
    wall_now = wall_now or _now_utc()
    cache = RuntimeCache()
    try:
        state, previous = _prepare_stage(cache, stage, now, wall_now)
    except CollectorPrecondition as exc:
        rejected: dict[str, Any] = {"action": "REJECTED", "stage": stage, "error": str(exc), "error_code": exc.code}
        message = str(exc)
        if message.startswith("COLLECTOR_STAGE_LEASE_HELD:"):
            rejected["lease_expires_at"] = message.split(":", 2)[2] if message.count(":") >= 2 else None
        return 409, rejected
    _begin_stage_budget(budget_seconds)

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
        elif stage in REGIONAL_STAGE_MARKET_CODES or stage in REGIONAL_FALLBACK_STAGE_MARKET_CODES:
            result = _run_regional_market(cache, state, stage)
        elif stage == "publish":
            result = _run_publish(cache, state)
        else:
            raise CollectorPrecondition(f"COLLECTOR_STAGE_INVALID:{stage}")
    except Exception as exc:
        try:
            _mark_failed(cache, state, stage, exc)
        except CollectorPrecondition as lost:
            return 409, {"action": "REJECTED", "stage": stage, "error": str(lost), "error_code": lost.code}
        return 503, {
            "action": "FAILED",
            "stage": stage,
            "local_date": state.get("local_date"),
            "error_code": getattr(exc, "code", type(exc).__name__),
            "error": str(exc)[:300],
        }

    try:
        _mark_completed(cache, state, stage, result)
    except CollectorPrecondition as lost:
        return 409, {"action": "REJECTED", "stage": stage, "error": str(lost), "error_code": lost.code}
    return 200, {
        "action": "COMPLETED",
        "stage": stage,
        "local_date": state.get("local_date"),
        "result": result,
    }
