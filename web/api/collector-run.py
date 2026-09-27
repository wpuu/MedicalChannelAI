from __future__ import annotations

import asyncio
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from vercel.functions import RuntimeCache
from vercel.queue import DuplicateIdempotencyKeyError, send

from collector_incremental import scan_bucket_id
from collector_incremental_scheduler import (
    SCHEDULED_INCREMENTAL_SOURCES,
    choose_due_incremental_source,
    mark_incremental_source_attempt,
)
from collector_namespace import (
    ACTIVE_CYCLE_KEY,
    ACTIVE_CYCLE_TTL_SECONDS,
    INCREMENTAL_ACTIVE_KEY,
    MAX_RECOVERY_CYCLES_PER_DAY,
    META_KEY,
    QUEUE_TOPIC_NAME,
    active_cycle_id,
    active_incremental_id,
    cycle_has_live_running_stage,
    cycle_publish_completed,
    recovery_attempt_count,
    reset_unfinished_stage_attempts,
    write_collector_state,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
MESSAGE_RETENTION = timedelta(days=2)
DEEP_START_DELAY_WHEN_INCREMENTAL_SECONDS = 300
# This is an explicit allowlist of implemented source adapters. Merely adding a
# policy must never activate a new collector without an adapter and tests.
INCREMENTAL_SOURCE_IDS = SCHEDULED_INCREMENTAL_SOURCES


class CollectorStartConflict(RuntimeError):
    pass


def _authorized(request: BaseHTTPRequestHandler) -> tuple[bool, str]:
    # Vercel Cron authenticates scheduled invocations with
    # Authorization: Bearer $CRON_SECRET. A schedule/header marker is not a
    # credential and can be forged by any public caller, so fail closed when
    # the secret is absent or does not match.
    cron_secret = str(os.environ.get("CRON_SECRET") or "").strip()
    if not cron_secret:
        return False, "NONE"

    authorization = str(request.headers.get("authorization") or "")
    if not hmac.compare_digest(authorization, f"Bearer {cron_secret}"):
        return False, "NONE"
    return True, "VERCEL_CRON"


def _request_query(request: BaseHTTPRequestHandler) -> dict[str, list[str]]:
    path = str(getattr(request, "path", "") or "")
    return parse_qs(urlsplit(path).query, keep_blank_values=False)


def _first_query(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name) or []
    return str(values[0]).strip().lower() if values else ""


def _plan_cycle(state: object, *, local_date: str) -> tuple[str, bool]:
    """Choose the cycle id for a trigger on ``local_date``.

    First trigger of the day: ``prod:{date}``. A later same-day trigger while
    the day's cycle is unfinished mints ``prod:{date}:recovery-{n}`` with a
    counter persisted in collector state, so every recovery gets fresh queue
    idempotency keys (a reused key is rejected by Vercel Queues for 24 h) and
    the number of same-day recoveries is bounded.
    """
    if not isinstance(state, dict) or str(state.get("local_date") or "") != local_date:
        return f"prod:{local_date}", False
    if cycle_publish_completed(state):
        raise CollectorStartConflict("COLLECTOR_CYCLE_ALREADY_COMPLETED_TODAY")
    attempt = recovery_attempt_count(state) + 1
    if attempt > MAX_RECOVERY_CYCLES_PER_DAY:
        raise CollectorStartConflict("COLLECTOR_RECOVERY_LIMIT")
    return f"prod:{local_date}:recovery-{attempt}", True


def _activate_cycle(
    cache: RuntimeCache,
    *,
    cycle_id: str,
    now: datetime,
    local_date: str,
    source: str,
) -> None:
    current_state = cache.get(META_KEY)
    # Only a stage whose wall-clock lease is unexpired can still have a live
    # worker. A RUNNING marker left behind by a platform kill (or by any
    # previous day) never blocks a new cycle.
    if cycle_has_live_running_stage(current_state, now=now):
        raise CollectorStartConflict("COLLECTOR_CYCLE_ALREADY_RUNNING")

    active = {
        "schema_version": "0.1",
        "cycle_id": cycle_id,
        "cycle_as_of": now.isoformat(),
        "local_date": local_date,
        "trigger_source": source,
    }
    cache.set(
        ACTIVE_CYCLE_KEY,
        active,
        {"ttl": ACTIVE_CYCLE_TTL_SECONDS, "tags": ["medicalchannelai-collector-active-cycle"]},
    )
    read_back = cache.get(ACTIVE_CYCLE_KEY)
    if active_cycle_id(read_back) != cycle_id:
        raise RuntimeError("COLLECTOR_ACTIVE_CYCLE_READBACK_FAILED")


def _release_cycle_if_owned(cache: RuntimeCache, cycle_id: str) -> None:
    if active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)) == cycle_id:
        cache.delete(ACTIVE_CYCLE_KEY)


async def _enqueue_start(source: str) -> tuple[str, str, str, int]:
    now = datetime.now(timezone.utc)
    local_date = now.astimezone(SHANGHAI).date().isoformat()

    cache = RuntimeCache()
    state = cache.get(META_KEY)
    cycle_id, is_recovery = _plan_cycle(state, local_date=local_date)
    _activate_cycle(
        cache,
        cycle_id=cycle_id,
        now=now,
        local_date=local_date,
        source=source,
    )
    if is_recovery and isinstance(state, dict):
        # Persist the recovery counter before send() so a failed send can never
        # reuse this cycle id, and give unfinished stages a fresh attempt budget.
        reset_unfinished_stage_attempts(state, recovery_cycle_id=cycle_id, now=now)
        write_collector_state(cache, state, now=now)

    # Deep collection owns the authoritative mutation lease from this point.
    # If an incremental invocation was already in flight, delay the first deep
    # queue message long enough for that bounded function to finish/abort. New
    # incremental scans will see ACTIVE_CYCLE_KEY and will not enter.
    delay_seconds = (
        DEEP_START_DELAY_WHEN_INCREMENTAL_SECONDS
        if active_incremental_id(cache.get(INCREMENTAL_ACTIVE_KEY)) is not None
        else 0
    )
    try:
        message_id = await send(
            QUEUE_TOPIC_NAME,
            {
                "schema_version": "0.1",
                "stage": "ccgp",
                "cycle_as_of": now.isoformat(),
                "cycle_id": cycle_id,
            },
            retention=MESSAGE_RETENTION,
            delay=delay_seconds,
            idempotency_key=f"{QUEUE_TOPIC_NAME}:{cycle_id}:ccgp",
        )
    except DuplicateIdempotencyKeyError as exc:
        # The first message of this exact cycle id was already accepted by the
        # queue; the lease we just wrote belongs to that in-flight cycle, keep it.
        raise CollectorStartConflict("COLLECTOR_CYCLE_ALREADY_QUEUED") from exc
    except Exception:
        # No queue message exists for this lease: release it so the next trigger
        # (cron or manual) is not locked out until ACTIVE_CYCLE_TTL_SECONDS.
        _release_cycle_if_owned(cache, cycle_id)
        raise
    return str(message_id), local_date, cycle_id, delay_seconds


async def _enqueue_incremental(source: str, trigger_source: str) -> tuple[str, str, str]:
    source_id = str(source or "").strip().lower()
    if source_id not in INCREMENTAL_SOURCE_IDS:
        raise ValueError("INCREMENTAL_SOURCE_UNSUPPORTED")

    now = datetime.now(timezone.utc)
    cache = RuntimeCache()
    # The deep-cycle lease is written before its first queue message is delivered,
    # closing the old gap where an incremental scan could slip in before META_KEY
    # had a RUNNING stage. Also keep one incremental source active at a time.
    if (
        active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)) is not None
        or cycle_has_live_running_stage(cache.get(META_KEY), now=now)
    ):
        raise CollectorStartConflict("INCREMENTAL_BLOCKED_BY_DEEP_CYCLE")
    if active_incremental_id(cache.get(INCREMENTAL_ACTIVE_KEY)) is not None:
        raise CollectorStartConflict("INCREMENTAL_SCAN_ALREADY_RUNNING")

    bucket_id = scan_bucket_id(source_id, now=now)
    message_id = await send(
        QUEUE_TOPIC_NAME,
        {
            "schema_version": "0.1",
            "mode": "incremental",
            "source_id": source_id,
            "observed_at": now.isoformat(),
            "scan_bucket_id": bucket_id,
            "trigger_source": trigger_source,
        },
        retention=MESSAGE_RETENTION,
        idempotency_key=f"{QUEUE_TOPIC_NAME}:{bucket_id}",
    )
    # A scheduler attempt means Queue accepted a real source job. Do not write it
    # before send(): a transient queue-start failure must remain immediately
    # eligible for the next auto-selection tick rather than consuming 1-2 hours
    # of source backoff without any scan having run.
    mark_incremental_source_attempt(cache, source_id, now=now)
    return str(message_id), bucket_id, now.isoformat()


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        allowed, trigger_source = _authorized(self)
        if not allowed:
            return self._send_json(403, {"error": "COLLECTOR_TRIGGER_FORBIDDEN"})

        query = _request_query(self)
        mode = _first_query(query, "mode")
        if mode and mode != "incremental":
            return self._send_json(400, {"error": "COLLECTOR_MODE_INVALID"})

        if mode == "incremental":
            requested_source = _first_query(query, "source")
            auto_decision = None
            if not requested_source or requested_source == "auto":
                auto_decision = choose_due_incremental_source(RuntimeCache())
                if auto_decision.source_id is None:
                    return self._send_json(
                        200,
                        {
                            "schema_version": "0.1",
                            "service": "MedicalChannelAI",
                            "trigger_source": trigger_source,
                            "collector": {
                                "action": "NO_SOURCE_DUE",
                                "execution_plane": "VERCEL_QUEUE_V2",
                                "mode": "INCREMENTAL_AUTO",
                                "evaluated_at": auto_decision.evaluated_at,
                                "next_due_at": auto_decision.next_due_at,
                            },
                        },
                    )
                source_id = auto_decision.source_id
            else:
                source_id = requested_source

            if source_id not in INCREMENTAL_SOURCE_IDS:
                return self._send_json(
                    400,
                    {
                        "error": "INCREMENTAL_SOURCE_UNSUPPORTED",
                        "supported_sources": list(INCREMENTAL_SOURCE_IDS),
                    },
                )
            try:
                message_id, bucket_id, observed_at = asyncio.run(
                    _enqueue_incremental(source_id, trigger_source)
                )
            except CollectorStartConflict as exc:
                error = str(exc) or "INCREMENTAL_SCAN_CONFLICT"
                return self._send_json(409, {"error": error, "source_id": source_id})
            except Exception as exc:
                return self._send_json(
                    503,
                    {
                        "error": "INCREMENTAL_QUEUE_START_FAILED",
                        "source_id": source_id,
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:180],
                    },
                )

            return self._send_json(
                202,
                {
                    "schema_version": "0.1",
                    "service": "MedicalChannelAI",
                    "trigger_source": trigger_source,
                    "collector": {
                        "action": "QUEUED",
                        "execution_plane": "VERCEL_QUEUE_V2",
                        "mode": "INCREMENTAL_AUTO" if auto_decision else "INCREMENTAL",
                        "source_id": source_id,
                        "scan_bucket_id": bucket_id,
                        "observed_at": observed_at,
                        "due_source_count": len(auto_decision.due_sources) if auto_decision else None,
                        "message_id": message_id,
                    },
                },
            )

        try:
            message_id, local_date, cycle_id, start_delay_seconds = asyncio.run(
                _enqueue_start(trigger_source)
            )
        except CollectorStartConflict as exc:
            return self._send_json(409, {"error": str(exc) or "COLLECTOR_CYCLE_ALREADY_RUNNING"})
        except Exception as exc:
            return self._send_json(
                503,
                {
                    "error": "COLLECTOR_QUEUE_START_FAILED",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:180],
                },
            )

        self._send_json(
            202,
            {
                "schema_version": "0.1",
                "service": "MedicalChannelAI",
                "trigger_source": trigger_source,
                "collector": {
                    "action": "QUEUED",
                    "execution_plane": "VERCEL_QUEUE_V2",
                    "mode": "DEEP_DAILY",
                    "local_date": local_date,
                    "cycle_id": cycle_id,
                    "stage": "ccgp",
                    "start_delay_seconds": start_delay_seconds,
                    "message_id": message_id,
                },
            },
        )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
