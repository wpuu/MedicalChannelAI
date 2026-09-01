from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = PROJECT_ROOT / 'pipeline'
sys.path.insert(0, str(PIPELINE_ROOT))
CROSS_RUNTIME_KEY = 'medicalchannelai-cross-runtime-v1'

try:
    from medical_channel_pipeline import build_public_snapshot
    from medical_channel_pipeline.validation import validate_record
    from vercel.functions import RuntimeCache

    _IMPORT_OK = callable(build_public_snapshot) and callable(validate_record)
    _DATA_OK = (PIPELINE_ROOT / 'data' / 'tianjin_query_plan.json').is_file()
    _CACHE_IMPORT_OK = True
except Exception:
    _IMPORT_OK = False
    _DATA_OK = False
    _CACHE_IMPORT_OK = False
    RuntimeCache = None  # type: ignore[assignment,misc]


def cache_roundtrip() -> bool:
    if not _CACHE_IMPORT_OK or RuntimeCache is None:
        return False
    try:
        cache = RuntimeCache(namespace='medicalchannelai-runtime')
        key = 'health-roundtrip-v1'
        value = {
            'schema_version': '0.1',
            'probe': 'pipeline-runtime',
            'written_at_epoch': int(time.time()),
        }
        cache.set(key, value, {'ttl': 3600, 'tags': ['medicalchannelai-runtime-health']})
        read_back = cache.get(key)
        return isinstance(read_back, dict) and read_back.get('probe') == value['probe']
    except Exception:
        return False


def write_cross_runtime_probe() -> bool:
    if not _CACHE_IMPORT_OK or RuntimeCache is None:
        return False
    try:
        cache = RuntimeCache()
        value = {
            'schema_version': '0.1',
            'probe': 'python-to-node-runtime-cache',
            'written_at_epoch': int(time.time()),
        }
        cache.set(CROSS_RUNTIME_KEY, value, {'ttl': 3600, 'tags': ['medicalchannelai-cross-runtime']})
        read_back = cache.get(CROSS_RUNTIME_KEY)
        return isinstance(read_back, dict) and read_back.get('probe') == value['probe']
    except Exception:
        return False


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
        cache_ok = cache_roundtrip()
        cross_runtime_written = write_cross_runtime_probe()
        ready = bool(_IMPORT_OK and _DATA_OK and cache_ok and cross_runtime_written)
        self._send_json(
            200 if ready else 503,
            {
                'schema_version': '0.1',
                'service': 'MedicalChannelAI',
                'pipeline_runtime': {
                    'available': ready,
                    'module_import': bool(_IMPORT_OK),
                    'data_bundle': bool(_DATA_OK),
                    'runtime_cache': cache_ok,
                    'cross_runtime_probe_written': cross_runtime_written,
                },
            },
        )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header('Allow', 'GET')
        self.end_headers()
