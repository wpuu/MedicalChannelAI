from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from collector_runtime import STAGE_ORDER, load_status


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
            state = load_status()
            stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
            completed = sum(
                1
                for stage in STAGE_ORDER
                if isinstance(stages.get(stage), dict) and stages[stage].get("status") == "COMPLETED"
            )
            self._send_json(
                200,
                {
                    "schema_version": "0.1",
                    "service": "MedicalChannelAI",
                    "collector": {
                        **state,
                        "stage_order": list(STAGE_ORDER),
                        "completed_stage_count": completed,
                        "total_stage_count": len(STAGE_ORDER),
                    },
                },
            )
        except Exception:
            self._send_json(503, {"error": "COLLECTOR_STATUS_UNAVAILABLE"})

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
