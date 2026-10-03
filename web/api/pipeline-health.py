from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = PROJECT_ROOT / 'pipeline'
BUNDLED_SNAPSHOT_PATH = PROJECT_ROOT / 'public' / 'data' / 'today-actions.public.json'
MAX_VERIFIED_SNAPSHOT_AGE_SECONDS = 30 * 60 * 60
MAX_FUTURE_SNAPSHOT_SKEW_SECONDS = 15 * 60
SAFE_SOURCE_ID = re.compile(r"^(?:[a-zA-Z0-9_.-]{1,80}|[a-zA-Z0-9_.-]{1,77}:[a-z]{2})$")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PIPELINE_ROOT))

try:
    from collector_namespace import LATEST_RUNTIME_SNAPSHOT_KEY, META_KEY
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
    META_KEY = 'medicalchannelai:collector-runtime-state:v2'


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


def _parse_snapshot_timestamp(value: Any) -> datetime | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _valid_source_ids(value: Any) -> bool:
    return isinstance(value, list) and len(value) <= 20 and all(
        isinstance(item, str) and SAFE_SOURCE_ID.fullmatch(item) for item in value
    )


def _snapshot_coverage(value: Any) -> tuple[bool | None, datetime | None, str | None]:
    if not isinstance(value, dict):
        return None, None, 'SNAPSHOT_INVALID'
    coverage = value.get('collection_coverage')
    if not isinstance(coverage, dict):
        return None, None, 'COLLECTION_COVERAGE_UNKNOWN'
    complete = coverage.get('complete')
    if type(complete) is not bool:
        return None, None, 'COLLECTION_COVERAGE_INVALID'
    revision = _parse_snapshot_timestamp(value.get('snapshot_as_of'))
    raw_anchor = coverage.get('last_complete_as_of')
    anchor = _parse_snapshot_timestamp(raw_anchor)
    if raw_anchor is not None and anchor is None:
        return complete, None, 'SNAPSHOT_TIME_INVALID'
    failures = coverage.get('failed_source_ids')
    updated = coverage.get('updated_source_ids')
    if revision is None:
        return complete, None, 'SNAPSHOT_TIME_INVALID'
    if not _valid_source_ids(failures) or not _valid_source_ids(updated):
        return complete, None, 'COLLECTION_COVERAGE_INVALID'
    if complete:
        if anchor is None or anchor != revision or failures:
            return complete, None, 'COLLECTION_COVERAGE_INVALID'
        return True, revision, None
    if anchor is not None and anchor > revision:
        return False, None, 'COLLECTION_COVERAGE_INVALID'
    return False, anchor, 'COLLECTION_COVERAGE_PARTIAL'


def _snapshot_time(value: Any) -> datetime | None:
    """Return the represented full or last-complete coverage clock, if valid."""
    _, snapshot_time, _ = _snapshot_coverage(value)
    return snapshot_time


def _snapshot_freshness(value: Any, now: datetime) -> tuple[bool, int | None, str | None]:
    complete, snapshot_time, coverage_reason = _snapshot_coverage(value)
    revision = _parse_snapshot_timestamp(value.get('snapshot_as_of')) if isinstance(value, dict) else None
    if revision is not None and (revision - now).total_seconds() > MAX_FUTURE_SNAPSHOT_SKEW_SECONDS:
        return False, None, 'SNAPSHOT_FUTURE'
    if snapshot_time is None:
        return False, None, coverage_reason or 'SNAPSHOT_TIME_INVALID'
    raw_age = (now - snapshot_time).total_seconds()
    if raw_age < -MAX_FUTURE_SNAPSHOT_SKEW_SECONDS:
        return False, int(raw_age), 'SNAPSHOT_FUTURE'
    age_seconds = max(0, int(raw_age))
    if complete is not True:
        return False, age_seconds, coverage_reason or 'COLLECTION_COVERAGE_PARTIAL'
    if age_seconds > MAX_VERIFIED_SNAPSHOT_AGE_SECONDS:
        return False, age_seconds, 'SNAPSHOT_STALE'
    return True, age_seconds, None


def _bundled_snapshot() -> dict[str, Any] | None:
    try:
        value = json.loads(BUNDLED_SNAPSHOT_PATH.read_text(encoding='utf-8'))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _bundle_diagnostic(now: datetime) -> tuple[str, int | None]:
    """Report a bundled snapshot clock on degraded paths without treating it as readiness proof."""
    bundled = _bundled_snapshot()
    _, age_seconds, _ = _snapshot_freshness(bundled, now)
    return ('BUNDLED_SNAPSHOT' if bundled is not None else 'RUNTIME_CACHE_V2', age_seconds)


def _durable_status_is_configured() -> bool:
    return bool(str(os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL') or '').strip())


def _durable_status_snapshot(now: datetime) -> tuple[bool, datetime | None, int | None, str | None]:
    """Read the authoritative production status when durable storage is configured."""
    if not _durable_status_is_configured():
        return False, None, None, None
    host = str(
        os.environ.get('VERCEL_PROJECT_PRODUCTION_URL')
        or os.environ.get('VERCEL_URL')
        or ('medicalchannelai.vercel.app' if str(os.environ.get('VERCEL_ENV') or '').lower() == 'production' else '')
    ).strip()
    if not host:
        return True, None, None, 'DATABASE_STATUS_UNAVAILABLE'
    origin = host if host.startswith(('https://', 'http://')) else f'https://{host}'
    request = Request(
        f"{origin.rstrip('/')}/api/status",
        headers={
            'Accept': 'application/json',
            'User-Agent': 'MedicalChannelAI-PipelineHealth/0.1',
        },
        method='GET',
    )
    try:
        with urlopen(request, timeout=5) as response:
            if int(getattr(response, 'status', 0) or 0) != 200:
                return True, None, None, 'DATABASE_STATUS_UNAVAILABLE'
            payload = json.loads(response.read().decode('utf-8'))
    except Exception:
        return True, None, None, 'DATABASE_STATUS_UNAVAILABLE'
    if not isinstance(payload, dict) or payload.get('ready') is not True:
        return True, None, None, 'DATABASE_STATUS_NOT_READY'
    if payload.get('degraded') is True:
        return True, None, None, 'DATABASE_STATUS_DEGRADED'
    if payload.get('degraded') is not False:
        return True, None, None, 'DATABASE_STATUS_INVALID'
    collection = payload.get('collection')
    if (not isinstance(collection, dict) or collection.get('available') is not True
            or collection.get('outcome') != 'COMPLETED' or collection.get('failures') != []):
        return True, None, None, 'COLLECTION_STATUS_INCOMPLETE'
    snapshot = payload.get('snapshot') if isinstance(payload, dict) else None
    if not isinstance(snapshot, dict):
        return True, None, None, 'DATABASE_STATUS_NOT_READY'
    if snapshot.get('available') is not True:
        return True, None, None, 'DATABASE_STATUS_NOT_READY'
    if snapshot.get('degraded') is True:
        return True, None, None, 'DATABASE_STATUS_DEGRADED'
    if snapshot.get('degraded') is not False:
        return True, None, None, 'DATABASE_STATUS_INVALID'
    if snapshot.get('source_mode') != 'DATABASE' or snapshot.get('freshness') != 'FRESH':
        return True, None, None, 'DATABASE_SNAPSHOT_NOT_FRESH'
    fresh, age_seconds, reason = _snapshot_freshness(snapshot, now)
    if not fresh:
        return True, None, age_seconds, reason or 'DATABASE_SNAPSHOT_NOT_FRESH'
    return True, _snapshot_time(snapshot), age_seconds, None


def _collection_state_reason(value: Any) -> str | None:
    if not isinstance(value, dict) or not isinstance(value.get('stages'), dict) or not value['stages']:
        return 'COLLECTION_STATE_UNKNOWN'
    stages = value['stages']
    statuses = [item.get('status') for item in stages.values() if isinstance(item, dict)]
    if len(statuses) != len(stages) or any(not isinstance(status, str) for status in statuses):
        return 'COLLECTION_STATE_UNKNOWN'
    if any(status not in {'COMPLETED', 'RUNNING', 'FAILED', 'BLOCKED'} for status in statuses):
        return 'COLLECTION_STATE_UNKNOWN'
    if any(status in {'FAILED', 'BLOCKED'} for status in statuses):
        return 'COLLECTION_STATE_DEGRADED'
    if any(status != 'COMPLETED' for status in statuses):
        return 'COLLECTION_STATE_INCOMPLETE'
    publish = stages.get('publish')
    if not isinstance(publish, dict) or publish.get('terminal') is not True:
        return 'COLLECTION_STATE_INCOMPLETE'
    return None


def _verified_snapshot_health() -> tuple[bool, str | None, int | None, str | None]:
    now = datetime.now(timezone.utc)
    database_configured, durable_time, durable_age, durable_reason = _durable_status_snapshot(now)
    if database_configured:
        if durable_reason:
            return False, 'DATABASE_STATUS', durable_age, durable_reason
        if durable_time is None:
            return False, 'DATABASE_STATUS', None, 'DATABASE_STATUS_UNAVAILABLE'
        return True, 'DATABASE_STATUS', durable_age, None

    if not _CACHE_IMPORT_OK or RuntimeCache is None:
        source, age_seconds = _bundle_diagnostic(now)
        return False, source, age_seconds, 'COLLECTION_STATE_UNKNOWN'
    try:
        cache = RuntimeCache()
        runtime_value = cache.get(LATEST_RUNTIME_SNAPSHOT_KEY)
        collection_state = cache.get(META_KEY)
    except Exception:
        source, age_seconds = _bundle_diagnostic(now)
        return False, source, age_seconds, 'RUNTIME_CACHE_UNAVAILABLE'
    state_reason = _collection_state_reason(collection_state)
    if state_reason:
        source, age_seconds = _bundle_diagnostic(now)
        return False, source, age_seconds, state_reason
    if runtime_value is None:
        source, age_seconds = _bundle_diagnostic(now)
        return False, source, age_seconds, 'RUNTIME_SNAPSHOT_MISSING'
    fresh, age_seconds, reason = _snapshot_freshness(runtime_value, now)
    if not fresh:
        return False, 'RUNTIME_CACHE_V2', age_seconds, reason
    return True, 'RUNTIME_CACHE_V2', age_seconds, None


def verified_snapshot_freshness() -> tuple[bool, str | None, int | None]:
    fresh, source, age_seconds, _ = _verified_snapshot_health()
    return fresh, source, age_seconds


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
        snapshot_fresh, snapshot_source, snapshot_age_seconds, snapshot_health_reason = _verified_snapshot_health()
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
                    'verified_snapshot_clock_skew_seconds': MAX_FUTURE_SNAPSHOT_SKEW_SECONDS,
                    'verified_snapshot_health_reason': snapshot_health_reason,
                },
            },
        )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header('Allow', 'GET')
        self.end_headers()
