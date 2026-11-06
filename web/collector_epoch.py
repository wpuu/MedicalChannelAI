"""Opt-in Preview epochs isolate all collector cache keys and queue messages."""
from __future__ import annotations

import os
import re
from typing import Any


def preview_epoch() -> str | None:
    if os.environ.get("VERCEL_ENV", "").strip().lower() != "preview":
        return None
    value = os.environ.get("MCAI_PREVIEW_EPOCH", "").strip()
    if not value:
        return None
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", value):
        raise ValueError("PREVIEW_EPOCH_INVALID")
    return value


def epoch_key(value: str, epoch: str) -> str:
    return f"medicalchannelai:preview:{epoch}:{value}"


class _EpochCache:
    def __init__(self, cache: Any, epoch: str):
        self._cache = cache
        self._epoch = epoch

    def get(self, key: str):
        return self._cache.get(epoch_key(key, self._epoch))

    def set(self, key: str, value: Any, options=None):
        if options is None:
            return self._cache.set(epoch_key(key, self._epoch), value)
        scoped = dict(options)
        if "tags" in scoped:
            scoped["tags"] = [epoch_key(tag, self._epoch) for tag in scoped["tags"]]
        return self._cache.set(epoch_key(key, self._epoch), value, scoped)

    def delete(self, key: str):
        return self._cache.delete(epoch_key(key, self._epoch))


def RuntimeCache(*args, **kwargs):
    epoch = preview_epoch()  # Validate before constructing/accessing a cache.
    from vercel.functions import RuntimeCache as NativeCache
    cache = NativeCache(*args, **kwargs)
    return _EpochCache(cache, epoch) if epoch else cache


def accepts_payload(payload: dict[str, Any]) -> bool:
    epoch = preview_epoch()
    received = payload.get("preview_epoch")
    # A labelled Preview message must never enter a legacy/Production consumer.
    return received == epoch if epoch else received is None


async def send(topic, payload: dict[str, Any], **options):
    epoch = preview_epoch()
    if epoch:
        if payload.get("preview_epoch") not in {None, epoch}:
            raise ValueError("PREVIEW_QUEUE_EPOCH_MISMATCH")
        payload = {**payload, "preview_epoch": epoch}
        options = dict(options)
        if "idempotency_key" in options:
            options["idempotency_key"] = epoch_key(options["idempotency_key"], epoch)
    elif payload.get("preview_epoch") is not None:
        raise ValueError("PREVIEW_QUEUE_EPOCH_MISMATCH")
    from vercel.queue import send as native_send
    return await native_send(topic, payload, **options)
