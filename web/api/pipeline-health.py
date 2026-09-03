from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = PROJECT_ROOT / 'pipeline'
BUNDLED_SNAPSHOT_PATH = PROJECT_ROOT / 'public' / 'data' / 'today-actions.public.json'
MAX_VERIFIED_SNAPSHOT_AGE_SECONDS = 36 * 60 * 60
sys.path.insert(0, str(PIPELINE_ROOT))

try:
    from collector_namespace import LATEST_RUNTIME_SNAPSHOT_KEY
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
    LATEST_RUNTIME_SNAPSHOT_KEY = 'medicalchannelai:verified-snapshot:latest:v2'


def cache_roundtrip() -> bool:
    if not _CACHE_IMPORT_OK or RuntimeCache is None:
        return False
    try:
        cache = RuntimeCache(namespace='medicalchannelai-runtime')
        key = 'health-roundtrip-v1'
        value = {'schema_version': '0.1', 'probe': 'pipeline-runtime'}
        cache.set(key, value, {'ttl': 3600, 'tags': ['medicalchannelai-runtime-health']})
        read_back = cache.get(key)
        return isinstance(read_back, dict) and read_back.get('probe') == value['probe']
    except Exception:
        return False


def cron_secret_state() -> tuple[bool, bool]:
    configured = bool(str(os.environ.get('CRON_SECRET') or '').strip())
    required = str(os.environ.get('VERCEL_ENV') or '').strip().lower() == 'production'
    return configured, required


def _snapshot_time(value: Any) -> datetime | None:
    if not isinstance(value, dict):
        return None
    raw = str(value.get('snapshot_as_of') or '').strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _bundled_snapshot() -> dict[str, Any] | None:
    try:
        value = json.loads(BUNDLED_SNAPSHOT_PATH.read_text(encoding='utf-8'))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def verified_snapshot_freshness() -> tuple[bool, str | None, int | None]:
    candidates: list[tuple[str, datetime]] = []
    if _CACHE_IMPORT_OK and RuntimeCache is not None:
        try:
            runtime_value = RuntimeCache().get(LATEST_RUNTIME_SNAPSHOT_KEY)
            runtime_time = _snapshot_time(runtime_value)
            if runtime_time is not None:
                candidates.append(('RUNTIME_CACHE_V2', runtime_time))
        except Exception:
            pass

    bundled_time = _snapshot_time(_bundled_snapshot())
    if bundled_time is not None:
        candidates.append(('BUNDLED_SNAPSHOT', bundled_time))

    if not candidates:
        return False, None, None

    source, latest = max(candidates, key=lambda item: item[1])
    age_seconds = max(0, int((datetime.now(timezone.utc) - latest).total_seconds()))
    return age_seconds <= MAX_VERIFIED_SNAPSHOT_AGE_SECONDS, source, age_seconds


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
        cron_secret_configured, production_mode = cron_secret_state()
        cron_ready = cron_secret_configured or not production_mode
        snapshot_fresh, snapshot_source, snapshot_age_seconds = verified_snapshot_freshness()
        snapshot_ready = snapshot_fresh or not production_mode
        ready = bool(_IMPORT_OK and _DATA_OK and cache_ok and cron_ready and snapshot_ready)
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
                    'cron_secret_configured': cron_secret_configured,
                    'cron_secret_required': production_mode,
                    'verified_snapshot_fresh': snapshot_fresh,
                    'verified_snapshot_freshness_required': production_mode,
                    'verified_snapshot_source': snapshot_source,
                    'verified_snapshot_age_seconds': snapshot_age_seconds,
                    'verified_snapshot_max_age_seconds': MAX_VERIFIED_SNAPSHOT_AGE_SECONDS,
                },
            },
        )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header('Allow', 'GET')
        self.end_headers()
