from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .agnes_dispatch_queue import SQLiteAgnesDispatchQueue
from .agnes_task_result import SQLiteAgnesTaskResultStore
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

    One SQLite file may safely host the Pilot profile/public-fact/session/Agnes queue
    tables because each component uses distinct table names plus WAL/busy timeout.
    This is deliberately a single-host reference runtime. It must not be copied to
    multiple stateless serverless instances as independent local databases.
    """

    path: Path
    repository: SQLiteTodayActionsRepository
    session_store: SQLiteSessionStore
    result_store: SQLiteAgnesTaskResultStore
    dispatch_queue: SQLiteAgnesDispatchQueue
    principal_resolver: OpaqueCookiePrincipalResolver
    application: RepositoryTodayActionsApplication
    transport: TodayActionsHttpTransport

    def issue_authenticated_session(
        self,
        *,
        principal: TrustedPrincipal,
        now: datetime,
        ttl_seconds: int | None = None,
    ) -> IssuedSession:
        """Issue a browser session only after an upstream login/admin check succeeds.

        This method is not an HTTP login endpoint and performs no credential check by
        itself. External adapters must never expose it directly to unauthenticated
        callers.
        """

        kwargs = {}
        if ttl_seconds is not None:
            kwargs["ttl_seconds"] = ttl_seconds
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
    session_store = SQLiteSessionStore(path)
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
        session_store=session_store,
        result_store=result_store,
        dispatch_queue=dispatch_queue,
        principal_resolver=principal_resolver,
        application=application,
        transport=transport,
    )
