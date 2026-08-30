from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import sqlite3
from pathlib import Path
from typing import Mapping, Protocol

from .today_actions_http import TrustedPrincipal


SESSION_COOKIE_NAME = "__Host-mcai_session"
MAX_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
DEFAULT_SESSION_TTL_SECONDS = MAX_SESSION_TTL_SECONDS


class SessionStore(Protocol):
    def put_if_absent(
        self,
        *,
        token_hash: str,
        principal: TrustedPrincipal,
        created_at: datetime,
        expires_at: datetime,
    ) -> bool: ...

    def get_active(self, token_hash: str, *, now: datetime) -> TrustedPrincipal | None: ...

    def revoke(self, token_hash: str, *, revoked_at: datetime) -> bool: ...

    def revoke_principal(self, principal: TrustedPrincipal, *, revoked_at: datetime) -> int: ...


@dataclass(frozen=True)
class IssuedSession:
    token: str
    set_cookie: str
    expires_at: datetime


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _validate_principal(principal: TrustedPrincipal) -> None:
    if not isinstance(principal.tenant_id, str) or not principal.tenant_id.strip():
        raise ValueError("principal.tenant_id is required")
    if not isinstance(principal.profile_id, str) or not principal.profile_id.strip():
        raise ValueError("principal.profile_id is required")
    if len(principal.tenant_id) > 128 or len(principal.profile_id) > 160:
        raise ValueError("principal identity is too long")


def _validate_token_hash(token_hash: str) -> None:
    if not isinstance(token_hash, str) or len(token_hash) != 64:
        raise ValueError("session token_hash must be lowercase sha256")
    if any(ch not in "0123456789abcdef" for ch in token_hash):
        raise ValueError("session token_hash must be lowercase sha256")


def _token_hash(token: str) -> str:
    if not isinstance(token, str) or len(token) < 32 or len(token) > 128:
        raise ValueError("session token length is invalid")
    if any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in token):
        raise ValueError("session token contains invalid characters")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _utc_iso(value: datetime) -> str:
    _require_aware(value, "datetime")
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require_aware(parsed, "stored datetime")
    return parsed


class MemorySessionStore:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[TrustedPrincipal, datetime, datetime, datetime | None]] = {}

    def put_if_absent(
        self,
        *,
        token_hash: str,
        principal: TrustedPrincipal,
        created_at: datetime,
        expires_at: datetime,
    ) -> bool:
        _validate_token_hash(token_hash)
        _validate_principal(principal)
        _require_aware(created_at, "created_at")
        _require_aware(expires_at, "expires_at")
        if expires_at <= created_at:
            raise ValueError("expires_at must be after created_at")
        if token_hash in self._rows:
            return False
        self._rows[token_hash] = (principal, created_at, expires_at, None)
        return True

    def get_active(self, token_hash: str, *, now: datetime) -> TrustedPrincipal | None:
        _validate_token_hash(token_hash)
        _require_aware(now, "now")
        row = self._rows.get(token_hash)
        if row is None:
            return None
        principal, _created_at, expires_at, revoked_at = row
        if revoked_at is not None or now >= expires_at:
            return None
        return principal

    def revoke(self, token_hash: str, *, revoked_at: datetime) -> bool:
        _validate_token_hash(token_hash)
        _require_aware(revoked_at, "revoked_at")
        row = self._rows.get(token_hash)
        if row is None:
            return False
        principal, created_at, expires_at, current_revoked = row
        if current_revoked is not None:
            return False
        self._rows[token_hash] = (principal, created_at, expires_at, revoked_at)
        return True

    def revoke_principal(self, principal: TrustedPrincipal, *, revoked_at: datetime) -> int:
        _validate_principal(principal)
        _require_aware(revoked_at, "revoked_at")
        count = 0
        for token_hash, row in list(self._rows.items()):
            row_principal, created_at, expires_at, current_revoked = row
            if row_principal != principal or current_revoked is not None:
                continue
            self._rows[token_hash] = (row_principal, created_at, expires_at, revoked_at)
            count += 1
        return count


class SQLiteSessionStore:
    """Single-host opaque session store.

    The browser receives only a random bearer token. The database stores only its
    SHA-256 digest plus trusted tenant/profile identity, so tenant/profile IDs are not
    encoded in a client-visible token. This reference store is suitable for one-host
    Pilot deployment; horizontal/serverless deployment needs a shared durable store.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_sessions ("
                "token_hash TEXT PRIMARY KEY, "
                "tenant_id TEXT NOT NULL, "
                "profile_id TEXT NOT NULL, "
                "created_at TEXT NOT NULL, "
                "expires_at TEXT NOT NULL, "
                "revoked_at TEXT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_medical_sessions_principal "
                "ON medical_sessions(tenant_id, profile_id, expires_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def put_if_absent(
        self,
        *,
        token_hash: str,
        principal: TrustedPrincipal,
        created_at: datetime,
        expires_at: datetime,
    ) -> bool:
        _validate_token_hash(token_hash)
        _validate_principal(principal)
        _require_aware(created_at, "created_at")
        _require_aware(expires_at, "expires_at")
        if expires_at <= created_at:
            raise ValueError("expires_at must be after created_at")
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO medical_sessions("
                "token_hash, tenant_id, profile_id, created_at, expires_at, revoked_at"
                ") VALUES (?, ?, ?, ?, ?, NULL)",
                (
                    token_hash,
                    principal.tenant_id,
                    principal.profile_id,
                    _utc_iso(created_at),
                    _utc_iso(expires_at),
                ),
            )
        return cursor.rowcount == 1

    def get_active(self, token_hash: str, *, now: datetime) -> TrustedPrincipal | None:
        _validate_token_hash(token_hash)
        _require_aware(now, "now")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT tenant_id, profile_id, expires_at, revoked_at "
                "FROM medical_sessions WHERE token_hash=?",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        tenant_id, profile_id, expires_at_raw, revoked_at = row
        if revoked_at is not None or now >= _parse_time(expires_at_raw):
            return None
        principal = TrustedPrincipal(str(tenant_id), str(profile_id))
        _validate_principal(principal)
        return principal

    def revoke(self, token_hash: str, *, revoked_at: datetime) -> bool:
        _validate_token_hash(token_hash)
        _require_aware(revoked_at, "revoked_at")
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE medical_sessions SET revoked_at=? "
                "WHERE token_hash=? AND revoked_at IS NULL",
                (_utc_iso(revoked_at), token_hash),
            )
        return cursor.rowcount == 1

    def revoke_principal(self, principal: TrustedPrincipal, *, revoked_at: datetime) -> int:
        _validate_principal(principal)
        _require_aware(revoked_at, "revoked_at")
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE medical_sessions SET revoked_at=? "
                "WHERE tenant_id=? AND profile_id=? AND revoked_at IS NULL",
                (_utc_iso(revoked_at), principal.tenant_id, principal.profile_id),
            )
        return int(cursor.rowcount)


def build_set_cookie(token: str, *, ttl_seconds: int) -> str:
    _token_hash(token)
    if ttl_seconds < 300 or ttl_seconds > MAX_SESSION_TTL_SECONDS:
        raise ValueError("session ttl_seconds must be 300..2592000")
    return (
        f"{SESSION_COOKIE_NAME}={token}; Path=/; Max-Age={ttl_seconds}; "
        "Secure; HttpOnly; SameSite=Strict"
    )


def build_clear_cookie() -> str:
    return (
        f"{SESSION_COOKIE_NAME}=; Path=/; Max-Age=0; "
        "Secure; HttpOnly; SameSite=Strict"
    )


def issue_session(
    store: SessionStore,
    *,
    principal: TrustedPrincipal,
    now: datetime,
    ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
) -> IssuedSession:
    _validate_principal(principal)
    _require_aware(now, "now")
    if ttl_seconds < 300 or ttl_seconds > MAX_SESSION_TTL_SECONDS:
        raise ValueError("session ttl_seconds must be 300..2592000")
    expires_at = now + timedelta(seconds=ttl_seconds)
    for _ in range(4):
        token = secrets.token_urlsafe(32)
        token_hash = _token_hash(token)
        if store.put_if_absent(
            token_hash=token_hash,
            principal=principal,
            created_at=now,
            expires_at=expires_at,
        ):
            return IssuedSession(
                token=token,
                set_cookie=build_set_cookie(token, ttl_seconds=ttl_seconds),
                expires_at=expires_at,
            )
    raise RuntimeError("unable to allocate unique session token")


def revoke_session(store: SessionStore, token: str, *, now: datetime) -> bool:
    _require_aware(now, "now")
    return store.revoke(_token_hash(token), revoked_at=now)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    matches = [value for key, value in headers.items() if key.lower() == wanted]
    if len(matches) != 1:
        return None
    return matches[0]


def _session_cookie_value(raw_cookie: str | None) -> str | None:
    if not raw_cookie:
        return None
    values: list[str] = []
    for part in raw_cookie.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == SESSION_COOKIE_NAME:
            values.append(value.strip())
    if len(values) != 1:
        return None
    token = values[0]
    try:
        _token_hash(token)
    except ValueError:
        return None
    return token


class OpaqueCookiePrincipalResolver:
    def __init__(self, store: SessionStore, *, now_provider=None) -> None:
        self._store = store
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def resolve(self, headers: Mapping[str, str]) -> TrustedPrincipal | None:
        token = _session_cookie_value(_header(headers, "Cookie"))
        if token is None:
            return None
        now = self._now_provider()
        _require_aware(now, "resolver now")
        return self._store.get_active(_token_hash(token), now=now)
