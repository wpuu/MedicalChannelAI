from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler

from vercel.queue import Message, Topic, accept_and_handle, subscribe

from collector_queue import process_collector_payload

QUEUE_TOPIC = Topic[dict[str, object]]("medicalchannelai-refresh-v2")
CONSUMER_GROUP = "api/collector-queue.py"


@subscribe(
    topic=QUEUE_TOPIC,
    consumer_group=CONSUMER_GROUP,
    retry_after=360,
    max_concurrency=1,
    max_attempts=3,
)
async def collector_worker(message: Message[dict[str, object]]) -> None:
    payload = message.payload
    if isinstance(payload, dict):
        await process_collector_payload(payload)


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
            asyncio.run(accept_and_handle(body, headers, lease_duration=360))
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
