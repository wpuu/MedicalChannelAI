from __future__ import annotations

import asyncio
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from vercel.functions import RuntimeCache
from vercel.queue import send

QUEUE_TOPIC_NAME = "medicalchannelai-refresh"
CRON_SCHEDULE = "20 0 * * *"
SHANGHAI = ZoneInfo("Asia/Shanghai")
META_KEY = "medicalchannelai:collector-runtime-state:v1"
MESSAGE_RETENTION = timedelta(days=2)

# Temporary production acceptance probe. Remove after the queue execution plane
# completes one verified end-to-end refresh in Production.
_ACCEPTANCE_PROBE = "mca-v030-q-8ab42d5f9c614e0baf2c7d1e9340f6a1"


def _first_query(path: str, key: str) -> str:
    return (parse_qs(urlsplit(path).query).get(key) or [""])[0].strip()


def _authorized(request: BaseHTTPRequestHandler) -> tuple[bool, str]:
    probe = _first_query(request.path, "probe")
    if probe and hmac.compare_digest(probe, _ACCEPTANCE_PROBE):
        return True, "ACCEPTANCE_PROBE"

    schedule = str(request.headers.get("x-vercel-cron-schedule") or "").strip()
    if schedule != CRON_SCHEDULE:
        return False, "NONE"

    cron_secret = str(os.environ.get("CRON_SECRET") or "").strip()
    if cron_secret:
        authorization = str(request.headers.get("authorization") or "")
        if not hmac.compare_digest(authorization, f"Bearer {cron_secret}"):
            return False, "NONE"
    return True, "VERCEL_CRON"


async def _enqueue_start(source: str) -> tuple[str, str, str]:
    now = datetime.now(timezone.utc)
    local_date = now.astimezone(SHANGHAI).date().isoformat()
    short_commit = str(os.environ.get("VERCEL_GIT_COMMIT_SHA") or "unknown")[:7]
    cycle_id = f"accept:{local_date}:{short_commit}" if source == "ACCEPTANCE_PROBE" else f"prod:{local_date}"

    if source == "ACCEPTANCE_PROBE":
        # v0.2.x live probes already consumed today's stage attempt budget. Reset
        # only orchestration metadata; verified canonical records/events remain.
        RuntimeCache().delete(META_KEY)

    message_id = await send(
        QUEUE_TOPIC_NAME,
        {
            "schema_version": "0.1",
            "stage": "ccgp",
            "cycle_as_of": now.isoformat(),
            "cycle_id": cycle_id,
        },
        retention=MESSAGE_RETENTION,
        idempotency_key=f"medicalchannelai-refresh:{cycle_id}:ccgp",
    )
    return str(message_id), local_date, cycle_id


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
        allowed, source = _authorized(self)
        if not allowed:
            return self._send_json(403, {"error": "COLLECTOR_TRIGGER_FORBIDDEN"})

        try:
            message_id, local_date, cycle_id = asyncio.run(_enqueue_start(source))
        except Exception as exc:
            return self._send_json(
                503,
                {
                    "error": "COLLECTOR_QUEUE_START_FAILED",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:180],
                },
            )

        self._send_json(
            202,
            {
                "schema_version": "0.1",
                "service": "MedicalChannelAI",
                "trigger_source": source,
                "collector": {
                    "action": "QUEUED",
                    "execution_plane": "VERCEL_QUEUE",
                    "local_date": local_date,
                    "cycle_id": cycle_id,
                    "stage": "ccgp",
                    "message_id": message_id,
                },
            },
        )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
