from __future__ import annotations

import asyncio
import hmac
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from vercel.functions import RuntimeCache

import backfill_runtime as runtime
from backfill_queue import enqueue_start

_ACCEPTANCE_PROBE = "JlVQZp2jBIqZPfipT4NVkLEVeGYwV04FZHtMPgNqn8Q"


def _safe_report(report: dict | None) -> dict | None:
    if not isinstance(report, dict):
        return None
    return {
        "schema_version": report.get("schema_version"),
        "mode": report.get("mode"),
        "cycle_id": report.get("cycle_id"),
        "as_of": report.get("as_of"),
        "base_record_count": report.get("base_record_count"),
        "discovery_query_count": report.get("discovery_query_count"),
        "discovery_success_count": report.get("discovery_success_count"),
        "unique_discovered_candidate_count": report.get("unique_discovered_candidate_count"),
        "new_verified_record_count": report.get("new_verified_record_count"),
        "merged_record_count": report.get("merged_record_count"),
        "event_watch_project_count": report.get("event_watch_project_count"),
        "new_notice_event_count": report.get("new_notice_event_count"),
        "failure_count": report.get("failure_count"),
        "candidate_public_opportunity_count": report.get("candidate_public_opportunity_count"),
        "candidate_opportunities": report.get("candidate_opportunities") or [],
        "acceptance_ready": bool(report.get("acceptance_ready")),
        "policy": report.get("policy") or {},
    }


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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        action = str((query.get("action") or ["status"])[0]).strip().lower()

        if action == "status":
            state = runtime.load_status()
            report = _safe_report(runtime.load_report())
            return self._send_json(
                200,
                {
                    "schema_version": "0.1",
                    "service": "MedicalChannelAI",
                    "execution_plane": "VERCEL_QUEUE_BACKFILL_V1",
                    "state": state,
                    "report": report,
                },
            )

        if action != "start":
            return self._send_json(400, {"error": "BACKFILL_ACTION_INVALID"})

        supplied = str((query.get("probe") or [""])[0])
        if not supplied or not hmac.compare_digest(supplied, _ACCEPTANCE_PROBE):
            return self._send_json(403, {"error": "BACKFILL_START_FORBIDDEN"})

        cache = RuntimeCache()
        now = datetime.now(timezone.utc)
        commit = str(os.environ.get("VERCEL_GIT_COMMIT_SHA") or "unknown")
        try:
            state = runtime.start_cycle(now=now, commit=commit, cache=cache)
            message_id = asyncio.run(enqueue_start(cycle_id=str(state["cycle_id"])))
        except runtime.BackfillConflict:
            return self._send_json(409, {"error": "BACKFILL_ALREADY_RUNNING"})
        except Exception as exc:
            runtime.mark_start_failed(f"{type(exc).__name__}:{str(exc)[:180]}", cache)
            return self._send_json(
                503,
                {
                    "error": "BACKFILL_START_FAILED",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:180],
                },
            )

        return self._send_json(
            202,
            {
                "schema_version": "0.1",
                "service": "MedicalChannelAI",
                "execution_plane": "VERCEL_QUEUE_BACKFILL_V1",
                "action": "QUEUED",
                "cycle_id": state["cycle_id"],
                "stage": "discover:0",
                "message_id": message_id,
                "publishes_public_snapshot": False,
            },
        )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
