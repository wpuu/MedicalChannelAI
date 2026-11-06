from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from collector_epoch import RuntimeCache
from collector_oidc import preview_oidc_token
from collector_diagnostics import failure_row, failure_summary, reported_event_failure_row

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
from medical_channel_pipeline.tjzyefy_discovery import (  # noqa: E402
    INDEX_URL as TJZYEFY_INDEX_URL,
    parse_tjzyefy_index_html,
    select_candidates_since as select_tjzyefy_candidates,
    stable_opportunity_id as tjzyefy_opportunity_id,
)
from medical_channel_pipeline.tjzyefy_market_research import TjzyefyParseError, parse_tjzyefy_market_research  # noqa: E402
from medical_channel_pipeline.tjzyefy_intent_discovery import (  # noqa: E402
    parse_tjzyefy_intent_index_html,
    select_intent_candidates_since,
    stable_intent_opportunity_id,
)
from medical_channel_pipeline.tjzyefy_procurement_intent import TjzyefyIntentParseError, parse_tjzyefy_procurement_intent  # noqa: E402
from medical_channel_pipeline.tjzxfc_discovery import (  # noqa: E402
    INDEX_URL as TJZXFC_INDEX_URL,
    parse_tjzxfc_index_html,
    select_candidates_since as select_tjzxfc_candidates,
    stable_opportunity_id as tjzxfc_opportunity_id,
)
from medical_channel_pipeline.tjzxfc_market_research import TjzxfcParseError, parse_tjzxfc_market_research  # noqa: E402
from sync_tjzyefy_market_research import (  # noqa: E402
    fetch_page_with_retry as fetch_tjzyefy_page_with_retry,
    UNSUPPORTED_DETAIL_CODES as TJZYEFY_UNSUPPORTED_DETAIL_CODES,
)
from sync_tjzyefy_procurement_intent import (  # noqa: E402
    UNSUPPORTED_DETAIL_CODES as TJZYEFY_INTENT_UNSUPPORTED_DETAIL_CODES,
)
from sync_tjzxfc_market_research import (  # noqa: E402
    fetch_page_with_retry as fetch_tjzxfc_page_with_retry,
    UNSUPPORTED_DETAIL_CODES as TJZXFC_UNSUPPORTED_DETAIL_CODES,
)
from sync_ccgp_query import VERIFIED_NOTICE_ADAPTERS, discover_candidates, scan_events, stable_id  # noqa: E402
from sync_teda_market_research import (  # noqa: E402
    UNSUPPORTED_DETAIL_CODES as TEDA_UNSUPPORTED_DETAIL_CODES,
    discover_candidates as discover_teda_candidates,
    fetch_page_with_retry as fetch_teda_page_with_retry,
)
from sync_tianjin_plan import load_plan, plan_date_window, publish_gate as ccgp_publish_gate  # noqa: E402
from sync_regional_ccgp import (  # noqa: E402
    CliBudget,
    CliBudgetExceeded,
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
EARLY_SIGNAL_LOOKBACK_DAYS = 30
EARLY_SIGNAL_MAX_CANDIDATES = 20
EARLY_SIGNAL_MAX_DETAILS = 12

META_KEY = "medicalchannelai:collector-runtime-state:v1"
CCGP_RECORDS_KEY = "medicalchannelai:collector-ccgp-records:v1"
CCGP_EVENTS_KEY = "medicalchannelai:collector-ccgp-events:v1"
CCGP_WATCH_KEY = "medicalchannelai:collector-ccgp-watch-projects:v1"
CCGP_COMMITTED_STATE_KEY = "medicalchannelai:collector-ccgp-committed:v2"
CCGP_CYCLE_STAGING_KEY = "medicalchannelai:collector-ccgp-cycle-staging:v2"
TJMUGH_RECORDS_KEY = "medicalchannelai:collector-tjmugh-records:v1"
TJNOTHOP_RECORDS_KEY = "medicalchannelai:collector-tjnothop-records:v1"
TEDA_RECORDS_KEY = "medicalchannelai:collector-teda-records:v1"
TJFCH_RECORDS_KEY = "medicalchannelai:collector-tjfch-records:v1"
TJZYEFY_RECORDS_KEY = "medicalchannelai:collector-tjzyefy-records:v2"
TJZYEFY_INTENT_RECORDS_KEY = "medicalchannelai:collector-tjzyefy-intent-records:v2"
TJZXFC_RECORDS_KEY = "medicalchannelai:collector-tjzxfc-records:v2"
SOURCE_HEALTH_KEY = "medicalchannelai:collector-source-health:v2"
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
    "tjzyefy",
    "tjzyefy_intent",
    "tjzxfc",
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

# Initial operational bounds, pending runtime SLA acceptance. Seed import never
# advances these clocks; only a complete successful official scan may do so.
SOURCE_STALE_AFTER_SECONDS = {
    "ccgp": 48 * 60 * 60,
    **{source: 24 * 60 * 60 for source in (
        "tjmugh", "tjnothop", "teda", "tjfch", "tjfch_test",
        "tjzyefy", "tjzyefy_intent", "tjzxfc",
    )},
    **{stage: 48 * 60 * 60 for stage in REGIONAL_STAGE_MARKET_CODES},
}


def record_source_scan(
    cache: RuntimeCache, source_id: str, *, successful: bool,
    attempted_at: datetime, failure_reason: str | None = None,
) -> None:
    if source_id not in SOURCE_STALE_AFTER_SECONDS:
        return
    value = cache.get(SOURCE_HEALTH_KEY)
    sources = dict(value.get("sources", {})) if isinstance(value, dict) else {}
    previous = sources.get(source_id)
    row = dict(previous) if isinstance(previous, dict) else {}
    timestamp = attempted_at.astimezone(timezone.utc).isoformat()
    row.update(last_attempt_at=timestamp, stale_after_seconds=SOURCE_STALE_AFTER_SECONDS[source_id])
    if successful:
        row["last_successful_scan_at"] = timestamp
        row["failure_reason"] = None
    else:
        row.setdefault("last_successful_scan_at", None)
        row["failure_reason"] = failure_reason or "SOURCE_SCAN_FAILED"
    sources[source_id] = row
    _cache_set(cache, SOURCE_HEALTH_KEY, {"schema_version": SCHEMA_VERSION, "sources": sources},
               tag="medicalchannelai-collector-source-health", ttl=45 * 24 * 60 * 60)


def snapshot_source_health(cache: RuntimeCache) -> dict[str, Any]:
    value = cache.get(SOURCE_HEALTH_KEY)
    known = value.get("sources", {}) if isinstance(value, dict) else {}
    sources = {}
    for source_id, stale_after in SOURCE_STALE_AFTER_SECONDS.items():
        row = known.get(source_id) if isinstance(known, dict) else None
        sources[source_id] = {
            "last_attempt_at": row.get("last_attempt_at") if isinstance(row, dict) else None,
            "last_successful_scan_at": row.get("last_successful_scan_at") if isinstance(row, dict) else None,
            "failure_reason": row.get("failure_reason") if isinstance(row, dict) else None,
            "stale_after_seconds": stale_after,
        }
    return {"schema_version": SCHEMA_VERSION, "required_source_ids": list(sources), "sources": sources}


class CollectorError(RuntimeError):
    code = "COLLECTOR_ERROR"


class CollectorPrecondition(CollectorError):
    code = "COLLECTOR_PRECONDITION_FAILED"


class CollectorStageBlocked(CollectorError):
    code = "COLLECTOR_STAGE_BLOCKED"

    def __init__(self, message: str, *, diagnostics=None, retryable: bool = True):
        super().__init__(message)
        self.diagnostics = diagnostics
        self.retryable = retryable


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cache_set(cache: RuntimeCache, key: str, value: Any, *, tag: str, ttl: int = STATE_TTL_SECONDS,
               verified_nonfact_urls: set[str] | None = None, canonical_source_id: str | None = None) -> None:
    reconciled = {}
    if tag == "medicalchannelai-collector-canonical" or tag.startswith("medicalchannelai-collector-regional-"):
        reconciled = _assert_pending_canonical_commit(cache, key, value, verified_nonfact_urls=verified_nonfact_urls,
                                                      canonical_source_id=canonical_source_id)
    cache.set(key, value, {"ttl": ttl, "tags": [tag]})
    # Commit precedes cleanup. Only URLs proven by this source transaction may
    # release their barrier; a validated unsupported detail is also such proof.
    for source_id, verified_urls in reconciled.items():
        cache.delete(f"medicalchannelai:collector-incremental-pending-barrier:{source_id}:v2")
        pending_key = f"medicalchannelai:collector-incremental-pending:{source_id}:v2"
        staged = cache.get(pending_key)
        if isinstance(staged, list):
            remaining = [row for row in staged if str((row.get("source") or {}).get("url") or "") not in verified_urls]
            if remaining:
                cache.set(pending_key, remaining, {"ttl": 3 * 24 * 60 * 60,
                          "tags": ["medicalchannelai-collector-incremental-pending"]})
            else:
                cache.delete(pending_key)


def _assert_pending_canonical_commit(cache: RuntimeCache, key: str, records: Any, *,
                                     verified_nonfact_urls: set[str] | None = None,
                                     canonical_source_id: str | None = None) -> dict[str, set[str]]:
    # Initial seed imports restore an old known canonical version only. Every
    # subsequent source commit must prove it supersedes its unresolved URLs.
    if cache.get(key) is None:
        return {}
    keys = {
        CCGP_RECORDS_KEY: ("ccgp",), TJMUGH_RECORDS_KEY: ("tjmugh",),
        TJNOTHOP_RECORDS_KEY: ("tjnothop",), TEDA_RECORDS_KEY: ("teda",),
        TJFCH_RECORDS_KEY: ("tjfch", "tjfch_test"),
        TJZYEFY_RECORDS_KEY: ("tjzyefy",), TJZYEFY_INTENT_RECORDS_KEY: ("tjzyefy_intent",),
        TJZXFC_RECORDS_KEY: ("tjzxfc",),
    }
    sources = keys.get(key, ())
    if canonical_source_id is not None:
        if canonical_source_id not in sources:
            raise CollectorStageBlocked("SOURCE_CANONICAL_PARTITION_MISMATCH")
        # Incremental updates preserve a shared-cache sibling's old records.
        # Only a combined deep scan must reconcile both feeds' pending URLs.
        sources = (canonical_source_id,)
    reconciled = {}
    for source_id in sources:
        pending = cache.get(f"medicalchannelai:collector-incremental-pending-barrier:{source_id}:v2")
        if pending is None:
            continue
        if not isinstance(pending, list) or not all(isinstance(url, str) for url in pending):
            raise CollectorStageBlocked("SOURCE_PENDING_BARRIER_CORRUPT")
        ledger = cache.get(f"medicalchannelai:collector-incremental-ledger:{source_id}:v2")
        threshold_raw = ledger.get("updated_at") if isinstance(ledger, dict) else None
        try:
            threshold = datetime.fromisoformat(str(threshold_raw or "").replace("Z", "+00:00"))
        except ValueError:
            threshold = None
        # Explicit unsupported outcomes are successful verifications too. They
        # never manufacture canonical facts, and may discharge only their URL.
        verified = set(verified_nonfact_urls or ())
        for record in records if isinstance(records, list) else []:
            source = record.get("source") or {}
            try:
                observed = datetime.fromisoformat(str(source.get("observed_at") or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if (threshold is not None and threshold.tzinfo is not None and observed.tzinfo is not None
                    and observed >= threshold):
                verified.add(source.get("url"))
        if set(pending) - verified:
            raise CollectorStageBlocked("SOURCE_PENDING_VERIFICATION_BARRIER")
        reconciled[source_id] = verified
    return reconciled


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


def _bootstrap_tjzyefy_records() -> list[dict[str, Any]]:
    return merge_canonical_records([], _load_array(DATA_ROOT / "tianjin_live_tjzyefy_records.json"))


def _bootstrap_tjzyefy_intent_records() -> list[dict[str, Any]]:
    return merge_canonical_records([], _load_array(DATA_ROOT / "tianjin_live_tjzyefy_intent_records.json"))


def _bootstrap_tjzxfc_records() -> list[dict[str, Any]]:
    return merge_canonical_records([], _load_array(DATA_ROOT / "tianjin_live_tjzxfc_records.json"))


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


def _stage_retry_limit_reached(stage: str, previous: dict[str, Any] | None,
                             stages: dict[str, Any], *, canonical_replay: bool = False) -> bool:
    """One budget decision for admission and immediate failure finalization."""
    previous = previous if isinstance(previous, dict) else {}
    attempts = int(previous.get("attempt_count", 0))
    error = str(previous.get("error_message") or "")
    policy_recovery = (
        stage == "tjfch" and attempts == MAX_STAGE_ATTEMPTS_PER_DAY
        and previous.get("status") == "FAILED" and "TJFCH_NOTICE_TYPE_UNSUPPORTED" in error
    )
    publish_migration = (
        stage == "publish" and attempts == MAX_STAGE_ATTEMPTS_PER_DAY
        and previous.get("status") == "FAILED" and error.startswith("COLLECTOR_CANONICAL_STATE_INCOMPLETE")
    )
    regional_timeout_replay = (
        stage in REGIONAL_STAGE_MARKET_CODES and previous.get("status") == "RUNNING"
        and attempts in {MAX_STAGE_ATTEMPTS_PER_DAY, MAX_STAGE_ATTEMPTS_PER_DAY + 1}
        and isinstance(stages.get("publish"), dict)
        and str(stages["publish"].get("error_message") or "").startswith("COLLECTOR_CANONICAL_STATE_INCOMPLETE")
        and f"{stage}_fallback" not in stages
    )
    return attempts >= MAX_STAGE_ATTEMPTS_PER_DAY and not (
        canonical_replay or policy_recovery or publish_migration or regional_timeout_replay
    )


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
    if stage != "publish" and isinstance(previous, dict) and previous.get("status") == "DEGRADED":
        return state, previous  # Re-delivery may retry enqueue, never the terminal source.
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
        started_raw = str(previous.get("wall_started_at") or state.get("updated_at") or "")
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
            and _now_utc() - started.astimezone(timezone.utc) >= timedelta(minutes=15)
        )

    if index > 0:
        required = STAGE_ORDER[index - 1]
        required_state = stages.get(required)
        if not isinstance(required_state, dict) or required_state.get("status") not in {"COMPLETED", "DEGRADED"}:
            raise CollectorPrecondition(f"COLLECTOR_PREVIOUS_STAGE_INCOMPLETE:{required}")

    attempts = int(previous.get("attempt_count", 0)) if isinstance(previous, dict) else 0
    if _stage_retry_limit_reached(stage, previous, stages,
                                 canonical_replay=regional_cache_replay or regional_stale_migration_replay):
        raise CollectorPrecondition(f"COLLECTOR_STAGE_RETRY_LIMIT:{stage}")

    stages[stage] = {
        "status": "RUNNING",
        "attempt_count": attempts + 1,
        "started_at": now.isoformat(),
        "wall_started_at": _now_utc().isoformat(),
        "completed_at": None,
        "error_code": None,
        "error_message": None,
        "result": None,
    }
    _write_status(cache, state)
    return state, None


def mark_stage_degraded(
    stage: str, *, now: datetime, error: str, cache: RuntimeCache | None = None,
) -> None:
    """Finish an exhausted source without pretending its scan or publish succeeded."""
    if stage == "publish":
        raise CollectorPrecondition("COLLECTOR_PUBLISH_CANNOT_DEGRADE")
    _stage_index(stage)
    cache = cache or RuntimeCache()
    state = load_status(cache)
    row = (state.get("stages") or {}).get(stage)
    if not isinstance(row, dict):
        raise CollectorPrecondition("COLLECTOR_DEGRADED_STAGE_MISSING")
    row.update(status="DEGRADED", completed_at=now.isoformat(), degraded_reason=str(error)[:300])
    row["error_code"] = row.get("error_code") or "SOURCE_SCAN_FAILED"
    row["error_message"] = row.get("error_message") or str(error)[:300]
    _write_status(cache, state)
    source = "ccgp" if stage.startswith("event") else stage.removesuffix("_fallback")
    health = snapshot_source_health(cache)["sources"].get(source, {})
    record_source_scan(cache, source, successful=False, attempted_at=now,
                       failure_reason=health.get("failure_reason") or "SOURCE_SCAN_FAILED")
    if stage == "tjfch":
        record_source_scan(cache, "tjfch_test", successful=False, attempted_at=now,
                           failure_reason="SOURCE_SCAN_FAILED")


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
    current["completed_at"] = _now_utc().isoformat()
    current["result"] = result
    current["error_code"] = None
    current["error_message"] = None
    _write_status(cache, latest)


def _mark_failed(cache: RuntimeCache, state: dict[str, Any], stage: str, exc: Exception) -> None:
    latest, current = _latest_stage_state_for_update(cache, state, stage)
    current["status"] = "FAILED"
    current["completed_at"] = _now_utc().isoformat()
    current["failed_at"] = current["completed_at"]
    current["error_code"] = getattr(exc, "code", type(exc).__name__)
    current["error_message"] = str(exc)[:300]
    if isinstance(exc, CollectorStageBlocked):
        current["diagnostics"] = exc.diagnostics
        current["retryable"] = exc.retryable
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
    committed = cache.get(CCGP_COMMITTED_STATE_KEY)
    if committed is not None:
        if not isinstance(committed, dict) or not isinstance(committed.get("records"), list) or not isinstance(committed.get("events"), list):
            raise CollectorPrecondition("COLLECTOR_CCGP_COMMITTED_STATE_CORRUPT")
        existing_records, existing_events = committed["records"], committed["events"]

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

    if failures:
        raise CollectorStageBlocked("CCGP_CANDIDATE_VERIFICATION_INCOMPLETE")
    merged_records = merge_canonical_records(existing_records, new_records)
    watch_projects = active_ccgp_project_numbers(merged_records, as_of)
    if len(watch_projects) > plan["max_event_watch_projects"]:
        raise CollectorStageBlocked(
            f"ACTIVE_EVENT_WATCH_CAP_EXCEEDED:{len(watch_projects)}>{plan['max_event_watch_projects']}"
        )

    # Notices and all event-watch batches form one source transaction. No
    # current-cycle fact becomes canonical until every batch has passed.
    _cache_set(cache, CCGP_CYCLE_STAGING_KEY, {
        "cycle_as_of": state["cycle_as_of"], "records": merged_records, "events": existing_events,
    }, tag="medicalchannelai-collector-ccgp-staging")
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
    staged = cache.get(CCGP_CYCLE_STAGING_KEY)
    if (not isinstance(staged, dict) or staged.get("cycle_as_of") != state.get("cycle_as_of")
            or not isinstance(staged.get("records"), list) or not isinstance(staged.get("events"), list)):
        raise CollectorPrecondition("COLLECTOR_CCGP_CYCLE_STAGING_MISSING")
    existing_events = staged["events"]
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
        try:
            new_events.extend(scan_events(
                project_number,
                region=plan["region"],
                start_date=start_text,
                end_date=end_text,
                delay_seconds=plan["delay_seconds"],
                observed_at=observed_at,
                failures=failures,
            ))
        except Exception as exc:
            diagnostics = [reported_event_failure_row(row) for row in failures]
            diagnostics.append(failure_row("event_scan", exc, project_number))
            raise CollectorStageBlocked("EVENT_WATCH_SCAN_FAILED", diagnostics=failure_summary(diagnostics)) from exc
        project_search_failures = [
            item
            for item in failures[before:]
            if item.get("stage") == "event_search" and item.get("project_number") == project_number
        ]
        if len(project_search_failures) >= 2:
            raise CollectorStageBlocked("EVENT_WATCH_ALL_SEARCHES_FAILED",
                diagnostics=failure_summary([reported_event_failure_row(row) for row in failures]))

    if failures:
        raise CollectorStageBlocked("EVENT_WATCH_VERIFICATION_INCOMPLETE",
            diagnostics=failure_summary([reported_event_failure_row(row) for row in failures]))
    merged_events = merge_notice_events(existing_events, new_events)
    staged["events"] = merged_events
    if stage == "event6":
        if not all(((state.get("stages") or {}).get(required) or {}).get("status") == "COMPLETED"
                   for required in ("ccgp", "event1", "event2", "event3", "event4", "event5")):
            raise CollectorStageBlocked("CCGP_SOURCE_TRANSACTION_INCOMPLETE")
        _assert_pending_canonical_commit(cache, CCGP_RECORDS_KEY, staged["records"])
        _cache_set(cache, CCGP_COMMITTED_STATE_KEY, staged, tag="medicalchannelai-collector-ccgp-committed")
    else:
        _cache_set(cache, CCGP_CYCLE_STAGING_KEY, staged, tag="medicalchannelai-collector-ccgp-staging")
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
    if failures:
        raise CollectorStageBlocked("TJMUGH_CANDIDATE_VERIFICATION_INCOMPLETE")

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


def _run_early_signal_source(cache: RuntimeCache, state: dict[str, Any], source_id: str) -> dict[str, Any]:
    # Local import reuses the exact incremental adapters without introducing an
    # import-time cycle. Deep and intraday runs share parser/identity contracts.
    import collector_incremental_runtime as incremental

    existing, cache_key = incremental._existing_records(cache, source_id)
    as_of = _cycle_as_of(state)
    discovered = incremental._DISCOVERY[source_id](as_of)
    if len(discovered) > EARLY_SIGNAL_MAX_DETAILS:
        # Deep scans cannot declare this source complete after verifying only a
        # prefix. Intraday's ledger/staging drains that backlog in bounded scans.
        plan = incremental.plan_detail_verification(
            source_id, discovered, incremental._load_ledger(cache, source_id),
            now=as_of, max_details=EARLY_SIGNAL_MAX_DETAILS,
        )
        unresolved = (*plan.selected, *plan.deferred)
        incremental._mark_budget_deferred(plan.next_ledger, unresolved)
        incremental._save_ledger(cache, source_id, plan.next_ledger)
        barrier = incremental._load_pending_barrier(cache, source_id)
        barrier.update(item.candidate.detail_url for item in unresolved)
        incremental._save_pending_barrier(cache, source_id, barrier)
        raise CollectorStageBlocked("EARLY_SIGNAL_DETAIL_BUDGET_DEFERRED")
    selected = discovered[:EARLY_SIGNAL_MAX_DETAILS]
    verified: list[dict[str, Any]] = []
    unsupported = 0
    verified_nonfact_urls: set[str] = set()
    failures = 0
    for candidate in selected:
        time.sleep(3.0)
        try:
            record = incremental._VERIFICATION[source_id](candidate, as_of.isoformat(), as_of)
            if record is None:
                unsupported += 1
                verified_nonfact_urls.add(str(candidate.detail_url))
            else:
                verified.append(record)
        except Exception:
            failures += 1
    if failures:
        # A failed sibling must not permit a partly reconciled source commit.
        raise CollectorStageBlocked("EARLY_SIGNAL_DETAIL_VERIFICATION_PENDING")
    merged = merge_canonical_records(existing, verified)
    _cache_set(cache, cache_key, merged, tag="medicalchannelai-collector-canonical",
               verified_nonfact_urls=verified_nonfact_urls)
    return {
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "deferred_detail_count": max(0, len(discovered) - len(selected)),
        "new_verified_record_count": len(verified),
        "unsupported_count": unsupported,
        "failure_count": 0,
        "merged_record_count": len(merged),
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
    if failures:
        raise CollectorStageBlocked("TJNOTHOP_CANDIDATE_VERIFICATION_INCOMPLETE")

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
        cause = exc
        status = None
        for _ in range(6):
            if isinstance(cause, HTTPError):
                status = cause.code
                break
            if cause.__cause__ is None:
                break
            cause = cause.__cause__
        reason = f"TEDA_HTTP_{status}" if status in {401, 403, 404, 429, 500, 502, 503, 504} else "TEDA_INDEX_FETCH_FAILED"
        raise CollectorStageBlocked(
            f"TEDA_INDEX_DISCOVERY_FAILED:{reason}",
            diagnostics={"failure_count": 1, "reason_counts": {reason: 1},
                         "phase_counts": {"index_discovery": 1}, "samples": []},
            retryable=status not in {401, 403, 404},
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
    _cache_set(cache, TJFCH_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical",
               verified_nonfact_urls={str(row["url"]) for row in unsupported})
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
    *, budget: CliBudget | None = None,
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

    if budget:
        budget.check("REGIONAL_PREPARE")
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

    if budget:
        budget.request_timeout(90, "REGIONAL_PREPARE")
    session = RegionalCcgpSearchSession(budget=budget) if budget else RegionalCcgpSearchSession()

    def pause(delay: float, phase: str) -> None:
        if budget:
            budget.sleep_checked(delay, phase)
        else:
            time.sleep(delay)

    def check(phase: str) -> None:
        if budget:
            budget.check(phase)

    def commit(records: list[dict[str, Any]], tag: str) -> dict[str, Any]:
        check("REGIONAL_WORK_COMPLETE")
        if budget:
            budget.work_complete = True
            budget.check("REGIONAL_PRE_COMMIT", finalize=True)
        try:
            _cache_set(cache, regional_records_key, records, tag=tag)
        except Exception as exc:
            if budget:
                raise CollectorStageBlocked("REGIONAL_CANONICAL_WRITE_RESULT_UNKNOWN", diagnostics={
                    "budget": budget.snapshot(), "canonical_mutation_possible": True,
                    "canonical_write_completed": None,
                }) from exc
            raise
        if budget:
            return {"budget": budget.snapshot(), "budget_observation_phase": "CANONICAL_RETURN",
                    "canonical_write_completed": True,
                    "budget_finalization_overrun": budget.clock() >= budget.started + budget.total_seconds}
        return {}
    discovered_by_url: dict[str, tuple[str, object]] = {}
    failures: list[dict[str, Any]] = []
    scoped_query_success_count = 0
    scoped_region_mismatch_count = 0

    if not fallback_only:
        for keyword in plan["keywords"]:
            for notice_type in plan["notice_types"]:
                try:
                    if budget:
                        budget.request_timeout(90, "REGIONAL_SCOPED")
                    items = fetch_regional_candidates_page(
                        session,
                        keyword=keyword,
                        notice_type=notice_type,
                        start_date=start_date,
                        end_date=end_date,
                        region=str(market["name"]),
                        page_index=1,
                    )
                    check("REGIONAL_SCOPED_PARSE")
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
                    check("REGIONAL_SCOPED_PARSE")
                except CliBudgetExceeded:
                    raise
                except Exception as exc:
                    failures.append(failure_row("scoped_discovery", exc, f"{market_code}:{keyword}:{notice_type}:1"))
                    if failures[-1]["reason"] in {"RATE_LIMITED", "HTTP_401", "HTTP_403", "HTTP_429"}:
                        raise CollectorStageBlocked(f"REGIONAL_DISCOVERY_ACCESS_BLOCKED:{market_code}", diagnostics=failure_summary(failures)) from exc
                pause(plan["delay_seconds"], "REGIONAL_SCOPED_SLEEP")

    fallback_query_success_count = 0
    scoped_found_candidates = bool(discovered_by_url)
    national_fallback_used = fallback_only
    if national_fallback_used:
        for keyword in plan["keywords"]:
            for notice_type in plan["notice_types"]:
                for page_index in range(1, REGIONAL_FALLBACK_MAX_PAGES + 1):
                    try:
                        if budget:
                            budget.request_timeout(90, "REGIONAL_FALLBACK")
                        items = fetch_regional_candidates_page(
                            session,
                            keyword=keyword,
                            notice_type=notice_type,
                            start_date=start_date,
                            end_date=end_date,
                            region=None,
                            page_index=page_index,
                        )
                        check("REGIONAL_FALLBACK_PARSE")
                        fallback_query_success_count += 1
                    except CliBudgetExceeded:
                        raise
                    except Exception as exc:
                        failures.append(failure_row("national_fallback_discovery", exc, f"{market_code}:{keyword}:{notice_type}:{page_index}"))
                        if failures[-1]["reason"] in {"RATE_LIMITED", "HTTP_401", "HTTP_403", "HTTP_429"}:
                            raise CollectorStageBlocked(f"REGIONAL_DISCOVERY_ACCESS_BLOCKED:{market_code}", diagnostics=failure_summary(failures)) from exc
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
                    pause(plan["delay_seconds"], "REGIONAL_FALLBACK_SLEEP")
                pause(plan["delay_seconds"], "REGIONAL_FALLBACK_SLEEP")

    if not fallback_only and scoped_query_success_count <= 0:
        raise CollectorStageBlocked(f"REGIONAL_ALL_DISCOVERY_QUERIES_FAILED:{market_code}", diagnostics=failure_summary(failures))
    if fallback_only and fallback_query_success_count <= 0:
        raise CollectorStageBlocked(f"REGIONAL_ALL_DISCOVERY_QUERIES_FAILED:{market_code}", diagnostics=failure_summary(failures))

    if stage == "regional_bj" and not scoped_found_candidates:
        if failures:
            raise CollectorStageBlocked(f"REGIONAL_CANDIDATE_VERIFICATION_INCOMPLETE:{market_code}", diagnostics=failure_summary(failures))
        budget_result = commit(existing_records, "medicalchannelai-collector-regional-bj")
        return {
            **budget_result,
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

    for notice_type, candidate in selected:
        if candidate_market_code(getattr(candidate, "region", None), plan["markets"]) != market_code:
            failures.append(failure_row("pre_detail_market_guard", None, str(candidate.detail_url)))
            continue
        try:
            pause(plan["delay_seconds"], "REGIONAL_DETAIL_SLEEP")
            html = (fetch_ccgp_detail_html(candidate.detail_url, timeout_seconds=budget.request_timeout(30, "REGIONAL_DETAIL"))
                    if budget else fetch_ccgp_detail_html(candidate.detail_url))
            check("REGIONAL_DETAIL")
            record = VERIFIED_NOTICE_ADAPTERS[notice_type](
                html,
                source_url=candidate.detail_url,
                observed_at=observed_at,
                opportunity_id=stable_id(
                    f"ccgp_{market_code.lower()}",
                    candidate.detail_url,
                ),
            )
            check("REGIONAL_DETAIL_PARSE")
            new_records.append(annotate_regional_market(record, market))
        except CliBudgetExceeded:
            raise
        except Exception as exc:
            failures.append(failure_row("verified_detail", exc, str(candidate.detail_url)))

    if selected and not new_records:
        raise CollectorStageBlocked(
            f"REGIONAL_ALL_SELECTED_DETAILS_FAILED_VERIFICATION:{market_code}", diagnostics=failure_summary(failures)
        )
    if failures:
        raise CollectorStageBlocked(f"REGIONAL_CANDIDATE_VERIFICATION_INCOMPLETE:{market_code}", diagnostics=failure_summary(failures))

    merged = merge_canonical_records(existing_records, new_records)
    budget_result = commit(merged, f"medicalchannelai-collector-regional-{market_code.lower()}")
    return {
        **budget_result,
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
        "merged_record_count": len(merged),
        "failure_count": len(failures),
        "bootstrapped_records": bootstrapped,
    }


def _durable_publish_url() -> str:
    if str(os.environ.get("VERCEL_ENV") or "").strip().lower() != "preview":
        return DURABLE_PUBLISH_URL
    host = str(os.environ.get("VERCEL_URL") or "").strip()
    if not host:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PREVIEW_HOST_MISSING")
    # VERCEL_URL is a deployment hostname, not a configurable upstream URL.
    # Accept only one DNS label beneath vercel.app; reject ports, userinfo,
    # schemes and paths before attaching the publisher credential.
    suffix = ".vercel.app"
    label = host[:-len(suffix)] if host.endswith(suffix) else ""
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label):
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PREVIEW_HOST_INVALID")
    if host == "medicalchannelai.vercel.app":
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PREVIEW_PRODUCTION_HOST_REJECTED")
    return f"https://{host}/api/public-snapshot"


def _persist_verified_snapshot_durably(snapshot: dict[str, Any]) -> dict[str, Any]:
    publish_url = _durable_publish_url()
    token = str(os.environ.get("VERIFIED_SNAPSHOT_PUBLISH_TOKEN") or "").strip()
    if len(token) < 24:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_TOKEN_MISSING")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": "MedicalChannelAI-VercelCollector/0.1",
    }
    if str(os.environ.get("VERCEL_ENV") or "").strip().lower() == "preview":
        # URL validation above pins this credential to the exact deployment.
        oidc_token = preview_oidc_token()
        if oidc_token:
            headers["x-vercel-trusted-oidc-idp-token"] = oidc_token
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        publish_url,
        data=payload,
        headers=headers,
        method="PUT",
    )
    try:
        with urlopen(request, timeout=DURABLE_PUBLISH_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 0) or 0)
            body = response.read()
    except HTTPError as exc:
        detail = ""
        if str(os.environ.get("VERCEL_ENV") or "").strip().lower() != "preview":
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:180]
            except Exception:
                pass
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
    acknowledged_count = result.get("opportunity_pool_count")
    if type(acknowledged_count) is not int or acknowledged_count != expected_count:
        raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_POOL_MISMATCH")
    return result


def _run_publish(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    ccgp_records = cache.get(CCGP_RECORDS_KEY)
    events = cache.get(CCGP_EVENTS_KEY)
    committed = cache.get(CCGP_COMMITTED_STATE_KEY)
    if committed is not None:
        if not isinstance(committed, dict) or not isinstance(committed.get("records"), list) or not isinstance(committed.get("events"), list):
            raise CollectorPrecondition("COLLECTOR_CCGP_COMMITTED_STATE_CORRUPT")
        ccgp_records, events = committed["records"], committed["events"]
    tjmugh_records = cache.get(TJMUGH_RECORDS_KEY)
    tjnothop_records = cache.get(TJNOTHOP_RECORDS_KEY)
    teda_records = cache.get(TEDA_RECORDS_KEY)
    tjfch_records = cache.get(TJFCH_RECORDS_KEY)
    tjzyefy_records = cache.get(TJZYEFY_RECORDS_KEY)
    tjzyefy_intent_records = cache.get(TJZYEFY_INTENT_RECORDS_KEY)
    tjzxfc_records = cache.get(TJZXFC_RECORDS_KEY)
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
        "tjzyefy": tjzyefy_records,
        "tjzyefy_intent": tjzyefy_intent_records,
        "tjzxfc": tjzxfc_records,
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
        + list(tjzyefy_records)
        + list(tjzyefy_intent_records)
        + list(tjzxfc_records)
        + regional_records
    )
    as_of = _cycle_as_of(state)
    # Canonical identity conflicts still use the same deterministic reconciler.
    records = merge_canonical_records([], records)
    snapshot = build_public_snapshot(records, as_of, list(events))
    snapshot["source_health"] = snapshot_source_health(cache)
    source_by_opportunity = {
        str(record.get("opportunity_id")): (
            "tjfch_test" if source_id == "tjfch" and
            str((record.get("source") or {}).get("source_id") or "").startswith("tjfch-test:")
            else source_id
        )
        for source_id, rows in canonical_by_name.items()
        if source_id != "events"
        for record in rows
    }
    for card in [*(snapshot.get("cards") or []), *(snapshot.get("opportunity_pool") or [])]:
        card["source_id"] = source_by_opportunity.get(str(card.get("opportunity_id")))
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

    cache_status = "READY"
    try:
        cache.set(PUBLISHED_RUNTIME_SNAPSHOT_KEY, snapshot, {})
        serving_read_back = cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
        if not isinstance(serving_read_back, dict) or _digest(serving_read_back) != digest:
            cache_status = "RETRY_REQUIRED"
    except Exception:
        # The durable endpoint has already committed and read back this version.
        # A fallback-copy failure cannot turn that committed publish into FAILED.
        cache_status = "RETRY_REQUIRED"

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
        "cache_status": cache_status,
    }


def run_stage(stage: str, *, now: datetime | None = None, budget: CliBudget | None = None) -> tuple[int, dict[str, Any]]:
    if stage not in REGIONAL_STAGE_MARKET_CODES and stage not in REGIONAL_FALLBACK_STAGE_MARKET_CODES:
        budget = None
    now = now or _now_utc()
    cache = RuntimeCache()
    try:
        state, previous = _prepare_stage(cache, stage, now)
    except CollectorPrecondition as exc:
        return 409, {"action": "REJECTED", "stage": stage, "error": str(exc), "error_code": exc.code}

    if previous is not None:
        return 200, {
            "action": "ALREADY_DEGRADED_TODAY" if previous.get("status") == "DEGRADED" else "ALREADY_COMPLETED_TODAY",
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
        elif stage in {"tjzyefy", "tjzyefy_intent", "tjzxfc"}:
            result = _run_early_signal_source(cache, state, stage)
        elif stage == "teda":
            result = _run_teda(cache, state)
        elif stage == "tjfch":
            result = _run_tjfch(cache, state)
        elif stage in REGIONAL_STAGE_MARKET_CODES or stage in REGIONAL_FALLBACK_STAGE_MARKET_CODES:
            result = _run_regional_market(cache, state, stage, budget=budget) if budget else _run_regional_market(cache, state, stage)
        elif stage == "publish":
            result = _run_publish(cache, state)
        else:
            raise CollectorPrecondition(f"COLLECTOR_STAGE_INVALID:{stage}")
    except Exception as exc:
        if budget and isinstance(exc, CliBudgetExceeded):
            exc = CollectorStageBlocked("REGIONAL_WORK_BUDGET_EXCEEDED", diagnostics={
                "budget": budget.snapshot(), "canonical_mutation_possible": False,
                "new_canonical_write_attempted": False,
            })
        try:
            _mark_failed(cache, state, stage, exc)
            source = "ccgp" if stage.startswith("event") else stage.removesuffix("_fallback")
            record_source_scan(cache, source, successful=False,
                               attempted_at=_now_utc(), failure_reason="SOURCE_SCAN_FAILED")
            if stage == "tjfch":
                record_source_scan(cache, "tjfch_test", successful=False,
                                   attempted_at=_now_utc(), failure_reason="SOURCE_SCAN_FAILED")
            failed_stages = load_status(cache).get("stages") or {}
            failed = failed_stages.get(stage) or {}
        except Exception as persistence_error:
            if budget:
                raise CollectorStageBlocked("REGIONAL_FAILURE_STATE_RESULT_UNKNOWN", diagnostics={
                    "budget": budget.snapshot(),
                    "canonical_mutation_possible": bool(getattr(exc, "diagnostics", {}).get("canonical_mutation_possible")),
                    "stage_or_health_mutation_possible": True,
                }) from persistence_error
            raise
        return 503, {
            "action": "FAILED",
            "stage": stage,
            "local_date": state.get("local_date"),
            "error_code": getattr(exc, "code", type(exc).__name__),
            "error": str(exc)[:300],
            "retryable": getattr(exc, "retryable", True),
            "attempt_count": failed.get("attempt_count"),
            "retry_exhausted": _stage_retry_limit_reached(stage, failed, failed_stages),
            **({"budget": budget.snapshot(),
                "canonical_mutation_possible": bool(getattr(exc, "diagnostics", {}).get("canonical_mutation_possible")),
                "diagnostics": getattr(exc, "diagnostics", {})} if budget else {}),
        }

    try:
        _mark_completed(cache, state, stage, result)
        complete_scan = int(result.get("failure_count", 0)) == 0 and not result.get("fallback_required")
        source = "ccgp" if stage.startswith("event") else stage.removesuffix("_fallback")
        if stage == "ccgp":
            record_source_scan(cache, source, successful=False, attempted_at=_now_utc(),
                               failure_reason="EVENT_VERIFICATION_PENDING")
        elif stage.startswith("event"):
            latest_stages = load_status(cache).get("stages") or {}
            if all((latest_stages.get(required) or {}).get("status") == "COMPLETED"
                   for required in ("ccgp", "event1", "event2", "event3", "event4", "event5", "event6")):
                record_source_scan(cache, source, successful=True, attempted_at=_now_utc())
        elif not result.get("fallback_skipped"):
            record_source_scan(cache, source, successful=complete_scan,
                               attempted_at=_now_utc(),
                               failure_reason=None if complete_scan else "DETAIL_VERIFICATION_PENDING")
        if stage == "tjfch":
            record_source_scan(cache, "tjfch_test", successful=complete_scan,
                               attempted_at=_now_utc(),
                               failure_reason=None if complete_scan else "DETAIL_VERIFICATION_PENDING")
    except Exception as exc:
        if budget:
            raise CollectorStageBlocked("REGIONAL_FINALIZATION_RESULT_UNKNOWN", diagnostics={
                "budget": budget.snapshot(), "canonical_mutation_possible": bool(result.get("canonical_write_completed")),
                "stage_or_health_mutation_possible": True,
            }) from exc
        raise
    final_budget = ({"budget": budget.snapshot(), "budget_observation_phase": "STAGE_RETURN",
                     "budget_finalization_overrun": budget.clock() >= budget.started + budget.total_seconds}
                    if budget else {})
    return 200, {
        **final_budget,
        "action": "COMPLETED",
        "stage": stage,
        "local_date": state.get("local_date"),
        "result": result,
    }
