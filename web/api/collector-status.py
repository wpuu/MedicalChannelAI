from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from vercel.functions import RuntimeCache

STATUS_KEY = "medicalchannelai:collector-workflow-status:v1"


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
            value = RuntimeCache().get(STATUS_KEY)
            if not isinstance(value, dict):
                value = {
                    "schema_version": "0.1",
                    "phase": "IDLE",
                    "triggered_at": None,
                    "run_id": None,
                    "updated_at": None,
                }
            self._send_json(
                200,
                {
                    "schema_version": "0.1",
                    "service": "MedicalChannelAI",
                    "collector": value,
                },
            )
        except Exception:
            self._send_json(503, {"error": "COLLECTOR_STATUS_UNAVAILABLE"})

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
