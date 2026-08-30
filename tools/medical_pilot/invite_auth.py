from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import secrets
import sqlite3
from typing import Protocol

from .today_actions_http import TrustedPrincipal


DEFAULT_INVITE_TTL_SECONDS = 30 * 60
MAX_INVITE_TTL_SECONDS = 24 * 60 * 60


class InviteStore(Protocol):
    def put_if_absent(
        self,
        *,
        code_hash: str,
        principal: TrustedPrincipal,
        created_at: datetime,
        expires_at: datetime,
    ) -> bool: ...

    def redeem(self, code_hash: str, *, now: datetime) -> TrustedPrincipal | None: ...


@dataclass(frozen=True)
class IssuedInvite:
    code: str
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


def _code_hash(code: str) -> str:
    if not isinstance(code, str) or len(code) < 32 or len(code) > 128:
        raise ValueError("invite code length is invalid")
    if any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in code):
        raise ValueError("invite code contains invalid characters")
    return hashlib.sha256(code.encode("ascii")).hexdigest()


def _validate_code_hash(code_hash: str) -> None:
    if not isinstance(code_hash, str) or len(code_hash) != 64:
        raise ValueError("invite code_hash must be lowercase sha256")
    if any(ch not in "0123456789abcdef" for ch in code_hash):
        raise ValueError("invite code_hash must be lowercase sha256")


def _utc_iso(value: datetime) -> str:
    _require_aware(value, "datetime")
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require_aware(parsed, "stored datetime")
    return parsed


class SQLiteInviteStore:
    """One-time, server-side Pilot invite store.

    Only the SHA-256 digest is persisted. A successful redemption is atomic and marks
    the invite consumed before a browser session is issued. This is a Pilot bootstrap
    mechanism, not a long-term multi-user identity provider.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_invites ("
                "code_hash TEXT PRIMARY KEY, "
                "tenant_id TEXT NOT NULL, "
                "profile_id TEXT NOT NULL, "
                "created_at TEXT NOT NULL, "
                "expires_at TEXT NOT NULL, "
                "redeemed_at TEXT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_medical_invites_principal "
                "ON medical_invites(tenant_id, profile_id, expires_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def put_if_absent(
        self,
        *,
        code_hash: str,
        principal: TrustedPrincipal,
        created_at: datetime,
        expires_at: datetime,
    ) -> bool:
        _validate_code_hash(code_hash)
        _validate_principal(principal)
        _require_aware(created_at, "created_at")
        _require_aware(expires_at, "expires_at")
        if expires_at <= created_at:
            raise ValueError("expires_at must be after created_at")
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO medical_invites("
                "code_hash, tenant_id, profile_id, created_at, expires_at, redeemed_at"
                ") VALUES (?, ?, ?, ?, ?, NULL)",
                (
                    code_hash,
                    principal.tenant_id,
                    principal.profile_id,
                    _utc_iso(created_at),
                    _utc_iso(expires_at),
                ),
            )
        return cursor.rowcount == 1

    def redeem(self, code_hash: str, *, now: datetime) -> TrustedPrincipal | None:
        _validate_code_hash(code_hash)
        _require_aware(now, "now")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT tenant_id, profile_id, expires_at, redeemed_at "
                "FROM medical_invites WHERE code_hash=?",
                (code_hash,),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return None
            tenant_id, profile_id, expires_at_raw, redeemed_at = row
            if redeemed_at is not None or now >= _parse_time(expires_at_raw):
                conn.execute("ROLLBACK")
                return None
            cursor = conn.execute(
                "UPDATE medical_invites SET redeemed_at=? "
                "WHERE code_hash=? AND redeemed_at IS NULL",
                (_utc_iso(now), code_hash),
            )
            if cursor.rowcount != 1:
                conn.execute("ROLLBACK")
                return None
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()
        principal = TrustedPrincipal(str(tenant_id), str(profile_id))
        _validate_principal(principal)
        return principal


def issue_invite(
    store: InviteStore,
    *,
    principal: TrustedPrincipal,
    now: datetime,
    ttl_seconds: int = DEFAULT_INVITE_TTL_SECONDS,
) -> IssuedInvite:
    _validate_principal(principal)
    _require_aware(now, "now")
    if ttl_seconds < 60 or ttl_seconds > MAX_INVITE_TTL_SECONDS:
        raise ValueError("invite ttl_seconds must be 60..86400")
    expires_at = now + timedelta(seconds=ttl_seconds)
    for _ in range(4):
        code = secrets.token_urlsafe(32)
        if store.put_if_absent(
            code_hash=_code_hash(code),
            principal=principal,
            created_at=now,
            expires_at=expires_at,
        ):
            return IssuedInvite(code=code, expires_at=expires_at)
    raise RuntimeError("unable to allocate unique invite code")


def redeem_invite(store: InviteStore, code: str, *, now: datetime) -> TrustedPrincipal | None:
    _require_aware(now, "now")
    try:
        code_hash = _code_hash(code)
    except ValueError:
        return None
    return store.redeem(code_hash, now=now)
