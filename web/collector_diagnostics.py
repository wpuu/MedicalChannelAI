"""Bounded diagnostics: never persist exception text, URLs, queries or titles."""
from __future__ import annotations
import hashlib
import re
from collections import Counter
from typing import Any
from urllib.error import HTTPError

SAFE_CCGP_CODES = frozenset({
    "CCGP_BID_DEADLINE_NOT_FOUND",
    "CCGP_BUYER_NOT_FOUND",
    "CCGP_COMPETITIVE_CONSULTATION_METHOD_NOT_FOUND",
    "CCGP_DETAIL_SOURCE_HOST_REJECTED",
    "CCGP_NOTICE_TYPE_NOT_COMPETITIVE_CONSULTATION",
    "CCGP_NOTICE_TYPE_NOT_PUBLIC_TENDER",
    "CCGP_PROJECT_NAME_NOT_FOUND",
    "CCGP_PROJECT_NUMBER_NOT_FOUND",
    "CCGP_PUBLISHED_DATE_NOT_FOUND",
    "CCGP_REGISTRATION_END_TIME_NOT_FOUND",
    "CCGP_REGISTRATION_SECTION_NOT_FOUND",
    "CCGP_RESPONSE_DEADLINE_NOT_FOUND",
    "CCGP_TIME_INVALID",
    "CCGP_EVENT_SOURCE_HOST_REJECTED",
    "CCGP_EVENT_PROJECT_NUMBER_NOT_FOUND",
    "CCGP_EVENT_PUBLISHED_DATE_NOT_FOUND",
    "CCGP_EVENT_TYPE_NOT_SUPPORTED",
})
PHASES = {"scoped_discovery", "national_fallback_discovery", "verified_detail", "pre_detail_market_guard", "index_discovery",
          "event_search", "event_detail", "event_scan"}

def _failure_reason(error_type: str, raw_message: str, http_code: int | None = None) -> str:
    message = raw_message.partition(":")[0]
    if isinstance(http_code, int) and 100 <= http_code <= 599:
        reason = f"HTTP_{http_code}"
    elif message in SAFE_CCGP_CODES:
        reason = message
    elif message == "CCGP_RATE_LIMITED":
        reason = "RATE_LIMITED"
    elif re.fullmatch(r"CCGP_DETAIL_HTTP_[1-5][0-9]{2}", message):
        reason = message
    elif message == "CCGP_DETAIL_NETWORK_ERROR":
        reason = "NETWORK_ERROR"
    else:
        reason = {"TimeoutError": "NETWORK_TIMEOUT", "HTTPError": "HTTP_ERROR", "URLError": "NETWORK_ERROR",
                  "UnicodeDecodeError": "RESPONSE_ENCODING_ERROR", "CcgpDetailParseError": "DETAIL_PARSE_FAILED",
                  "CcgpEventParseError": "EVENT_PARSE_FAILED",
                  "ValueError": "DETAIL_VALIDATION_FAILED"}.get(error_type, "SOURCE_VERIFICATION_FAILED")
    return reason

def failure_row(phase: str, exc: Exception | None, reference: str) -> dict[str, str]:
    phase = phase if phase in PHASES else "verified_detail"
    reason = _failure_reason(type(exc).__name__, str(exc) if exc is not None else "",
                             exc.code if isinstance(exc, HTTPError) else None)
    return {"phase": phase, "reason": reason, "candidate_ref": hashlib.sha256(reference.encode()).hexdigest()}

def reported_event_failure_row(report: dict[str, Any]) -> dict[str, str]:
    """Reduce scan_events' internal report to fixed codes and a hashed reference."""
    phase = report.get("stage")
    phase = phase if isinstance(phase, str) and phase in {"event_search", "event_detail"} else "event_scan"
    error_type = report.get("error") if isinstance(report.get("error"), str) else ""
    message = report.get("message") if isinstance(report.get("message"), str) else ""
    http = re.match(r"HTTP Error ([1-5][0-9]{2}):", message) if error_type == "HTTPError" else None
    reason = _failure_reason(error_type, message, int(http[1]) if http else None)
    reference = (str(report.get("url") or "") if phase == "event_detail" else
                 f"{report.get('project_number') or ''}:{report.get('notice_type') or ''}")
    return {"phase": phase, "reason": reason, "candidate_ref": hashlib.sha256(reference.encode()).hexdigest()}

def failure_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {"failure_count": len(rows),
            "reason_counts": dict(sorted(Counter(row["reason"] for row in rows).items())),
            "phase_counts": dict(sorted(Counter(row["phase"] for row in rows).items())),
            "samples": sorted(rows, key=lambda row: (row["phase"], row["candidate_ref"], row["reason"]))[:5]}
