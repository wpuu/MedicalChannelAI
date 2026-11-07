from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from collector_epoch import RuntimeCache

import collector_runtime as runtime
from collector_incremental import (
    SOURCE_POLICIES,
    VerificationDecision,
    empty_ledger,
    ledger_key,
    normalize_ledger,
    plan_detail_verification,
    record_verification_failure,
    record_verification_success,
    scan_bucket_id,
)
from collector_namespace import META_KEY, apply_runtime_namespace, cycle_has_running_stage

apply_runtime_namespace(runtime)

SUPPORTED_INCREMENTAL_SOURCES = (
    "tjmugh",
    "tjnothop",
    "teda",
    "tjfch",
    "tjfch_test",
    "tjzyefy",
    "tjzyefy_intent",
    "tjzxfc",
)

LEDGER_TTL_SECONDS = 45 * 24 * 60 * 60
BUCKET_TTL_SECONDS = 7 * 24 * 60 * 60
PENDING_TTL_SECONDS = 3 * 24 * 60 * 60


def _ledger_cache_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-ledger:{source_id}:v2"


def _bucket_cache_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-bucket:{source_id}:v2"


def _pending_cache_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-pending:{source_id}:v2"


def _pending_barrier_cache_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-pending-barrier:{source_id}:v2"


def _cache_set(cache: RuntimeCache, key: str, value: Any, *, ttl: int, tag: str) -> None:
    cache.set(key, value, {"ttl": ttl, "tags": [tag]})


def _load_ledger(cache: RuntimeCache, source_id: str) -> dict[str, Any]:
    return normalize_ledger(cache.get(_ledger_cache_key(source_id)))


def _save_ledger(cache: RuntimeCache, source_id: str, ledger: dict[str, Any]) -> None:
    _cache_set(
        cache,
        _ledger_cache_key(source_id),
        ledger,
        ttl=LEDGER_TTL_SECONDS,
        tag="medicalchannelai-collector-incremental-ledger",
    )


def _mark_budget_deferred(ledger: dict[str, Any], decisions: Iterable[VerificationDecision]) -> None:
    # Even a previously VERIFIED periodic recheck must remain eligible for
    # carryover when it disappears from a later bounded index response.
    for decision in decisions:
        entry = ledger["entries"][ledger_key(decision.candidate)]
        if entry.get("verification_status") == "VERIFIED":
            entry["verification_status"] = "UNVERIFIED"
        if not entry.get("last_error"):
            entry["last_error"] = "DETAIL_BUDGET_DEFERRED"


def _load_pending_records(cache: RuntimeCache, source_id: str) -> list[dict[str, Any]]:
    value = cache.get(_pending_cache_key(source_id))
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError("INCREMENTAL_PENDING_RECORDS_CORRUPT")
    return runtime.merge_canonical_records([], value)


def _save_pending_records(
    cache: RuntimeCache,
    source_id: str,
    records: list[dict[str, Any]],
) -> None:
    key = _pending_cache_key(source_id)
    if not records:
        cache.delete(key)
        return
    _cache_set(
        cache,
        key,
        records,
        ttl=PENDING_TTL_SECONDS,
        tag="medicalchannelai-collector-incremental-pending",
    )


def _load_pending_barrier(cache: RuntimeCache, source_id: str) -> set[str]:
    value = cache.get(_pending_barrier_cache_key(source_id))
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError("INCREMENTAL_PENDING_BARRIER_CORRUPT")
    return {item.strip() for item in value if item.strip()}


def _save_pending_barrier(cache: RuntimeCache, source_id: str, urls: set[str]) -> None:
    key = _pending_barrier_cache_key(source_id)
    normalized = sorted({str(item).strip() for item in urls if str(item).strip()})
    if not normalized:
        cache.delete(key)
        return
    _cache_set(
        cache,
        key,
        normalized,
        ttl=PENDING_TTL_SECONDS,
        tag="medicalchannelai-collector-incremental-pending-barrier",
    )


def reconcile_incremental_pending_from_canonical(
    cache: RuntimeCache, *, verified_after: datetime,
) -> dict[str, int]:
    """Resolve only URLs whose canonical verification supersedes pending state."""
    resolved = 0
    retained = 0
    for source_id in SUPPORTED_INCREMENTAL_SOURCES:
        barrier = _load_pending_barrier(cache, source_id)
        staged = _load_pending_records(cache, source_id)
        if not barrier and not staged:
            continue
        records, _ = _existing_records(cache, source_id)
        ledger = _load_ledger(cache, source_id)
        # v0.1 has only a source-level mutation time. Use it as a conservative
        # lower bound: an old verification cannot undo a newer failed attempt.
        raw_ledger_at = ledger.get("updated_at")
        threshold = _parsed_verification_time(raw_ledger_at)
        threshold = max(verified_after, threshold) if threshold else verified_after
        verified_urls = set()
        for record in records:
            source = record.get("source") or {}
            observed_at = _parsed_verification_time(source.get("observed_at"))
            if observed_at is not None and observed_at >= threshold:
                verified_urls.add(str(source.get("url") or ""))
        resolved += len(barrier & verified_urls)
        barrier.difference_update(verified_urls)
        remaining = [row for row in staged if str((row.get("source") or {}).get("url") or "") not in verified_urls]
        _save_pending_records(cache, source_id, remaining)
        _save_pending_barrier(cache, source_id, barrier)
        retained += len(barrier)
    return {"resolved_barrier_count": resolved, "retained_barrier_count": retained}


def _parsed_verification_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def _last_completed_bucket(cache: RuntimeCache, source_id: str) -> str | None:
    value = cache.get(_bucket_cache_key(source_id))
    if not isinstance(value, dict):
        return None
    bucket = str(value.get("bucket_id") or "").strip()
    return bucket or None


def _mark_bucket_completed(
    cache: RuntimeCache,
    *,
    source_id: str,
    bucket_id: str,
    completed_at: datetime,
    result: dict[str, Any],
) -> None:
    _cache_set(
        cache,
        _bucket_cache_key(source_id),
        {
            "schema_version": "0.1",
            "source_id": source_id,
            "bucket_id": bucket_id,
            "completed_at": completed_at.astimezone(timezone.utc).isoformat(),
            "result": result,
        },
        ttl=BUCKET_TTL_SECONDS,
        tag="medicalchannelai-collector-incremental-bucket",
    )


def _deep_cycle_running(cache: RuntimeCache) -> bool:
    return cycle_has_running_stage(cache.get(META_KEY))


def _now_utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("INCREMENTAL_RUNTIME_TIMEZONE_REQUIRED")
    return current.astimezone(timezone.utc)


def _source_delay_seconds(source_id: str) -> float:
    if source_id == "teda":
        return float(runtime.TEDA_REQUEST_DELAY_SECONDS)
    if source_id in {"tjfch", "tjfch_test"}:
        return float(runtime.TJFCH_REQUEST_DELAY_SECONDS)
    return 3.0


def _existing_records(cache: RuntimeCache, source_id: str) -> tuple[list[dict[str, Any]], str]:
    if source_id == "tjmugh":
        rows, _ = runtime._cached_list(cache, runtime.TJMUGH_RECORDS_KEY, runtime._bootstrap_tjmugh_records)
        return rows, runtime.TJMUGH_RECORDS_KEY
    if source_id == "tjnothop":
        rows, _ = runtime._cached_list(cache, runtime.TJNOTHOP_RECORDS_KEY, runtime._bootstrap_tjnothop_records)
        return rows, runtime.TJNOTHOP_RECORDS_KEY
    if source_id == "tjzyefy":
        rows, _ = runtime._cached_list(cache, runtime.TJZYEFY_RECORDS_KEY, runtime._bootstrap_tjzyefy_records)
        return rows, runtime.TJZYEFY_RECORDS_KEY
    if source_id == "tjzyefy_intent":
        rows, _ = runtime._cached_list(cache, runtime.TJZYEFY_INTENT_RECORDS_KEY, runtime._bootstrap_tjzyefy_intent_records)
        return rows, runtime.TJZYEFY_INTENT_RECORDS_KEY
    if source_id == "tjzxfc":
        rows, _ = runtime._cached_list(cache, runtime.TJZXFC_RECORDS_KEY, runtime._bootstrap_tjzxfc_records)
        return rows, runtime.TJZXFC_RECORDS_KEY
    if source_id == "teda":
        rows, _ = runtime._cached_list(cache, runtime.TEDA_RECORDS_KEY, runtime._bootstrap_teda_records)
        return rows, runtime.TEDA_RECORDS_KEY
    if source_id in {"tjfch", "tjfch_test"}:
        rows, _ = runtime._cached_list(cache, runtime.TJFCH_RECORDS_KEY, runtime._bootstrap_tjfch_records)
        return rows, runtime.TJFCH_RECORDS_KEY
    raise ValueError(f"INCREMENTAL_SOURCE_UNSUPPORTED:{source_id}")


def _discover_tjmugh(now: datetime) -> list[Any]:
    local_date = now.astimezone(runtime.SHANGHAI).date()
    html = runtime.fetch_tjmugh_page(runtime.TJMUGH_INDEX_URL)
    discovered = runtime.parse_tjmugh_index_html(html)
    return runtime.select_tjmugh_candidates(
        discovered,
        start_date=local_date - timedelta(days=6),
        end_date=local_date,
        max_candidates=15,
    )


def _verify_tjmugh(candidate: Any, observed_at: str, now: datetime) -> dict[str, Any] | None:
    html = runtime.fetch_tjmugh_page(candidate.detail_url)
    return runtime.parse_tjmugh_market_research(
        html,
        source_url=candidate.detail_url,
        observed_at=observed_at,
        opportunity_id=runtime.tjmugh_opportunity_id(candidate.detail_url),
    )


def _discover_tjnothop(now: datetime) -> list[Any]:
    local_date = now.astimezone(runtime.SHANGHAI).date()
    html = runtime.fetch_tjnothop_page(runtime.TJNOTHOP_INDEX_URL)
    discovered = runtime.parse_tjnothop_index_html(html)
    return runtime.select_tjnothop_candidates(
        discovered,
        start_date=local_date - timedelta(days=20),
        end_date=local_date,
        max_candidates=15,
    )


def _verify_tjnothop(candidate: Any, observed_at: str, now: datetime) -> dict[str, Any] | None:
    if not candidate.published_at:
        raise ValueError("TJNOTHOP_INDEX_PUBLISHED_DATE_REQUIRED")
    html = runtime.fetch_tjnothop_page(candidate.detail_url)
    return runtime.parse_tjnothop_market_research(
        html,
        source_url=candidate.detail_url,
        index_url=runtime.TJNOTHOP_INDEX_URL,
        index_published_at=candidate.published_at,
        expected_title=candidate.title,
        observed_at=observed_at,
        opportunity_id=runtime.tjnothop_opportunity_id(candidate.detail_url),
    )


def _discover_tjzyefy(now: datetime, *, budget=None) -> list[Any]:
    local_date = now.astimezone(runtime.SHANGHAI).date()
    html = (runtime.fetch_tjzyefy_page_with_retry(runtime.TJZYEFY_INDEX_URL, delay_seconds=3.0, budget=budget)
            if budget else runtime.fetch_tjzyefy_page_with_retry(runtime.TJZYEFY_INDEX_URL, delay_seconds=3.0))
    result = runtime.select_tjzyefy_candidates(
        runtime.parse_tjzyefy_index_html(html),
        start_date=local_date - timedelta(days=runtime.EARLY_SIGNAL_LOOKBACK_DAYS - 1),
        end_date=local_date, max_candidates=runtime.EARLY_SIGNAL_MAX_CANDIDATES,
    )
    if budget:
        budget.check("TJZYEFY_DISCOVERY_PARSE")
    return result


def _verify_tjzyefy(candidate: Any, observed_at: str, now: datetime, *, budget=None) -> dict[str, Any] | None:
    html = (runtime.fetch_tjzyefy_page_with_retry(candidate.detail_url, delay_seconds=3.0, budget=budget)
            if budget else runtime.fetch_tjzyefy_page_with_retry(candidate.detail_url, delay_seconds=3.0))
    try:
        result = runtime.parse_tjzyefy_market_research(
            html, source_url=candidate.detail_url, index_url=runtime.TJZYEFY_INDEX_URL,
            index_published_at=candidate.published_at, expected_title=candidate.title,
            observed_at=observed_at, opportunity_id=runtime.tjzyefy_opportunity_id(candidate.detail_url),
        )
    except runtime.TjzyefyParseError as exc:
        if budget:
            budget.check("TJZYEFY_DETAIL_PARSE")
        if str(exc) in runtime.TJZYEFY_UNSUPPORTED_DETAIL_CODES:
            return None
        raise
    if budget:
        budget.check("TJZYEFY_DETAIL_PARSE")
    return result


def _discover_tjzyefy_intent(now: datetime) -> list[Any]:
    local_date = now.astimezone(runtime.SHANGHAI).date()
    html = runtime.fetch_tjzyefy_page_with_retry(runtime.TJZYEFY_INDEX_URL, delay_seconds=3.0)
    return runtime.select_intent_candidates_since(
        runtime.parse_tjzyefy_intent_index_html(html),
        start_date=local_date - timedelta(days=runtime.EARLY_SIGNAL_LOOKBACK_DAYS - 1),
        end_date=local_date, max_candidates=runtime.EARLY_SIGNAL_MAX_CANDIDATES,
    )


def _verify_tjzyefy_intent(candidate: Any, observed_at: str, now: datetime) -> dict[str, Any] | None:
    html = runtime.fetch_tjzyefy_page_with_retry(candidate.detail_url, delay_seconds=3.0)
    try:
        return runtime.parse_tjzyefy_procurement_intent(
            html, source_url=candidate.detail_url, index_url=runtime.TJZYEFY_INDEX_URL,
            index_published_at=candidate.published_at, expected_title=candidate.title,
            observed_at=observed_at, opportunity_id=runtime.stable_intent_opportunity_id(candidate.detail_url),
        )
    except runtime.TjzyefyIntentParseError as exc:
        if str(exc) in runtime.TJZYEFY_INTENT_UNSUPPORTED_DETAIL_CODES:
            return None
        raise


def _discover_tjzxfc(now: datetime) -> list[Any]:
    local_date = now.astimezone(runtime.SHANGHAI).date()
    html = runtime.fetch_tjzxfc_page_with_retry(runtime.TJZXFC_INDEX_URL, delay_seconds=3.0)
    return runtime.select_tjzxfc_candidates(
        runtime.parse_tjzxfc_index_html(html),
        start_date=local_date - timedelta(days=runtime.EARLY_SIGNAL_LOOKBACK_DAYS - 1),
        end_date=local_date, max_candidates=runtime.EARLY_SIGNAL_MAX_CANDIDATES,
    )


def _verify_tjzxfc(candidate: Any, observed_at: str, now: datetime) -> dict[str, Any] | None:
    html = runtime.fetch_tjzxfc_page_with_retry(candidate.detail_url, delay_seconds=3.0)
    try:
        return runtime.parse_tjzxfc_market_research(
            html, source_url=candidate.detail_url, index_url=runtime.TJZXFC_INDEX_URL,
            index_published_at=candidate.published_at, expected_title=candidate.title,
            observed_at=observed_at, opportunity_id=runtime.tjzxfc_opportunity_id(candidate.detail_url),
        )
    except runtime.TjzxfcParseError as exc:
        if str(exc) in runtime.TJZXFC_UNSUPPORTED_DETAIL_CODES:
            return None
        raise


def _discover_teda(now: datetime) -> list[Any]:
    return list(
        runtime.discover_teda_candidates(
            index_pages=runtime.TEDA_INDEX_PAGES,
            delay_seconds=runtime.TEDA_REQUEST_DELAY_SECONDS,
        )
    )[: runtime.TEDA_MAX_CANDIDATES]


def _verify_teda(candidate: Any, observed_at: str, now: datetime) -> dict[str, Any] | None:
    try:
        html = runtime.fetch_teda_page_with_retry(
            candidate.detail_url,
            delay_seconds=runtime.TEDA_REQUEST_DELAY_SECONDS,
        )
        record = runtime.parse_teda_market_research(
            html,
            source_url=candidate.detail_url,
            index_url=candidate.index_url,
            index_published_at=candidate.published_at,
            expected_title=candidate.title,
            observed_at=observed_at,
            opportunity_id=runtime.teda_opportunity_id(candidate.detail_url),
        )
    except runtime.TedaParseError as exc:
        if str(exc) in runtime.TEDA_UNSUPPORTED_DETAIL_CODES:
            return None
        raise
    local_date = now.astimezone(runtime.SHANGHAI).date()
    start_date = local_date - timedelta(days=runtime.TEDA_LOOKBACK_DAYS - 1)
    published_at = datetime.fromisoformat(record["facts"]["published_at"]).date()
    return record if start_date <= published_at <= local_date else None


def _discover_tjfch(now: datetime) -> list[Any]:
    local_date = now.astimezone(runtime.SHANGHAI).date()
    html = runtime.fetch_tjfch_page(runtime.TJFCH_INDEX_URL)
    discovered = runtime.parse_tjfch_index_html(html)
    return runtime.select_tjfch_candidates(
        discovered,
        start_date=local_date - timedelta(days=runtime.TJFCH_LOOKBACK_DAYS - 1),
        end_date=local_date,
        max_candidates=runtime.TJFCH_MAX_CANDIDATES,
    )


def _verify_tjfch(candidate: Any, observed_at: str, now: datetime) -> dict[str, Any] | None:
    try:
        html = runtime.fetch_tjfch_page(candidate.detail_url)
        return runtime.parse_tjfch_procurement_notice(
            html,
            source_url=candidate.detail_url,
            index_url=runtime.TJFCH_INDEX_URL,
            index_published_at=candidate.published_at,
            expected_title=candidate.title,
            observed_at=observed_at,
            opportunity_id=runtime.tjfch_opportunity_id(candidate.detail_url),
        )
    except runtime.TjfchParseError as exc:
        if str(exc) == "TJFCH_BID_DEADLINE_NOT_EXACT":
            return None
        raise


def _discover_tjfch_test(now: datetime) -> list[Any]:
    html = runtime.fetch_tjfch_page(runtime.TJFCH_TEST_INDEX_URL)
    return list(
        runtime.parse_tjfch_test_index_html(
            html,
            max_candidates=runtime.TJFCH_TEST_MAX_CANDIDATES,
        )
    )


def _verify_tjfch_test(candidate: Any, observed_at: str, now: datetime) -> dict[str, Any] | None:
    try:
        html = runtime.fetch_tjfch_page(candidate.detail_url)
        record = runtime.parse_tjfch_test_recruitment(
            html,
            source_url=candidate.detail_url,
            index_url=runtime.TJFCH_TEST_INDEX_URL,
            expected_title=candidate.title,
            observed_at=observed_at,
            opportunity_id=runtime.tjfch_opportunity_id(candidate.detail_url),
        )
    except runtime.TjfchTestParseError as exc:
        if str(exc) == "TJFCH_TEST_REGISTRATION_WINDOW_UNSUPPORTED":
            return None
        raise
    local_date = now.astimezone(runtime.SHANGHAI).date()
    start_date = local_date - timedelta(days=runtime.TJFCH_TEST_LOOKBACK_DAYS - 1)
    published_at = datetime.fromisoformat(record["facts"]["published_at"]).date()
    return record if start_date <= published_at <= local_date else None


_DISCOVERY: dict[str, Callable[[datetime], list[Any]]] = {
    "tjmugh": _discover_tjmugh,
    "tjnothop": _discover_tjnothop,
    "teda": _discover_teda,
    "tjfch": _discover_tjfch,
    "tjfch_test": _discover_tjfch_test,
    "tjzyefy": _discover_tjzyefy,
    "tjzyefy_intent": _discover_tjzyefy_intent,
    "tjzxfc": _discover_tjzxfc,
}
_VERIFICATION: dict[str, Callable[[Any, str, datetime], dict[str, Any] | None]] = {
    "tjmugh": _verify_tjmugh,
    "tjnothop": _verify_tjnothop,
    "teda": _verify_teda,
    "tjfch": _verify_tjfch,
    "tjfch_test": _verify_tjfch_test,
    "tjzyefy": _verify_tjzyefy,
    "tjzyefy_intent": _verify_tjzyefy_intent,
    "tjzxfc": _verify_tjzxfc,
}


def _candidate_from_decision(decision: VerificationDecision, discovered_by_url: dict[str, Any]) -> Any:
    candidate = discovered_by_url.get(decision.candidate.detail_url)
    if candidate is not None:
        return candidate
    # Carryover candidates were discovered on an earlier bounded index scan and
    # are intentionally absent from today's truncated discovery set. Their
    # CandidateObservation contains the exact official URL/index metadata whose
    # fingerprint was persisted in the source ledger. Only this explicit reason
    # may bypass the current-discovery lookup; all other misses remain bugs.
    if decision.reason == "PENDING_CARRYOVER":
        return decision.candidate
    raise RuntimeError("INCREMENTAL_SELECTED_CANDIDATE_MISSING")


def _publish_snapshot_if_ready(cache: RuntimeCache, now: datetime, *, budget=None) -> tuple[bool, dict[str, Any] | None]:
    try:
        result = (runtime._run_publish(cache, {"cycle_as_of": now.isoformat()}, budget=budget)
                  if budget else runtime._run_publish(cache, {"cycle_as_of": now.isoformat()}))
    except runtime.CollectorPrecondition:
        return False, None
    return True, result


def run_incremental_source(
    source_id: str, *, now: datetime | None = None, cache: RuntimeCache | None = None,
    budget=None,
) -> tuple[int, dict[str, Any]]:
    # Only the explicitly authorized source receives this optional Queue budget.
    if str(source_id or "").strip().lower() != "tjzyefy":
        budget = None
    if budget is None:
        return _run_incremental_source(source_id, now=now, cache=cache)
    cache = cache or RuntimeCache()
    context = {"phase": "PRECHECK", "ledger": None, "barrier": None, "remaining": (),
               "canonical_mutation_possible": False, "canonical_write_completed": False, "source_finalized": False,
               "pending_or_ledger_mutation_possible": False, "health_mutation_possible": False,
               "bucket_mutation_possible": False, "publication_outcome": "NOT_ATTEMPTED"}
    try:
        status, result = _run_incremental_source(source_id, now=now, cache=cache,
                                                 budget=budget, context=context)
    except Exception as exc:
        failed_phase = context["phase"]
        time_stop = isinstance(exc, runtime.CliBudgetExceeded)
        recovery_confirmed = False
        recovery_error = None
        try:
            if not context["source_finalized"] and not context["canonical_mutation_possible"] and context["ledger"] is not None:
                ledger = context["ledger"]
                remaining = context["remaining"]
                _mark_budget_deferred(ledger, remaining)
                budget.check("RECOVERY_READ", finalize=True)
                barrier = set(context["barrier"] or ()) | _load_pending_barrier(cache, "tjzyefy")
                barrier.update(row.candidate.detail_url for row in remaining)
                budget.check("RECOVERY_BARRIER", finalize=True)
                _save_pending_barrier(cache, "tjzyefy", barrier)
                budget.check("RECOVERY_LEDGER", finalize=True)
                _save_ledger(cache, "tjzyefy", ledger)
                budget.check("RECOVERY_RETURN", finalize=True)
                recovery_confirmed = True
            if not context["source_finalized"] and not context["canonical_mutation_possible"]:
                budget.check("FAILURE_HEALTH", finalize=True)
                context["health_mutation_possible"] = True
                runtime.record_source_scan(cache, "tjzyefy", successful=False, attempted_at=_now_utc(now),
                                           failure_reason="DETAIL_VERIFICATION_PENDING")
        except Exception as save_error:
            recovery_error = type(save_error).__name__
        status, result = 503, {
            "action": "FAILED", "source_id": "tjzyefy",
            "error": "INCREMENTAL_TIME_BUDGET_EXCEEDED" if time_stop else "INCREMENTAL_STATE_RESULT_UNKNOWN",
            "error_type": type(exc).__name__, "error_phase": failed_phase,
            "snapshot_refreshed": context.get("snapshot_refreshed", False),
            "snapshot_as_of": context.get("snapshot_as_of"),
            "recovery_confirmed": recovery_confirmed, "recovery_scope": "PENDING_BARRIER_AND_LEDGER_ONLY",
            "recovery_error_type": recovery_error,
            "failure_ledger_error_type": context.get("failure_ledger_error_type"),
        }
    receipt = {key: context[key] for key in ("canonical_mutation_possible", "canonical_write_completed",
                "pending_or_ledger_mutation_possible", "health_mutation_possible",
                "bucket_mutation_possible", "publication_outcome")}
    return status, {**result, **receipt, "publish_receipt": context.get("publish_receipt"), "budget": budget.snapshot(),
                    "budget_observation_phase": "SOURCE_RETURN",
                    "budget_finalization_overrun": budget.clock() >= budget.started + budget.total_seconds}


def _run_incremental_source(
    source_id: str,
    *,
    now: datetime | None = None,
    cache: RuntimeCache | None = None,
    budget=None,
    context=None,
) -> tuple[int, dict[str, Any]]:
    source = str(source_id or "").strip().lower()
    if source not in SUPPORTED_INCREMENTAL_SOURCES:
        return 400, {"action": "REJECTED", "error": "INCREMENTAL_SOURCE_UNSUPPORTED", "source_id": source}

    def work(phase):
        if budget:
            context["phase"] = phase
            budget.check(phase)

    def total(phase):
        if budget:
            context["phase"] = phase
            budget.check(phase, finalize=True)

    def url_check(phase):
        total(phase)
        if budget and budget.clock() >= save_deadline:
            budget.fail(phase)

    observed = _now_utc(now)
    cache = cache or RuntimeCache()
    if _deep_cycle_running(cache):
        return 409, {
            "action": "DEFERRED",
            "error": "INCREMENTAL_BLOCKED_BY_DEEP_CYCLE",
            "source_id": source,
        }

    bucket_id = scan_bucket_id(source, now=observed)
    if _last_completed_bucket(cache, source) == bucket_id:
        return 200, {
            "action": "ALREADY_SCANNED_BUCKET",
            "source_id": source,
            "bucket_id": bucket_id,
        }

    try:
        work("DISCOVERY")
        if budget:
            discovered = _DISCOVERY[source](observed, budget=budget)
        else:
            discovered = _DISCOVERY[source](observed)
        work("DISCOVERY_PARSE")
    except runtime.CliBudgetExceeded:
        raise
    except Exception as exc:
        work("DISCOVERY_ERROR")
        if budget:
            context.update(phase="FAILURE_HEALTH", health_mutation_possible=True)
        runtime.record_source_scan(cache, source, successful=False, attempted_at=observed,
                                   failure_reason="INDEX_SCAN_FAILED")
        return 503, {
            "action": "FAILED",
            "source_id": source,
            "bucket_id": bucket_id,
            "error": f"INCREMENTAL_DISCOVERY_FAILED:{type(exc).__name__}:{str(exc)[:180]}",
        }

    # Bootstrap is an optimization for a brand-new ledger, but it must reuse the
    # exact discovery rows from this real scan. Local import avoids the bootstrap
    # module's runtime reference becoming an import-time cycle.
    from collector_incremental_bootstrap import bootstrap_incremental_ledger_from_canonical

    bootstrap_incremental_ledger_from_canonical(
        source,
        now=observed,
        cache=cache,
        discovered=discovered,
    )

    ledger = _load_ledger(cache, source)
    policy = SOURCE_POLICIES[source]
    plan = plan_detail_verification(
        source,
        discovered,
        ledger,
        now=observed,
        reverify_after_hours=policy["reverify_after_hours"],
        max_details=policy["max_details_per_scan"],
    )
    ledger = plan.next_ledger
    if budget:
        context.update(ledger=ledger, remaining=plan.selected)
    _mark_budget_deferred(ledger, plan.deferred)
    scan_barrier = _load_pending_barrier(cache, source)
    scan_barrier.update(item.candidate.detail_url for item in (*plan.selected, *plan.deferred))
    if budget:
        context["barrier"] = scan_barrier
        context["pending_or_ledger_mutation_possible"] = True
    work("PREPARE_BARRIER")
    _save_pending_barrier(cache, source, scan_barrier)
    work("PREPARE_LEDGER")
    _save_ledger(cache, source, ledger)
    work("PREPARE_RETURN")
    durable_staging = _load_pending_records(cache, source)

    discovered_by_url = {
        str(getattr(item, "detail_url", "") or (item.get("detail_url") if isinstance(item, dict) else "")): item
        for item in discovered
    }
    verified_records: list[dict[str, Any]] = []
    nonfact_verified_count = 0
    failures: list[dict[str, str]] = []
    successful_urls: set[str] = set()
    verified_nonfact_urls: set[str] = set()
    observed_at = observed.isoformat()
    delay_seconds = _source_delay_seconds(source)

    for index, decision in enumerate(plan.selected):
        candidate = _candidate_from_decision(decision, discovered_by_url)
        if not budget and (index > 0 or delay_seconds > 0):
            runtime.time.sleep(delay_seconds)
        verified = False
        save_deadline = None
        try:
            work("DETAIL_SLEEP")
            if budget:
                budget.sleep_checked(delay_seconds, "DETAIL_SLEEP")
                record = _VERIFICATION[source](candidate, observed_at, observed, budget=budget)
            else:
                record = _VERIFICATION[source](candidate, observed_at, observed)
            work("DETAIL_PARSE")
            if budget:
                save_deadline = min(budget.clock() + 30, budget.started + 210)
            # Persist verified facts before a VERIFIED ledger can make the next
            # scan skip them. A hard timeout must not strand facts in memory.
            if record is not None:
                durable_staging = runtime.merge_canonical_records(durable_staging, [record])
                url_check("URL_STAGING")
                _save_pending_records(cache, source, durable_staging)
                url_check("URL_STAGING_RETURN")
            # A successful explicit non-fact also resolves only its own URL.
            # Do this before the ledger update so interruption remains retryable.
            url_check("URL_BARRIER")
            scan_barrier.discard(decision.candidate.detail_url)
            _save_pending_barrier(cache, source, scan_barrier)
            url_check("URL_BARRIER_RETURN")
            ledger = record_verification_success(
                ledger,
                decision.candidate,
                verified_at=observed,
            )
            verified = True
        except runtime.CliBudgetExceeded:
            if budget:
                _mark_budget_deferred(ledger, plan.selected[index:])
            raise
        except Exception as exc:
            failed_phase = context["phase"] if budget else ""
            if not failed_phase.startswith("URL_"):
                work("DETAIL_ERROR")
            ledger = record_verification_failure(
                ledger,
                decision.candidate,
                f"{type(exc).__name__}:{str(exc)[:220]}",
                failed_at=observed,
            )
            failures.append({"url": decision.candidate.detail_url,
                             "error": type(exc).__name__, "message": str(exc)[:180]})
            if budget and failed_phase.startswith("URL_"):
                raise
        finally:
            active_error = sys.exc_info()[1]
            if budget:
                context["ledger"] = ledger
            if budget and active_error is not None:
                # A failed cleanup must not replace the original cache/parse/hard-stop error.
                try:
                    budget.check("FAILURE_LEDGER", finalize=True)
                    _save_ledger(cache, source, ledger)
                except Exception as ledger_error:
                    context["failure_ledger_error_type"] = type(ledger_error).__name__
            else:
                if budget and verified:
                    url_check("URL_LEDGER")
                elif budget:
                    total("FAILURE_LEDGER")
                _save_ledger(cache, source, ledger)
                if budget and verified:
                    url_check("URL_LEDGER_RETURN")
        if verified:
            successful_urls.add(decision.candidate.detail_url)
            if budget:
                context["remaining"] = plan.selected[index + 1:]
            if record is None:
                nonfact_verified_count += 1
                verified_nonfact_urls.add(decision.candidate.detail_url)
            else:
                verified_records.append(record)

    existing_records, cache_key = _existing_records(cache, source)
    pending_records = _load_pending_records(cache, source)
    pending_barrier = _load_pending_barrier(cache, source)
    pending_barrier.difference_update(successful_urls)
    pending_barrier.update(item["url"] for item in failures)
    pending_barrier.update(item.candidate.detail_url for item in plan.deferred)
    staged_records = (
        runtime.merge_canonical_records(pending_records, verified_records)
        if pending_records or verified_records
        else []
    )

    base_result = {
        "source_id": source,
        "bucket_id": bucket_id,
        "discovered_candidate_count": len(discovered),
        "selected_detail_count": len(plan.selected),
        "deferred_detail_count": len(plan.deferred),
        "skipped_unchanged_count": len(plan.skipped_unchanged),
        "verified_record_count": len(verified_records),
        "verified_nonfact_count": nonfact_verified_count,
        "verification_failure_count": len(failures),
        "canonical_record_count": len(existing_records),
        "pending_record_count": len(staged_records),
        "pending_barrier_count": len(pending_barrier),
    }

    if budget:
        context["phase"] = "FINALIZE_ADMISSION"
        if budget.clock() >= budget.started + 210:
            budget.fail("FINALIZE_ADMISSION")
        budget.work_complete = not failures and not pending_barrier

    if failures:
        total("FAILURE_FINALIZE")
        if budget:
            context.update(phase="FAILURE_HEALTH", health_mutation_possible=True)
        runtime.record_source_scan(cache, source, successful=False, attempted_at=observed,
                                   failure_reason="DETAIL_VERIFICATION_PENDING")
        _save_pending_records(cache, source, staged_records)
        _save_pending_barrier(cache, source, pending_barrier)
        return 503, {
            "action": "FAILED",
            **base_result,
            "snapshot_refreshed": False,
            "snapshot_as_of": None,
            "error": "INCREMENTAL_DETAIL_VERIFICATION_INCOMPLETE",
            "failures": failures[:5],
        }

    if pending_barrier:
        total("PENDING_FINALIZE")
        if budget:
            context.update(phase="FAILURE_HEALTH", health_mutation_possible=True)
        runtime.record_source_scan(cache, source, successful=False, attempted_at=observed,
                                   failure_reason="DETAIL_VERIFICATION_PENDING")
        # A detail that failed in an earlier attempt disappeared from this scan's
        # discovery set. Do not infer that the failure was resolved. Keep all
        # successful sibling records isolated, finish this bucket without a public
        # refresh, and let the normal source interval recheck the unresolved URL.
        # A later deep verification may resolve only the URLs it actually covers.
        _save_pending_records(cache, source, staged_records)
        _save_pending_barrier(cache, source, pending_barrier)
        result = {
            **base_result,
            "snapshot_refreshed": False,
            "snapshot_as_of": None,
            "deferred_reason": "DETAIL_BUDGET_DEFERRED" if plan.deferred else "PENDING_VERIFICATION_BARRIER",
        }
        total("PENDING_BUCKET")
        if budget:
            context["bucket_mutation_possible"] = True
        _mark_bucket_completed(
            cache,
            source_id=source,
            bucket_id=bucket_id,
            completed_at=observed,
            result=result,
        )
        return 200, {"action": "COMPLETED", **result}

    if staged_records:
        merged = runtime.merge_canonical_records(existing_records, staged_records)
        total("PRE_CANONICAL")
        if budget:
            context.update(canonical_mutation_possible=True, canonical_write_completed=None)
        runtime._cache_set(
            cache,
            cache_key,
            merged,
            tag="medicalchannelai-collector-canonical",
            verified_nonfact_urls=verified_nonfact_urls,
            canonical_source_id=source,
        )
    else:
        merged = existing_records
    if budget:
        context["canonical_write_completed"] = True if staged_records else False
        context["phase"] = "POST_CANONICAL"
        context["source_finalized"] = True
    _save_pending_records(cache, source, [])
    _save_pending_barrier(cache, source, set())
    if budget:
        context["phase"] = "HEALTH"
        context["health_mutation_possible"] = True
    runtime.record_source_scan(cache, source, successful=True, attempted_at=observed)

    completed_result = {
        **base_result,
        "canonical_record_count": len(merged),
        "pending_record_count": 0,
        "pending_barrier_count": 0,
    }
    try:
        total("PUBLISH_ADMISSION")
        if budget:
            if budget.started + budget.total_seconds - budget.clock() < 31:
                budget.fail("PUBLISH_ADMISSION")
            context.update(phase="PUBLISH", publication_outcome="NOT_ATTEMPTED")
        snapshot_refreshed, publish_result = (_publish_snapshot_if_ready(cache, observed, budget=budget)
                                             if budget else _publish_snapshot_if_ready(cache, observed))
        if budget:
            context["publication_outcome"] = "CONFIRMED" if snapshot_refreshed else "NO_REFRESH"
            context["publish_receipt"] = publish_result.get("publish_receipt") if publish_result else None
            context.update(snapshot_refreshed=snapshot_refreshed,
                           snapshot_as_of=publish_result.get("snapshot_as_of") if publish_result else None)
    except Exception as exc:
        if budget:
            receipt = getattr(exc, "diagnostics", {}).get("publish_receipt")
            context["publish_receipt"] = receipt
            context["publication_outcome"] = receipt.get("publication_outcome", "UNKNOWN") if receipt else "UNKNOWN"
        if isinstance(exc, runtime.CliBudgetExceeded):
            raise
        return 503, {
            "action": "FAILED",
            **completed_result,
            "snapshot_refreshed": False,
            "snapshot_as_of": None,
            "error": f"INCREMENTAL_SNAPSHOT_REFRESH_FAILED:{type(exc).__name__}:{str(exc)[:180]}",
        }

    result = {
        **completed_result,
        "snapshot_refreshed": snapshot_refreshed,
        "snapshot_as_of": publish_result.get("snapshot_as_of") if publish_result else None,
    }
    if budget:
        context.update(phase="BUCKET", bucket_mutation_possible=True)
    _mark_bucket_completed(
        cache,
        source_id=source,
        bucket_id=bucket_id,
        completed_at=observed,
        result=result,
    )
    return 200, {"action": "COMPLETED", **result}
