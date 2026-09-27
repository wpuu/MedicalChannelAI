"""In-memory stand-in for vercel.functions.RuntimeCache."""
from __future__ import annotations

import copy
import json

_STORE: dict[str, object] = {}


class RuntimeCache:
    def __init__(self, namespace: str | None = None, **_kwargs) -> None:
        self.namespace = namespace or "default"

    def _key(self, key: str) -> str:
        return f"{self.namespace}::{key}"

    def get(self, key: str):
        return copy.deepcopy(_STORE.get(self._key(key)))

    def set(self, key: str, value, options=None) -> None:
        # Emulate the JSON round trip of the real service.
        _STORE[self._key(key)] = json.loads(json.dumps(value, ensure_ascii=False))

    def delete(self, key: str) -> None:
        _STORE.pop(self._key(key), None)


def get_cache(**kwargs) -> RuntimeCache:
    return RuntimeCache(**kwargs)


def reset_store() -> None:
    _STORE.clear()


def dump_store() -> dict[str, object]:
    return copy.deepcopy(_STORE)
