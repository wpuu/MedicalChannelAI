"""Small, strict sanitizer shared by runner and offline failure diagnostics."""
from __future__ import annotations

import re
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ALLOWED_STAGES = {'index_discovery', 'verified_detail'}
ALLOWED_CATEGORIES = {
    'ACCESS_DENIED', 'TRANSIENT_FETCH_ERROR', 'PERMANENT_HTTP_ERROR',
    'EVIDENCE_VALIDATION_FAILED', 'PARSER_REJECTED', 'UNEXPECTED_ERROR',
}
ALLOWED_HOSTS = {'tjmugh.com.cn', 'www.tjmugh.com.cn'}
SAFE_ERROR_CODES = {
    'TJMUGH_INDEX_HOST_REJECTED', 'TJMUGH_DETAIL_URL_ID_NOT_FOUND',
    'TJMUGH_NETWORK_ERROR',
    'TJMUGH_SOURCE_HOST_REJECTED', 'TJMUGH_TITLE_NOT_FOUND',
    'TJMUGH_PUBLISHED_DATE_NOT_FOUND', 'TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND',
    'TJMUGH_PROJECT_SECTION_NOT_FOUND', 'TJMUGH_PROJECT_ITEMS_NOT_FOUND',
    'TJMUGH_PROJECT_ITEMS_EMPTY', 'INVALID_DATE', 'INVALID_DATE_ONLY',
    'INVALID_DATE_TYPE', 'UNSUPPORTED_SOURCE_TYPE', 'SOURCE_URL_REQUIRED',
    'INVALID_SOURCE_URL', 'CCGP_HOST_MISMATCH', 'SOURCE_OBSERVED_AT_REQUIRED',
    'EVIDENCE_LIST_REQUIRED', 'EVIDENCE_ITEM_INVALID', 'EVIDENCE_FIELD_PATH_INVALID',
    'EVIDENCE_LOCATOR_REQUIRED', 'EVIDENCE_SOURCE_MISMATCH', 'DUPLICATE_EVIDENCE_PATH',
    'MARKET_CODE_INVALID', 'MARKET_NAME_MISMATCH', 'MARKET_ADMIN_CODE_MISMATCH',
    'SCHEMA_VERSION_UNSUPPORTED', 'OPPORTUNITY_ID_REQUIRED', 'SOURCE_REQUIRED',
    'FACTS_REQUIRED', 'REQUIRED_FACT_MISSING', 'REGISTRATION_DEADLINE_PRECISION_CONFLICT',
    'INVALID_BUDGET_CNY', 'UNSUPPORTED_CRITICAL_FACT', 'RECORD_LIST_REQUIRED',
    'DUPLICATE_OPPORTUNITY_ID', 'DUPLICATE_CANONICAL_OPPORTUNITY',
}
PUBLISH_GATE_REASONS = {
    'INDEX_DISCOVERY_FAILED', 'ALL_SELECTED_DETAILS_FAILED_VERIFICATION',
    'SELECTED_DETAILS_INCOMPLETE', 'PASS',
}
REFRESH_OUTCOMES = {
    'BLOCKED', 'NO_CANDIDATES_IN_WINDOW',
    'EXISTING_VERIFIED_COVERAGE_WITH_FAILURES', 'VERIFIED',
}
SAFE_ERROR_TYPES = {
    'RuntimeError', 'TjmughParseError', 'TjmughDiscoveryError', 'ValidationError',
    'ValueError', 'TimeoutError', 'OSError', 'URLError', 'HTTPError', 'Error',
}
_CODE = re.compile(r'^([A-Z][A-Z0-9_]{0,79})(?::|$)')


def safe_error_code(message: object) -> str:
    if not isinstance(message, str):
        return 'ERROR_CODE_UNAVAILABLE'
    match = _CODE.match(message)
    code = match.group(1) if match else ''
    if code in SAFE_ERROR_CODES and (message == code or message.startswith(code + ':')):
        return code
    if re.fullmatch(r'TJMUGH_HTTP_(\d{3})', code):
        status = int(code[-3:])
        if 100 <= status <= 599 and (message == code or message.startswith(code + ':')):
            return code
    return 'ERROR_CODE_UNAVAILABLE'


def safe_tjmugh_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        if parsed.port not in (None, 443):
            return None
        if parsed.path != '/cgxxtzgg/index.shtml' and not re.fullmatch(
            r'/system/20\d{2}/\d{2}/\d{2}/\d{1,20}\.shtml', parsed.path
        ):
            return None
        return urlunsplit(('https', parsed.hostname, parsed.path, '', ''))
    except ValueError:
        return None


def sanitize_failure(failure: object) -> dict[str, str]:
    """Return bounded, allowlisted diagnostic fields; never copy arbitrary text."""
    item = failure if isinstance(failure, dict) else {}
    stage = item.get('stage')
    category = item.get('category')
    error = item.get('error')
    safe = {
        'stage': stage if isinstance(stage, str) and stage in ALLOWED_STAGES else 'unknown',
        'category': category if isinstance(category, str) and category in ALLOWED_CATEGORIES else 'UNEXPECTED_ERROR',
        'error': error if isinstance(error, str) and error in SAFE_ERROR_TYPES else 'Error',
        'message': safe_error_code(item.get('message')),
    }
    published_at = item.get('published_at')
    if isinstance(published_at, str):
        try:
            parsed_date = date.fromisoformat(published_at)
            if parsed_date.isoformat() == published_at:
                safe['published_at'] = published_at
        except ValueError:
            pass
    url = safe_tjmugh_url(item.get('url'))
    if url:
        safe['url'] = url
    return safe


def write_json_atomic(path: Path, payload: object, *, max_bytes: int | None = None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    encoded = serialized.encode('utf-8')
    if max_bytes is not None and len(encoded) > max_bytes:
        raise ValueError('diagnostic output exceeds size limit')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='wb', dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp', delete=False,
        ) as temporary:
            temporary_path = temporary.name
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
