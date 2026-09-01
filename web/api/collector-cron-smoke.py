from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from vercel.functions import RuntimeCache

STATE_KEY = "medicalchannelai:collector-cron-smoke:v1"
STATE_TTL_SECONDS = 7 * 24 * 60 * 60
SHANGHAI = ZoneInfo("Asia/Shanghai")
ALLOWED_STAGES = {"a", "b"}
EXPECTED_SCHEDULES = {
    "a": "20 0 * * *",
    "b": "40 0 * * *",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _write(cache: RuntimeCache, value: dict) -> None:
    cache.set(
        STATE_KEY,
        value,
        {
            "ttl": STATE_TTL_SECONDS,
            "tags": ["medicalchannelai-collector-cron-smoke"],
        },
    )


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
        stage = (parse_qs(urlsplit(self.path).query).get("stage") or [""])[0].strip().lower()
        if stage not in ALLOWED_STAGES:
            return self._send_json(400, {"error": "COLLECTOR_STAGE_INVALID"})

        try:
            cache = RuntimeCache()
            now = _now_utc()
            now_iso = now.isoformat()
            local_date = now.astimezone(SHANGHAI).date().isoformat()
            schedule_header = str(self.headers.get("x-vercel-cron-schedule") or "").strip()
            invocation_source = (
                "VERCEL_CRON"
                if schedule_header == EXPECTED_SCHEDULES[stage]
                else "MANUAL_SMOKE"
            )

            existing = cache.get(STATE_KEY)
            state = existing if isinstance(existing, dict) else {}
            if state.get("local_date") != local_date:
                state = {
                    "schema_version": "0.1",
                    "local_date": local_date,
                    "stages": {},
                    "updated_at": now_iso,
                }
            stages = state.get("stages")
            stages = stages if isinstance(stages, dict) else {}
            previous = stages.get(stage)
            if isinstance(previous, dict) and previous.get("status") == "COMPLETED":
                return self._send_json(
                    200,
                    {
                        "schema_version": "0.1",
                        "service": "MedicalChannelAI",
                        "collector": {
                            "action": "ALREADY_COMPLETED_TODAY",
                            "local_date": local_date,
                            "stage": stage,
                            "status": "COMPLETED",
                            "first_completed_at": previous.get("first_completed_at"),
                        },
                    },
                )

            stages[stage] = {
                "status": "COMPLETED",
                "first_completed_at": now_iso,
                "source": invocation_source,
                "schedule": EXPECTED_SCHEDULES[stage],
            }
            state["schema_version"] = "0.1"
            state["local_date"] = local_date
            state["stages"] = stages
            state["updated_at"] = now_iso
            _write(cache, state)

            return self._send_json(
                200,
                {
                    "schema_version": "0.1",
                    "service": "MedicalChannelAI",
                    "collector": {
                        "action": "COMPLETED",
                        "local_date": local_date,
                        "stage": stage,
                        "status": "COMPLETED",
                        "source": invocation_source,
                    },
                },
            )
        except Exception:
            return self._send_json(503, {"error": "COLLECTOR_CRON_SMOKE_UNAVAILABLE"})

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
