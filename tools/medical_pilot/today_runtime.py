from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .agnes_dispatch_queue import SQLiteAgnesDispatchQueue
from .agnes_global_lease import SQLiteAgnesLeaseStore
from .agnes_task_result import SQLiteAgnesTaskResultStore
from .auth_http import PilotAuthHttpTransport
from .followed_http import FollowedHttpTransport
from .followed_store import SQLiteFollowedOpportunityStore
from .followup_http import FollowupHttpTransport
from .followup_store import SQLiteFollowupStore
from .invite_auth import (
    IssuedInvite,
    SQLiteInviteStore,
    issue_invite,
    redeem_invite,
)
from .outreach_http import OutreachHttpTransport
from .outreach_service import GroundedOutreachService, SQLiteOutreachResultStore
from .profile_http import ProfileHttpTransport
from .reminder_http import ReminderHttpTransport
from .reminder_store import SQLiteReminderInboxStore
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


OutreachModelCall = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class SQLiteTodayRuntime:
    """Single-host Tianjin Pilot runtime binding."""

    path: Path
    repository: SQLiteTodayActionsRepository
    invite_store: SQLiteInviteStore
    session_store: SQLiteSessionStore
    followup_store: SQLiteFollowupStore
    followed_store: SQLiteFollowedOpportunityStore
    reminder_store: SQLiteReminderInboxStore
    outreach_result_store: SQLiteOutreachResultStore
    result_store: SQLiteAgnesTaskResultStore
    dispatch_queue: SQLiteAgnesDispatchQueue
    lease_store: SQLiteAgnesLeaseStore
    principal_resolver: OpaqueCookiePrincipalResolver
    application: RepositoryTodayActionsApplication
    transport: TodayActionsHttpTransport
    outreach_service: GroundedOutreachService
    auth_transport: PilotAuthHttpTransport = field(init=False)
    profile_transport: ProfileHttpTransport = field(init=False)
    followup_transport: FollowupHttpTransport = field(init=False)
    followed_transport: FollowedHttpTransport = field(init=False)
    reminder_transport: ReminderHttpTransport = field(init=False)
    outreach_transport: OutreachHttpTransport = field(init=False)

    def __post_init__(self) -> None:
        self.auth_transport = PilotAuthHttpTransport(
            invite_session_issuer=self,
            session_store=self.session_store,
        )
        self.profile_transport = ProfileHttpTransport(
            principal_resolver=self.principal_resolver,
            repository=self.repository,
        )
        self.followup_transport = FollowupHttpTransport(
            principal_resolver=self.principal_resolver,
            repository=self.repository,
            store=self.followup_store,
        )
        self.followed_transport = FollowedHttpTransport(
            principal_resolver=self.principal_resolver,
            repository=self.repository,
            store=self.followed_store,
        )
        self.reminder_transport = ReminderHttpTransport(
            principal_resolver=self.principal_resolver,
            repository=self.repository,
            store=self.reminder_store,
        )
        self.outreach_transport = OutreachHttpTransport(
            principal_resolver=self.principal_resolver,
            service=self.outreach_service,
        )

    def issue_profile_invite(
        self,
        *,
        principal: TrustedPrincipal,
        now: datetime,
        ttl_seconds: int | None = None,
    ) -> IssuedInvite:
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
    outreach_model_call: OutreachModelCall | None = None,
) -> SQLiteTodayRuntime:
    path = Path(path)
    initial_now = now_provider() if now_provider is not None else datetime.now(timezone.utc)
    if initial_now.tzinfo is None or initial_now.utcoffset() is None:
        raise ValueError("now_provider must return timezone-aware datetime")

    repository = SQLiteTodayActionsRepository(path)
    invite_store = SQLiteInviteStore(path)
    session_store = SQLiteSessionStore(path)
    followup_store = SQLiteFollowupStore(path)
    followed_store = SQLiteFollowedOpportunityStore(path)
    reminder_store = SQLiteReminderInboxStore(path)
    outreach_result_store = SQLiteOutreachResultStore(path)
    result_store = SQLiteAgnesTaskResultStore(path)
    dispatch_queue = SQLiteAgnesDispatchQueue(path)
    lease_store = SQLiteAgnesLeaseStore(path, now=initial_now)
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
    outreach_service = GroundedOutreachService(
        repository=repository,
        result_store=outreach_result_store,
        lease_store=lease_store,
        model_call=outreach_model_call,
        clock=now_provider,
    )
    return SQLiteTodayRuntime(
        path=path,
        repository=repository,
        invite_store=invite_store,
        session_store=session_store,
        followup_store=followup_store,
        followed_store=followed_store,
        reminder_store=reminder_store,
        outreach_result_store=outreach_result_store,
        result_store=result_store,
        dispatch_queue=dispatch_queue,
        lease_store=lease_store,
        principal_resolver=principal_resolver,
        application=application,
        transport=transport,
        outreach_service=outreach_service,
    )
