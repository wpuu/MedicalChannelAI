"""Optional isolated C05 client for durable failure-cycle event receipts.

Uses a dedicated collector-audit-only token, never the verified-snapshot
publisher token. Disabled by default; no production environment changes here.
Remote failures cannot turn a failed collector stage into success or invalidate
the original Queue exception. Only exact allowlisted event metadata is sent.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ENDPOINT = "https://medicalchannelai.vercel.app/api/collector-audit"
CYCLE = re.compile(r"^prod:\d{4}-\d{2}-\d{2}:(?:morning|noon):twice-daily-v1$")
STAGE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
ERROR = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")
EVENTS = frozenset({
    "CRON_QUEUE_FAILED",
    "STAGE_RETRY_ERROR",
    "STAGE_TERMINAL_FAILURE",
    "SOURCE_WINDOW_BLOCKED",
})


def audit_enabled() -> bool:
    return (
        os.environ.get("COLLECTOR_AUDIT_ENABLED") == "true"
        and len(os.environ.get("COLLECTOR_AUDIT_TOKEN", "").strip()) >= 32
    )


def try_persist_failure(
    *,
    cycle_id: str,
    stage: str,
    event_kind: str,
    error_code: str,
    occurred_at: datetime | None = None,
) -> bool:
    """Best-effort one HTTP call, timeout 2s, no retry, no token disclosure."""
    if not audit_enabled():
        return False
    if not (
        isinstance(cycle_id, str) and CYCLE.fullmatch(cycle_id)
        and isinstance(stage, str) and STAGE.fullmatch(stage)
        and event_kind in EVENTS
    ):
        return False
    code = error_code if isinstance(error_code, str) and ERROR.fullmatch(error_code) else "ERROR_CODE_UNAVAILABLE"
    at = occurred_at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        return False
    body = json.dumps(
        {
            "cycle_id": cycle_id,
            "stage_id": stage,
            "event_kind": event_kind,
            "error_code": code,
            "occurred_at": at.astimezone(timezone.utc).isoformat(),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + os.environ["COLLECTOR_AUDIT_TOKEN"].strip(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=2.0) as response:
            if response.status != 200:
                return False
            receipt = json.loads(response.read(600).decode("utf-8"))
        return receipt.get("ok") is True and bool(re.fullmatch(r"[a-f0-9]{64}", str(receipt.get("event_id") or "")))
    except Exception:
        # Credentials, HTTP bodies and raw transport exceptions must never
        # appear in logs or collector error payloads. The original Queue error
        # remains the single authoritative reason for retries.
        return False
