from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo

from vercel.functions import RuntimeCache
from vercel.workflow import start

from collector_workflow import tianjin_refresh_workflow

STATUS_KEY = "medicalchannelai:collector-workflow-status:v1"
TRIGGER_KEY_PREFIX = "medicalchannelai:collector-trigger:v1:"
STATUS_TTL_SECONDS = 7 * 24 * 60 * 60
TRIGGER_TTL_SECONDS = 2 * 24 * 60 * 60
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cache_set(cache: RuntimeCache, key: str, value: dict, ttl: int, tag: str) -> None:
    cache.set(key, value, {"ttl": ttl, "tags": [tag]})


async def _start_refresh() -> tuple[int, dict]:
    cache = RuntimeCache()
    now = _now_utc()
    triggered_at = now.isoformat()
    local_date = now.astimezone(SHANGHAI).date().isoformat()
    trigger_key = f"{TRIGGER_KEY_PREFIX}{local_date}"

    existing = cache.get(trigger_key)
    status = cache.get(STATUS_KEY)
    if isinstance(existing, dict) and existing.get("run_id"):
        return 200, {
            "schema_version": "0.1",
            "service": "MedicalChannelAI",
            "collector": {
                "action": "ALREADY_STARTED_TODAY",
                "run_id": existing.get("run_id"),
                "triggered_at": existing.get("triggered_at"),
                "phase": status.get("phase") if isinstance(status, dict) else None,
            },
        }

    _cache_set(
        cache,
        trigger_key,
        {"schema_version": "0.1", "run_id": None, "triggered_at": triggered_at},
        TRIGGER_TTL_SECONDS,
        "medicalchannelai-collector-trigger",
    )
    _cache_set(
        cache,
        STATUS_KEY,
        {
            "schema_version": "0.1",
            "phase": "STARTING",
            "triggered_at": triggered_at,
            "run_id": None,
            "updated_at": triggered_at,
        },
        STATUS_TTL_SECONDS,
        "medicalchannelai-collector-workflow",
    )

    try:
        run = await start(tianjin_refresh_workflow, triggered_at)
    except Exception:
        cache.delete(trigger_key)
        _cache_set(
            cache,
            STATUS_KEY,
            {
                "schema_version": "0.1",
                "phase": "START_FAILED",
                "triggered_at": triggered_at,
                "run_id": None,
                "updated_at": _now_utc().isoformat(),
            },
            STATUS_TTL_SECONDS,
            "medicalchannelai-collector-workflow",
        )
        return 503, {"error": "COLLECTOR_WORKFLOW_START_FAILED"}

    run_id = run.run_id
    _cache_set(
        cache,
        trigger_key,
        {"schema_version": "0.1", "run_id": run_id, "triggered_at": triggered_at},
        TRIGGER_TTL_SECONDS,
        "medicalchannelai-collector-trigger",
    )

    current = cache.get(STATUS_KEY)
    current = current if isinstance(current, dict) else {}
    phase = current.get("phase") if current.get("triggered_at") == triggered_at else "STARTED"
    if phase == "STARTING":
        phase = "STARTED"
    _cache_set(
        cache,
        STATUS_KEY,
        {
            "schema_version": "0.1",
            "phase": phase,
            "triggered_at": triggered_at,
            "run_id": run_id,
            "updated_at": _now_utc().isoformat(),
        },
        STATUS_TTL_SECONDS,
        "medicalchannelai-collector-workflow",
    )

    return 202, {
        "schema_version": "0.1",
        "service": "MedicalChannelAI",
        "collector": {
            "action": "STARTED",
            "run_id": run_id,
            "triggered_at": triggered_at,
            "phase": phase,
        },
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
        try:
            status, payload = asyncio.run(_start_refresh())
            self._send_json(status, payload)
        except Exception:
            self._send_json(503, {"error": "COLLECTOR_TRIGGER_UNAVAILABLE"})

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
