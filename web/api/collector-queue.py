from __future__ import annotations

from vercel.queue import Message, Topic, asgi_app, subscribe

from collector_namespace import QUEUE_TOPIC_NAME
from collector_queue import process_collector_payload

QUEUE_TOPIC = Topic[dict[str, object]](QUEUE_TOPIC_NAME)
CONSUMER_GROUP = "api/collector-queue.py"


@subscribe(
    topic=QUEUE_TOPIC,
    consumer_group=CONSUMER_GROUP,
    retry_after=150,
    max_concurrency=1,
    max_attempts=3,
)
async def collector_worker(message: Message[dict[str, object]]) -> None:
    payload = message.payload
    if isinstance(payload, dict):
        await process_collector_payload(payload)


app = asgi_app()
