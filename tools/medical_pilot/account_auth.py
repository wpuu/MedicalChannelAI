from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Mapping, Protocol

from .today_actions_http import TrustedPrincipal, TrustedPrincipalResolver


ACCOUNT_INVITED = "INVITED"
ACCOUNT_ACTIVE = "ACTIVE"
ACCOUNT_DISABLED = "DISABLED"
_ACCOUNT_STATUSES = {ACCOUNT_INVITED, ACCOUNT_ACTIVE, ACCOUNT_DISABLED}


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _required_text(value: str, name: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    result = value.strip()
    if len(result) > max_length:
        raise ValueError(f"{name} is too long")
    return result


def _validate_principal(principal: TrustedPrincipal) -> TrustedPrincipal:
    return TrustedPrincipal(
        _required_text(principal.tenant_id, "principal.tenant_id", max_length=128),
        _required_text(principal.profile_id, "principal.profile_id", max_length=160),
    )


def _utc_iso(value: datetime) -> str:
    _require_aware(value, "datetime")
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class PilotAccount:
    tenant_id: str
    profile_id: str
    company_name: str
    status: str
    created_at: str
    activated_at: str | None
    disabled_at: str | None
    last_login_at: str | None


class AccountStore(Protocol):
    def ensure_invited(
        self,
        *,
        principal: TrustedPrincipal,
        company_name: str,
        now: datetime,
    ) -> PilotAccount: ...

    def activate_login(self, principal: TrustedPrincipal, *, now: datetime) -> bool: ...

    def is_active(self, principal: TrustedPrincipal) -> bool: ...

    def set_disabled(self, principal: TrustedPrincipal, *, disabled: bool, now: datetime) -> bool: ...

    def get(self, principal: TrustedPrincipal) -> PilotAccount | None: ...


class SQLiteAccountStore:
    """Invite-only Pilot account lifecycle store.

    One Pilot account currently maps 1:1 to a tenant/profile. This is deliberate for the
    first customer trial: it gives us registration, activation, re-login and immediate
    disable semantics without introducing passwords/SMS/email infrastructure before the
    business model is validated. A later multi-user identity layer can map many users to
    one tenant without changing customer profiles or Today Actions.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_accounts ("
                "tenant_id TEXT NOT NULL, "
                "profile_id TEXT NOT NULL, "
                "company_name TEXT NOT NULL, "
                "status TEXT NOT NULL, "
                "created_at TEXT NOT NULL, "
                "activated_at TEXT NULL, "
                "disabled_at TEXT NULL, "
                "last_login_at TEXT NULL, "
                "PRIMARY KEY(tenant_id, profile_id))"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_medical_accounts_status "
                "ON medical_accounts(status, tenant_id, profile_id)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _row_to_account(row) -> PilotAccount:
        return PilotAccount(
            tenant_id=str(row[0]),
            profile_id=str(row[1]),
            company_name=str(row[2]),
            status=str(row[3]),
            created_at=str(row[4]),
            activated_at=None if row[5] is None else str(row[5]),
            disabled_at=None if row[6] is None else str(row[6]),
            last_login_at=None if row[7] is None else str(row[7]),
        )

    def get(self, principal: TrustedPrincipal) -> PilotAccount | None:
        principal = _validate_principal(principal)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT tenant_id, profile_id, company_name, status, created_at, "
                "activated_at, disabled_at, last_login_at "
                "FROM medical_accounts WHERE tenant_id=? AND profile_id=?",
                (principal.tenant_id, principal.profile_id),
            ).fetchone()
        if row is None:
            return None
        account = self._row_to_account(row)
        if account.status not in _ACCOUNT_STATUSES:
            raise RuntimeError("stored account status is invalid")
        return account

    def ensure_invited(
        self,
        *,
        principal: TrustedPrincipal,
        company_name: str,
        now: datetime,
    ) -> PilotAccount:
        principal = _validate_principal(principal)
        company_name = _required_text(company_name, "company_name", max_length=300)
        _require_aware(now, "now")
        created_at = _utc_iso(now)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO medical_accounts("
                "tenant_id, profile_id, company_name, status, created_at, activated_at, disabled_at, last_login_at"
                ") VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)",
                (
                    principal.tenant_id,
                    principal.profile_id,
                    company_name,
                    ACCOUNT_INVITED,
                    created_at,
                ),
            )
            conn.execute(
                "UPDATE medical_accounts SET company_name=? "
                "WHERE tenant_id=? AND profile_id=? AND status!=?",
                (company_name, principal.tenant_id, principal.profile_id, ACCOUNT_DISABLED),
            )
        account = self.get(principal)
        if account is None:
            raise RuntimeError("account provisioning did not persist")
        return account

    def activate_login(self, principal: TrustedPrincipal, *, now: datetime) -> bool:
        principal = _validate_principal(principal)
        _require_aware(now, "now")
        now_iso = _utc_iso(now)
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE medical_accounts SET "
                "status=?, activated_at=COALESCE(activated_at, ?), last_login_at=?, disabled_at=NULL "
                "WHERE tenant_id=? AND profile_id=? AND status IN (?, ?)",
                (
                    ACCOUNT_ACTIVE,
                    now_iso,
                    now_iso,
                    principal.tenant_id,
                    principal.profile_id,
                    ACCOUNT_INVITED,
                    ACCOUNT_ACTIVE,
                ),
            )
        return cursor.rowcount == 1

    def is_active(self, principal: TrustedPrincipal) -> bool:
        account = self.get(principal)
        return account is not None and account.status == ACCOUNT_ACTIVE

    def set_disabled(self, principal: TrustedPrincipal, *, disabled: bool, now: datetime) -> bool:
        principal = _validate_principal(principal)
        _require_aware(now, "now")
        account = self.get(principal)
        if account is None:
            return False
        now_iso = _utc_iso(now)
        if disabled:
            status = ACCOUNT_DISABLED
            disabled_at = now_iso
        else:
            status = ACCOUNT_ACTIVE if account.activated_at is not None else ACCOUNT_INVITED
            disabled_at = None
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE medical_accounts SET status=?, disabled_at=? "
                "WHERE tenant_id=? AND profile_id=?",
                (status, disabled_at, principal.tenant_id, principal.profile_id),
            )
        return cursor.rowcount == 1


class AccountAwarePrincipalResolver:
    """Reject sessions immediately when the Pilot account is not ACTIVE."""

    def __init__(self, base: TrustedPrincipalResolver, store: AccountStore) -> None:
        self._base = base
        self._store = store

    def resolve(self, headers: Mapping[str, str]) -> TrustedPrincipal | None:
        principal = self._base.resolve(headers)
        if principal is None:
            return None
        return principal if self._store.is_active(principal) else None
