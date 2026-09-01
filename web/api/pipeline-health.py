from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = PROJECT_ROOT / 'pipeline'
sys.path.insert(0, str(PIPELINE_ROOT))

try:
    from medical_channel_pipeline import build_public_snapshot
    from medical_channel_pipeline.validation import validate_record

    _IMPORT_OK = callable(build_public_snapshot) and callable(validate_record)
    _DATA_OK = (PIPELINE_ROOT / 'data' / 'tianjin_query_plan.json').is_file()
except Exception:
    _IMPORT_OK = False
    _DATA_OK = False


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        ready = bool(_IMPORT_OK and _DATA_OK)
        self._send_json(
            200 if ready else 503,
            {
                'schema_version': '0.1',
                'service': 'MedicalChannelAI',
                'pipeline_runtime': {
                    'available': ready,
                    'module_import': bool(_IMPORT_OK),
                    'data_bundle': bool(_DATA_OK),
                },
            },
        )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header('Allow', 'GET')
        self.end_headers()
