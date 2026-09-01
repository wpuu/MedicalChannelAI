from __future__ import annotations

from vercel.queue import Message, Topic, asgi_app, subscribe

from backfill_queue import process_backfill_payload

QUEUE_TOPIC = Topic[dict[str, object]]("medicalchannelai-backfill-v1")
CONSUMER_GROUP = "api/backfill-queue.py"


@subscribe(
    topic=QUEUE_TOPIC,
    consumer_group=CONSUMER_GROUP,
    retry_after=120,
    max_concurrency=1,
    max_attempts=4,
)
async def backfill_worker(message: Message[dict[str, object]]) -> None:
    payload = message.payload
    if isinstance(payload, dict):
        await process_backfill_payload(payload)


app = asgi_app()
