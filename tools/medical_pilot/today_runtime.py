from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .agnes_dispatch_queue import SQLiteAgnesDispatchQueue
from .agnes_task_result import SQLiteAgnesTaskResultStore
from .auth_http import PilotAuthHttpTransport
from .followup_http import FollowupHttpTransport
from .followup_store import SQLiteFollowupStore
from .invite_auth import (
    IssuedInvite,
    SQLiteInviteStore,
    issue_invite,
    redeem_invite,
)
from .session_auth import (
    IssuedSession,
    OpaqueCookiePrincipalResolver,
    SQLiteSessionStore,
    issue_session,
)
from .today_actions_http import (
    RepositoryTodayActionsApplication,
    TodayActionsHttpTransport,
    TrustedPrincipal,
)
from .today_repo import SQLiteTodayActionsRepository


@dataclass
class SQLiteTodayRuntime:
    """Single-host Tianjin Pilot runtime binding.

    One SQLite file may safely host the Pilot public facts, tenant-private profile,
    follow-up, session/invite and Agnes tables because components use distinct table
    names plus WAL/busy timeout. This remains a single-host reference runtime and must
    not be copied to independent stateless serverless instances.
    """

    path: Path
    repository: SQLiteTodayActionsRepository
    invite_store: SQLiteInviteStore
    session_store: SQLiteSessionStore
    followup_store: SQLiteFollowupStore
    result_store: SQLiteAgnesTaskResultStore
    dispatch_queue: SQLiteAgnesDispatchQueue
    principal_resolver: OpaqueCookiePrincipalResolver
    application: RepositoryTodayActionsApplication
    transport: TodayActionsHttpTransport
    auth_transport: PilotAuthHttpTransport = field(init=False)
    followup_transport: FollowupHttpTransport = field(init=False)

    def __post_init__(self) -> None:
        self.auth_transport = PilotAuthHttpTransport(
            invite_session_issuer=self,
            session_store=self.session_store,
        )
        self.followup_transport = FollowupHttpTransport(
            principal_resolver=self.principal_resolver,
            repository=self.repository,
            store=self.followup_store,
        )

    def issue_profile_invite(
        self,
        *,
        principal: TrustedPrincipal,
        now: datetime,
        ttl_seconds: int | None = None,
    ) -> IssuedInvite:
        """Admin/bootstrap action: issue one invite only for an existing profile."""

        profile = self.repository.load_profile(principal.tenant_id, principal.profile_id)
        if profile is None:
            raise ValueError("cannot issue invite for unknown tenant/profile")
        kwargs = {}
        if ttl_seconds is not None:
            kwargs["ttl_seconds"] = ttl_seconds
        return issue_invite(
            self.invite_store,
            principal=principal,
            now=now,
            **kwargs,
        )

    def issue_authenticated_session(
        self,
        *,
        principal: TrustedPrincipal,
        now: datetime,
        ttl_seconds: int | None = None,
    ) -> IssuedSession:
        """Issue a browser session only after an upstream auth/admin check succeeds.

        This method is not an HTTP login endpoint and performs no credential check by
        itself. External adapters must never expose it directly to unauthenticated
        callers.
        """

        profile = self.repository.load_profile(principal.tenant_id, principal.profile_id)
        if profile is None:
            raise ValueError("cannot issue session for unknown tenant/profile")
        kwargs = {}
        if ttl_seconds is not None:
            kwargs["ttl_seconds"] = ttl_seconds
        return issue_session(
            self.session_store,
            principal=principal,
            now=now,
            **kwargs,
        )

    def redeem_invite_to_session(
        self,
        *,
        code: str,
        now: datetime,
        session_ttl_seconds: int | None = None,
    ) -> IssuedSession | None:
        """Redeem one valid invite and exchange it for one browser session."""

        principal = redeem_invite(self.invite_store, code, now=now)
        if principal is None:
            return None
        profile = self.repository.load_profile(principal.tenant_id, principal.profile_id)
        if profile is None:
            return None
        kwargs = {}
        if session_ttl_seconds is not None:
            kwargs["ttl_seconds"] = session_ttl_seconds
        return issue_session(
            self.session_store,
            principal=principal,
            now=now,
            **kwargs,
        )


def build_sqlite_today_runtime(
    path: Path,
    *,
    now_provider: Callable[[], datetime] | None = None,
) -> SQLiteTodayRuntime:
    path = Path(path)
    repository = SQLiteTodayActionsRepository(path)
    invite_store = SQLiteInviteStore(path)
    session_store = SQLiteSessionStore(path)
    followup_store = SQLiteFollowupStore(path)
    result_store = SQLiteAgnesTaskResultStore(path)
    dispatch_queue = SQLiteAgnesDispatchQueue(path)
    principal_resolver = OpaqueCookiePrincipalResolver(
        session_store,
        now_provider=now_provider,
    )
    application = RepositoryTodayActionsApplication(
        repository=repository,
        result_store=result_store,
        dispatch_queue=dispatch_queue,
    )
    transport = TodayActionsHttpTransport(
        principal_resolver=principal_resolver,
        application=application,
    )
    return SQLiteTodayRuntime(
        path=path,
        repository=repository,
        invite_store=invite_store,
        session_store=session_store,
        followup_store=followup_store,
        result_store=result_store,
        dispatch_queue=dispatch_queue,
        principal_resolver=principal_resolver,
        application=application,
        transport=transport,
    )
