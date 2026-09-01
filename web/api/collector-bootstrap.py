from __future__ import annotations

import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from vercel.functions import RuntimeCache

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SNAPSHOT = PROJECT_ROOT / 'public' / 'data' / 'today-actions.public.json'
LATEST_SNAPSHOT_KEY = 'medicalchannelai:verified-snapshot:latest:v1'
SNAPSHOT_TTL_SECONDS = 7 * 24 * 60 * 60


def parsed_as_of(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def bundled_snapshot() -> dict:
    payload = json.loads(BUNDLED_SNAPSHOT.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('BUNDLED_SNAPSHOT_INVALID')
    if payload.get('schema_version') != '0.1' or payload.get('mode') != 'TODAY_ACTIONS':
        raise ValueError('BUNDLED_SNAPSHOT_SCHEMA_INVALID')
    if parsed_as_of(payload.get('snapshot_as_of')) is None:
        raise ValueError('BUNDLED_SNAPSHOT_AS_OF_INVALID')
    return payload


def bootstrap_latest_snapshot() -> tuple[str, dict]:
    cache = RuntimeCache()
    bundled = bundled_snapshot()
    bundled_time = parsed_as_of(bundled.get('snapshot_as_of'))
    current = cache.get(LATEST_SNAPSHOT_KEY)
    if isinstance(current, dict):
        current_time = parsed_as_of(current.get('snapshot_as_of'))
        if current_time is not None and bundled_time is not None and current_time >= bundled_time:
            return 'KEPT_EXISTING', current

    cache.set(
        LATEST_SNAPSHOT_KEY,
        bundled,
        {
            'ttl': SNAPSHOT_TTL_SECONDS,
            'tags': ['medicalchannelai-verified-snapshot'],
            'name': 'MedicalChannelAI latest verified snapshot',
        },
    )
    read_back = cache.get(LATEST_SNAPSHOT_KEY)
    if not isinstance(read_back, dict) or read_back.get('snapshot_as_of') != bundled.get('snapshot_as_of'):
        raise RuntimeError('RUNTIME_SNAPSHOT_READBACK_FAILED')
    return 'BOOTSTRAPPED_BUNDLED', read_back


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
        try:
            action, snapshot = bootstrap_latest_snapshot()
            pool = snapshot.get('opportunity_pool')
            self._send_json(
                200,
                {
                    'schema_version': '0.1',
                    'service': 'MedicalChannelAI',
                    'bootstrap': {
                        'action': action,
                        'snapshot_as_of': snapshot.get('snapshot_as_of'),
                        'card_count': len(snapshot.get('cards') or []),
                        'opportunity_pool_count': len(pool) if isinstance(pool, list) else len(snapshot.get('cards') or []),
                    },
                },
            )
        except Exception:
            self._send_json(503, {'error': 'COLLECTOR_BOOTSTRAP_FAILED'})

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header('Allow', 'GET')
        self.end_headers()
