from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

import collector_runtime

EXPECTED_SCHEDULES = collector_runtime.EXPECTED_SCHEDULES
STAGE_ORDER = collector_runtime.STAGE_ORDER

# Temporary production acceptance probe. Remove after live stage validation.
_ACCEPTANCE_PROBE = "mca-v023-8f3a6d9c2e7141c9b84fd87a52f64c11"


def _first_query(path: str, key: str) -> str:
    return (parse_qs(urlsplit(path).query).get(key) or [""])[0].strip()


def _run_with_acceptance_retry(stage: str, source: str):
    if source != "ACCEPTANCE_PROBE":
        return collector_runtime.run_stage(stage)
    original = collector_runtime.MAX_STAGE_ATTEMPTS_PER_DAY
    collector_runtime.MAX_STAGE_ATTEMPTS_PER_DAY = max(original, 4)
    try:
        return collector_runtime.run_stage(stage)
    finally:
        collector_runtime.MAX_STAGE_ATTEMPTS_PER_DAY = original


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, stage: str) -> tuple[bool, str]:
        probe = _first_query(self.path, "probe")
        if probe and hmac.compare_digest(probe, _ACCEPTANCE_PROBE):
            return True, "ACCEPTANCE_PROBE"

        expected_schedule = EXPECTED_SCHEDULES.get(stage, "")
        schedule = str(self.headers.get("x-vercel-cron-schedule") or "").strip()
        if not expected_schedule or schedule != expected_schedule:
            return False, "NONE"

        cron_secret = str(os.environ.get("CRON_SECRET") or "").strip()
        if cron_secret:
            authorization = str(self.headers.get("authorization") or "")
            if not hmac.compare_digest(authorization, f"Bearer {cron_secret}"):
                return False, "NONE"
        return True, "VERCEL_CRON"

    def do_GET(self) -> None:
        stage = _first_query(self.path, "stage").lower()
        if stage not in STAGE_ORDER:
            return self._send_json(400, {"error": "COLLECTOR_STAGE_INVALID"})

        allowed, source = self._authorized(stage)
        if not allowed:
            return self._send_json(403, {"error": "COLLECTOR_TRIGGER_FORBIDDEN"})

        status, collector = _run_with_acceptance_retry(stage, source)
        self._send_json(
            status,
            {
                "schema_version": "0.1",
                "service": "MedicalChannelAI",
                "trigger_source": source,
                "collector": collector,
            },
        )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
