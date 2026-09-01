from __future__ import annotations

from datetime import timedelta
from typing import Any

from vercel.queue import send

import backfill_runtime as runtime

QUEUE_TOPIC_NAME = runtime.QUEUE_TOPIC_NAME
MESSAGE_RETENTION = timedelta(hours=24)
NEXT_STAGE_DELAY_SECONDS = 2


def _active_cycle_matches(cycle_id: str) -> bool:
    return runtime.active_cycle_id() == cycle_id


async def _enqueue_stage(*, stage: str, cycle_id: str) -> str:
    message_id = await send(
        QUEUE_TOPIC_NAME,
        {
            "schema_version": "0.1",
            "stage": stage,
            "cycle_id": cycle_id,
        },
        retention=MESSAGE_RETENTION,
        delay=NEXT_STAGE_DELAY_SECONDS,
        idempotency_key=f"{QUEUE_TOPIC_NAME}:{cycle_id}:{stage}",
    )
    return str(message_id)


async def enqueue_start(*, cycle_id: str) -> str:
    return await _enqueue_stage(stage="discover:0", cycle_id=cycle_id)


async def _fence_duplicate_delivery(*, stage: str, cycle_id: str) -> bool:
    state = runtime.load_status()
    if str(state.get("cycle_id") or "") != cycle_id:
        return True

    current_stage = state.get("current_stage")
    status = str(state.get("status") or "")
    if status == "COMPLETED" and current_stage is None:
        return True

    if status in {"RUNNING", "QUEUED"} and isinstance(current_stage, str) and current_stage and current_stage != stage:
        # The delivered stage has already committed and the chain has advanced.
        # Re-emit only the authoritative current stage using its idempotency key.
        # This also closes the crash window between committing a stage and
        # enqueueing its successor.
        if _active_cycle_matches(cycle_id):
            await _enqueue_stage(stage=current_stage, cycle_id=cycle_id)
        return True
    return False


async def process_backfill_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != "0.1":
        return

    stage = str(payload.get("stage") or "").strip().lower()
    cycle_id = str(payload.get("cycle_id") or "").strip()
    if not stage or not cycle_id:
        return

    if not _active_cycle_matches(cycle_id):
        return
    if await _fence_duplicate_delivery(stage=stage, cycle_id=cycle_id):
        return

    try:
        status, result = runtime.run_stage(stage, cycle_id=cycle_id)
    except runtime.BackfillError as exc:
        # run_stage can reject an already-exhausted stage before entering its
        # internal handler. The runtime has already persisted FAILED state, so
        # acknowledge the final delivery instead of asking Queue to retry it.
        if "BACKFILL_STAGE_RETRY_LIMIT" in str(exc):
            return
        raise

    action = str(result.get("action") or "")
    next_stage = result.get("next_stage")

    if status == 200 and action in {"COMPLETED", "STALE_CYCLE_IGNORED"}:
        if action == "COMPLETED" and isinstance(next_stage, str) and next_stage:
            if not _active_cycle_matches(cycle_id):
                return
            await _enqueue_stage(stage=next_stage, cycle_id=cycle_id)
        return

    if status == 409 and result.get("final"):
        return

    error = str(result.get("error") or "UNKNOWN")
    raise RuntimeError(f"BACKFILL_QUEUE_STAGE_FAILED:{stage}:{status}:{error[:180]}")
