from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from vercel.functions import RuntimeCache

import collector_runtime as runtime
from collector_incremental import (
    SOURCE_POLICIES,
    VerificationDecision,
    empty_ledger,
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
)

LEDGER_TTL_SECONDS = 45 * 24 * 60 * 60
BUCKET_TTL_SECONDS = 7 * 24 * 60 * 60


def _ledger_cache_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-ledger:{source_id}:v2"


def _bucket_cache_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-bucket:{source_id}:v2"


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
            # Unsupported format is still a completed verification attempt. Marking
            # the discovery fingerprint as checked avoids hammering the same detail
            # every scan; metadata change or the periodic recheck will revisit it.
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
}
_VERIFICATION: dict[str, Callable[[Any, str, datetime], dict[str, Any] | None]] = {
    "tjmugh": _verify_tjmugh,
    "tjnothop": _verify_tjnothop,
    "teda": _verify_teda,
    "tjfch": _verify_tjfch,
    "tjfch_test": _verify_tjfch_test,
}


def _candidate_from_decision(decision: VerificationDecision, discovered_by_url: dict[str, Any]) -> Any:
    candidate = discovered_by_url.get(decision.candidate.detail_url)
    if candidate is None:
        raise RuntimeError("INCREMENTAL_SELECTED_CANDIDATE_MISSING")
    return candidate


def _publish_snapshot_if_ready(cache: RuntimeCache, now: datetime) -> tuple[bool, dict[str, Any] | None]:
    try:
        result = runtime._run_publish(cache, {"cycle_as_of": now.isoformat()})
    except runtime.CollectorPrecondition:
        # A brand-new environment may not have all source caches bootstrapped yet.
        # The daily deep collector remains the bootstrap/authority in that case.
        return False, None
    return True, result


def run_incremental_source(
    source_id: str,
    *,
    now: datetime | None = None,
    cache: RuntimeCache | None = None,
) -> tuple[int, dict[str, Any]]:
    source = str(source_id or "").strip().lower()
    if source not in SUPPORTED_INCREMENTAL_SOURCES:
        return 400, {"action": "REJECTED", "error": "INCREMENTAL_SOURCE_UNSUPPORTED", "source_id": source}

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
        discovered = _DISCOVERY[source](observed)
    except Exception as exc:
        return 503, {
            "action": "FAILED",
            "source_id": source,
            "bucket_id": bucket_id,
            "error": f"INCREMENTAL_DISCOVERY_FAILED:{type(exc).__name__}:{str(exc)[:180]}",
        }

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
    _save_ledger(cache, source, ledger)

    discovered_by_url = {
        str(getattr(item, "detail_url", "") or (item.get("detail_url") if isinstance(item, dict) else "")): item
        for item in discovered
    }
    verified_records: list[dict[str, Any]] = []
    nonfact_verified_count = 0
    failures: list[dict[str, str]] = []
    observed_at = observed.isoformat()
    delay_seconds = _source_delay_seconds(source)

    for index, decision in enumerate(plan.selected):
        candidate = _candidate_from_decision(decision, discovered_by_url)
        if index > 0 or delay_seconds > 0:
            runtime.time.sleep(delay_seconds)
        try:
            record = _VERIFICATION[source](candidate, observed_at, observed)
            ledger = record_verification_success(
                ledger,
                decision.candidate,
                verified_at=observed,
            )
            if record is None:
                nonfact_verified_count += 1
            else:
                verified_records.append(record)
        except Exception as exc:
            ledger = record_verification_failure(
                ledger,
                decision.candidate,
                f"{type(exc).__name__}:{str(exc)[:220]}",
                failed_at=observed,
            )
            failures.append(
                {
                    "url": decision.candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:180],
                }
            )
        finally:
            _save_ledger(cache, source, ledger)

    existing_records, cache_key = _existing_records(cache, source)
    if verified_records:
        merged = runtime.merge_canonical_records(existing_records, verified_records)
        runtime._cache_set(
            cache,
            cache_key,
            merged,
            tag="medicalchannelai-collector-canonical",
        )
    else:
        merged = existing_records

    try:
        snapshot_refreshed, publish_result = _publish_snapshot_if_ready(cache, observed)
    except Exception as exc:
        return 503, {
            "action": "FAILED",
            "source_id": source,
            "bucket_id": bucket_id,
            "error": f"INCREMENTAL_SNAPSHOT_REFRESH_FAILED:{type(exc).__name__}:{str(exc)[:180]}",
            "verified_record_count": len(verified_records),
            "verification_failure_count": len(failures),
        }

    result = {
        "source_id": source,
        "bucket_id": bucket_id,
        "discovered_candidate_count": len(discovered),
        "selected_detail_count": len(plan.selected),
        "deferred_detail_count": len(plan.deferred),
        "skipped_unchanged_count": len(plan.skipped_unchanged),
        "verified_record_count": len(verified_records),
        "verified_nonfact_count": nonfact_verified_count,
        "verification_failure_count": len(failures),
        "canonical_record_count": len(merged),
        "snapshot_refreshed": snapshot_refreshed,
        "snapshot_as_of": publish_result.get("snapshot_as_of") if publish_result else None,
    }

    if failures:
        # Leave this bucket incomplete so the queue redelivery can retry only the
        # failed fingerprints. Successful details are already marked VERIFIED and
        # will be skipped on the retry, avoiding duplicate official requests.
        return 503, {
            "action": "FAILED",
            **result,
            "error": "INCREMENTAL_DETAIL_VERIFICATION_INCOMPLETE",
            "failures": failures[:5],
        }

    _mark_bucket_completed(
        cache,
        source_id=source,
        bucket_id=bucket_id,
        completed_at=observed,
        result=result,
    )
    return 200, {"action": "COMPLETED", **result}
