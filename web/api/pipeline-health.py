from __future__ import annotations

import json
import math
import os
import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = PROJECT_ROOT / 'pipeline'
MAX_VERIFIED_SNAPSHOT_AGE_SECONDS = 30 * 60 * 60
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PIPELINE_ROOT))

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


class _NoStatusRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def served_snapshot_health() -> dict[str, Any]:
    """Read the same deployment's serving decision, never a collector candidate.

    status.js uses the application's verified-snapshot loader. Looking directly
    at latest/candidate cache entries or choosing the newest timestamp here can
    report a healthy product while its durable publish/readback failed.
    """
    unavailable = {
        'available': False, 'fresh': False, 'degraded': True,
        'source': None, 'age_seconds': None, 'freshness': 'UNAVAILABLE',
        'source_health': {'status': 'UNKNOWN'},
    }
    host = str(
        os.environ.get('VERCEL_URL')
        or (os.environ.get('VERCEL_PROJECT_PRODUCTION_URL')
            if str(os.environ.get('VERCEL_ENV') or '').strip().lower() == 'production' else '')
    ).strip()
    if not host:
        return unavailable
    preview = str(os.environ.get('VERCEL_ENV') or '').strip().lower() == 'preview'
    if preview and (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*\.vercel\.app', host)
                    or host.lower() == 'medicalchannelai.vercel.app'):
        return unavailable
    origin = host if host.startswith(('https://', 'http://')) else f'https://{host}'
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'MedicalChannelAI-PipelineHealth/0.1',
    }
    if preview:
        oidc_token = str(os.environ.get('VERCEL_OIDC_TOKEN') or '').strip()
        if oidc_token:
            headers['x-vercel-trusted-oidc-idp-token'] = oidc_token
    request = Request(
        f"{origin.rstrip('/')}/api/status",
        headers=headers,
        method='GET',
    )
    try:
        with build_opener(_NoStatusRedirect()).open(request, timeout=5) as response:
            if int(getattr(response, 'status', 0) or 0) != 200:
                return unavailable
            payload = json.loads(response.read(256 * 1024).decode('utf-8'))
    except Exception:
        return unavailable
    snapshot = payload.get('snapshot') if isinstance(payload, dict) and payload.get('service') == 'MedicalChannelAI' else None
    if not isinstance(snapshot, dict):
        return unavailable
    source_health = snapshot.get('source_health')
    source_health = source_health if isinstance(source_health, dict) else {'status': 'UNKNOWN'}
    age_minutes = snapshot.get('age_minutes')
    valid_age = (isinstance(age_minutes, (int, float)) and not isinstance(age_minutes, bool)
                 and math.isfinite(age_minutes) and age_minutes >= 0)
    available = payload.get('ready') is True and snapshot.get('available') is True
    fresh = (
        available and snapshot.get('freshness') == 'FRESH'
        and valid_age and age_minutes * 60 <= MAX_VERIFIED_SNAPSHOT_AGE_SECONDS
        and source_health.get('status') == 'HEALTHY' and payload.get('degraded') is False
    )
    return {
        'available': available, 'fresh': fresh, 'degraded': not fresh,
        'source': snapshot.get('source_mode'),
        'age_seconds': int(age_minutes * 60) if valid_age else None,
        'freshness': snapshot.get('freshness') or 'UNAVAILABLE',
        'source_health': source_health,
    }


def verified_snapshot_freshness() -> tuple[bool, str | None, int | None]:
    health = served_snapshot_health()
    return health['fresh'], health['source'], health['age_seconds']


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
        snapshot = served_snapshot_health()
        ready = bool(_IMPORT_OK and _DATA_OK and cache_ok and cron_ready and snapshot['available'])
        self._send_json(
            200 if ready else 503,
            {
                'schema_version': '0.1',
                'service': 'MedicalChannelAI',
                'ready': ready,
                'degraded': not ready or snapshot['degraded'],
                'pipeline_runtime': {
                    'available': ready,
                    'module_import': bool(_IMPORT_OK),
                    'data_bundle': bool(_DATA_OK),
                    'runtime_cache': cache_ok,
                    'cron_secret_configured': cron_secret_configured,
                    'cron_secret_required': production_mode,
                    'verified_snapshot_available': snapshot['available'],
                    'verified_snapshot_fresh': snapshot['fresh'],
                    'verified_snapshot_freshness_required': production_mode,
                    'verified_snapshot_source': snapshot['source'],
                    'verified_snapshot_age_seconds': snapshot['age_seconds'],
                    'verified_snapshot_freshness': snapshot['freshness'],
                    'source_health': snapshot['source_health'],
                    'verified_snapshot_max_age_seconds': MAX_VERIFIED_SNAPSHOT_AGE_SECONDS,
                },
            },
        )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header('Allow', 'GET')
        self.end_headers()
