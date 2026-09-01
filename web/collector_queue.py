from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from vercel.queue import send

from collector_runtime import STAGE_ORDER, run_stage

QUEUE_TOPIC_NAME = "medicalchannelai-refresh"
MESSAGE_RETENTION = timedelta(hours=24)
NEXT_STAGE_DELAY_SECONDS = 2


def _parse_cycle_as_of(payload: dict[str, Any]) -> datetime | None:
    raw = str(payload.get("cycle_as_of") or "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo is not None else None


def _next_stage(stage: str) -> str | None:
    try:
        index = STAGE_ORDER.index(stage)
    except ValueError:
        return None
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None


async def _enqueue_stage(*, stage: str, cycle_as_of: datetime, cycle_id: str) -> str:
    message_id = await send(
        QUEUE_TOPIC_NAME,
        {
            "schema_version": "0.1",
            "stage": stage,
            "cycle_as_of": cycle_as_of.isoformat(),
            "cycle_id": cycle_id,
        },
        retention=MESSAGE_RETENTION,
        delay=NEXT_STAGE_DELAY_SECONDS if stage != "ccgp" else 0,
        idempotency_key=f"medicalchannelai-refresh:{cycle_id}:{stage}",
    )
    return str(message_id)


async def process_collector_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != "0.1":
        return

    stage = str(payload.get("stage") or "").strip().lower()
    cycle_id = str(payload.get("cycle_id") or "").strip()
    cycle_as_of = _parse_cycle_as_of(payload)
    if stage not in STAGE_ORDER or not cycle_id or cycle_as_of is None:
        return

    status, result = run_stage(stage, now=cycle_as_of)
    action = str(result.get("action") or "")
    if status == 200 and action in {"COMPLETED", "ALREADY_COMPLETED_TODAY"}:
        next_stage = _next_stage(stage)
        if next_stage is not None:
            await _enqueue_stage(stage=next_stage, cycle_as_of=cycle_as_of, cycle_id=cycle_id)
        return

    error = str(result.get("error") or result.get("error_code") or "UNKNOWN")
    if status == 409 and "COLLECTOR_STAGE_RETRY_LIMIT" in error:
        # Two real attempts have already failed. Acknowledge this queue message and
        # leave the collector status FAILED instead of retrying forever.
        return

    # Raising asks Vercel Queues to redeliver. run_stage() itself caps real
    # upstream attempts per stage/day, so persistent failures become stable FAILED
    # status rather than an unbounded request loop.
    raise RuntimeError(f"COLLECTOR_QUEUE_STAGE_FAILED:{stage}:{status}:{error[:180]}")
