from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler
from datetime import datetime
from zoneinfo import ZoneInfo

from vercel.functions import RuntimeCache
from collector_audit import emit_collector_audit

from vercel.queue import Message, Topic, accept_and_handle, subscribe

from collector_queue import process_collector_payload, STAGE_ORDER, runtime

QUEUE_TOPIC = Topic[dict[str, object]]("medicalchannelai-refresh-v2")
CONSUMER_GROUP = "api/collector-queue.py"


def _deep_delivery(payload: object) -> tuple[str, str, str, str] | None:
    if not isinstance(payload, dict) or payload.get("schema_version") != "0.1":
        return None
    if payload.get("mode"):
        return None  # incremental tick/source jobs keep their existing policy
    stage = str(payload.get("stage") or "")
    cycle_id = str(payload.get("cycle_id") or "")
    cycle_as_of = str(payload.get("cycle_as_of") or "")
    if stage not in STAGE_ORDER or not cycle_id.startswith("prod:"):
        return None
    try:
        instant = datetime.fromisoformat(cycle_as_of.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return None
        business_date = instant.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    except ValueError:
        return None
    return cycle_id, cycle_as_of, stage, business_date


@subscribe(
    topic=QUEUE_TOPIC,
    consumer_group=CONSUMER_GROUP,
    retry_after=150,
    max_concurrency=1,
    max_attempts=3,
)
async def collector_worker(message: Message[dict[str, object]]) -> None:
    payload = message.payload
    if not isinstance(payload, dict):
        return
    audit = _deep_delivery(payload)
    if audit:
        cycle_id, cycle_as_of, stage, business_date = audit
        emit_collector_audit(
            cycle_id=cycle_id, cycle_as_of=cycle_as_of, stage=stage,
            status="RUNNING", outcome="QUEUE_DELIVERED",
        )
    try:
        await process_collector_payload(payload)
    except Exception:
        if audit:
            emit_collector_audit(
                cycle_id=cycle_id, cycle_as_of=cycle_as_of, stage=stage,
                status="FAILED", outcome="WORKER_EXCEPTION",
                error_code="QUEUE_WORKER_ERROR",
            )
        raise
    if audit:
        try:
            current = runtime.load_status(RuntimeCache())
            if current.get("local_date") != business_date:
                return
            step = (current.get("stages") or {}).get(stage)
            if not isinstance(step, dict):
                return
            stage_status = str(step.get("status") or "")
            if stage_status not in {"COMPLETED", "SKIPPED", "FAILED"}:
                return
            result = step.get("result") if isinstance(step.get("result"), dict) else {}
            count = result.get("new_verified_record_count")
            attempts = step.get("attempt_count")
            code = str(step.get("error_code") or "").upper()
            emit_collector_audit(
                cycle_id=cycle_id, cycle_as_of=cycle_as_of, stage=stage,
                status="FAILED" if stage_status == "FAILED" else "COMPLETED",
                outcome=stage_status,
                error_code=code if code and code.replace("_", "").isalnum() else None,
                attempt_count=attempts if type(attempts) is int else None,
                new_verified_record_count=count if type(count) is int else None,
            )
        except Exception as exc:
            print(f"COLLECTOR_AUDIT_READBACK_FAILED:{type(exc).__name__}", flush=True)


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        raw_length = str(self.headers.get("content-length") or "0").strip()
        try:
            content_length = max(0, int(raw_length))
        except ValueError:
            content_length = 0
        body = self.rfile.read(content_length) if content_length else b""
        headers = {str(key): str(value) for key, value in self.headers.items()}

        try:
            asyncio.run(accept_and_handle(body, headers, lease_duration=300))
        except Exception:
            self.send_response(500)
            self.end_headers()
            return

        self.send_response(204)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()

    def do_GET(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "POST")
        self.end_headers()
