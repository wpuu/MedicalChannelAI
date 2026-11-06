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
})
PHASES = {"scoped_discovery", "national_fallback_discovery", "verified_detail", "pre_detail_market_guard", "index_discovery"}

def failure_row(phase: str, exc: Exception | None, reference: str) -> dict[str, str]:
    phase = phase if phase in PHASES else "verified_detail"
    message = str(exc).partition(":")[0] if exc is not None else ""
    if isinstance(exc, HTTPError) and 100 <= exc.code <= 599:
        reason = f"HTTP_{exc.code}"
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
                  "ValueError": "DETAIL_VALIDATION_FAILED"}.get(type(exc).__name__, "SOURCE_VERIFICATION_FAILED")
    return {"phase": phase, "reason": reason, "candidate_ref": hashlib.sha256(reference.encode()).hexdigest()}

def failure_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {"failure_count": len(rows),
            "reason_counts": dict(sorted(Counter(row["reason"] for row in rows).items())),
            "phase_counts": dict(sorted(Counter(row["phase"] for row in rows).items())),
            "samples": sorted(rows, key=lambda row: (row["phase"], row["candidate_ref"]))[:5]}
