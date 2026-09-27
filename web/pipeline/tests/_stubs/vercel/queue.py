"""In-memory stand-in for vercel.queue."""
from __future__ import annotations

SENT: list[dict] = []
USED_IDEMPOTENCY_KEYS: set[str] = set()


class QueueError(Exception):
    pass


class DuplicateIdempotencyKeyError(QueueError):
    status_code = 409


async def send(topic, payload, *, retention=None, delay=0, idempotency_key=None, **_kwargs):
    if idempotency_key is not None:
        if idempotency_key in USED_IDEMPOTENCY_KEYS:
            raise DuplicateIdempotencyKeyError(idempotency_key)
        USED_IDEMPOTENCY_KEYS.add(idempotency_key)
    SENT.append({"topic": topic, "payload": payload, "delay": delay, "idempotency_key": idempotency_key})
    return f"msg-{len(SENT)}"


class Message:
    def __init__(self, payload) -> None:
        self.payload = payload

    def __class_getitem__(cls, item):
        return cls


class Topic:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, name: str) -> None:
        self.name = name


def subscribe(**_kwargs):
    def decorator(fn):
        return fn

    return decorator


async def accept_and_handle(body, headers, *, lease_duration=None) -> None:
    return None


def reset() -> None:
    SENT.clear()
    USED_IDEMPOTENCY_KEYS.clear()
