from __future__ import annotations

from datetime import datetime, timezone

from vercel.functions import RuntimeCache
from vercel.workflow import Workflows

wf = Workflows(namespace="medicalchannelaitianjinrefresh")

STATUS_KEY = "medicalchannelai:collector-workflow-status:v1"
STATUS_TTL_SECONDS = 7 * 24 * 60 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@wf.step(max_retries=2)
async def record_collector_phase(triggered_at: str, phase: str) -> dict:
    cache = RuntimeCache()
    current = cache.get(STATUS_KEY)
    current = current if isinstance(current, dict) else {}
    payload = {
        "schema_version": "0.1",
        "phase": phase,
        "triggered_at": triggered_at,
        "run_id": current.get("run_id"),
        "updated_at": _now_iso(),
    }
    cache.set(
        STATUS_KEY,
        payload,
        {
            "ttl": STATUS_TTL_SECONDS,
            "tags": ["medicalchannelai-collector-workflow"],
        },
    )
    return payload


@wf.workflow
async def tianjin_refresh_workflow(triggered_at: str) -> dict:
    await record_collector_phase(triggered_at, "RUNNING")
    return await record_collector_phase(triggered_at, "COMPLETED")
