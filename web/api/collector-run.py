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

from collector_namespace import (
    ACTIVE_CYCLE_KEY,
    ACTIVE_CYCLE_TTL_SECONDS,
    META_KEY,
    QUEUE_TOPIC_NAME,
    active_cycle_id,
    cycle_has_running_stage,
)

CRON_SCHEDULE = "20 0 * * *"
SHANGHAI = ZoneInfo("Asia/Shanghai")
MESSAGE_RETENTION = timedelta(days=2)

# Temporary production acceptance probe. Remove after the v2 queue execution
# plane completes one verified end-to-end refresh in Production.
_ACCEPTANCE_PROBE = "mca-v030-q-8ab42d5f9c614e0baf2c7d1e9340f6a1"


class CollectorStartConflict(RuntimeError):
    pass


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


def _activate_cycle(
    cache: RuntimeCache,
    *,
    cycle_id: str,
    now: datetime,
    local_date: str,
    source: str,
) -> None:
    current_state = cache.get(META_KEY)
    if cycle_has_running_stage(current_state):
        raise CollectorStartConflict("COLLECTOR_CYCLE_ALREADY_RUNNING")

    if source == "ACCEPTANCE_PROBE":
        # Reset only v2 orchestration metadata. Canonical v2 state remains and
        # can be reconciled by the next verified run.
        cache.delete(META_KEY)

    active = {
        "schema_version": "0.1",
        "cycle_id": cycle_id,
        "cycle_as_of": now.isoformat(),
        "local_date": local_date,
        "trigger_source": source,
    }
    cache.set(
        ACTIVE_CYCLE_KEY,
        active,
        {"ttl": ACTIVE_CYCLE_TTL_SECONDS, "tags": ["medicalchannelai-collector-active-cycle"]},
    )
    read_back = cache.get(ACTIVE_CYCLE_KEY)
    if active_cycle_id(read_back) != cycle_id:
        raise RuntimeError("COLLECTOR_ACTIVE_CYCLE_READBACK_FAILED")


async def _enqueue_start(source: str) -> tuple[str, str, str]:
    now = datetime.now(timezone.utc)
    local_date = now.astimezone(SHANGHAI).date().isoformat()
    short_commit = str(os.environ.get("VERCEL_GIT_COMMIT_SHA") or "unknown")[:7]
    cycle_id = f"accept:{local_date}:{short_commit}" if source == "ACCEPTANCE_PROBE" else f"prod:{local_date}"

    cache = RuntimeCache()
    _activate_cycle(
        cache,
        cycle_id=cycle_id,
        now=now,
        local_date=local_date,
        source=source,
    )

    message_id = await send(
        QUEUE_TOPIC_NAME,
        {
            "schema_version": "0.1",
            "stage": "ccgp",
            "cycle_as_of": now.isoformat(),
            "cycle_id": cycle_id,
        },
        retention=MESSAGE_RETENTION,
        idempotency_key=f"{QUEUE_TOPIC_NAME}:{cycle_id}:ccgp",
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
        except CollectorStartConflict:
            return self._send_json(409, {"error": "COLLECTOR_CYCLE_ALREADY_RUNNING"})
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
                    "execution_plane": "VERCEL_QUEUE_V2",
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
