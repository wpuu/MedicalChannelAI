from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

# Reuses the existing authenticated publisher. No token in URLs or logs.
AUDIT_URL = "https://medicalchannelai.vercel.app/api/public-snapshot"
AUDIT_TIMEOUT_SECONDS = 3


def emit_collector_audit(
    *, cycle_id: str, cycle_as_of: str, stage: str,
    status: str, outcome: str, error_code: str | None = None,
    attempt_count: int | None = None,
    new_verified_record_count: int | None = None,
) -> bool:
    if os.environ.get("VERCEL_ENV") != "production":
        return False
    token = str(os.environ.get("VERIFIED_SNAPSHOT_PUBLISH_TOKEN") or "").strip()
    if len(token) < 24:
        print(f"COLLECTOR_AUDIT_NOT_CONFIGURED:{stage}", flush=True)
        return False
    event = {
        "schema_version": "0.1", "cycle_id": cycle_id,
        "cycle_as_of": cycle_as_of, "stage": stage,
        "status": status, "outcome": outcome,
        "error_code": error_code,
    }
    if attempt_count is not None:
        event["attempt_count"] = int(attempt_count)
    if new_verified_record_count is not None:
        event["new_verified_record_count"] = int(new_verified_record_count)
    request = Request(
        AUDIT_URL, method="PATCH",
        data=json.dumps(event, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MedicalChannelAI-CollectorAudit/0.1",
        },
    )
    try:
        with urlopen(request, timeout=AUDIT_TIMEOUT_SECONDS) as response:
            status_code = int(getattr(response, "status", 0) or 0)
            response.read(2048)
        return status_code == 200
    except Exception as exc:
        # Never suppress a legitimate collector stage or expose credentials.
        print(f"COLLECTOR_AUDIT_WRITE_FAILED:{stage}:{type(exc).__name__}", flush=True)
        return False
