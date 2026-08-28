from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import TjmughAdapter
from .ccgp_lifecycle_adapter import CcgpLifecycleAdapter
from .first_central_adapter import FirstCentralHospitalAdapter
from .intent_adapter import CcgpIntentAdapter
from .tianjin_public_resource_adapter import TianjinPublicResourceAdapter


REGISTRY_PATH = Path(__file__).with_name("source_registry.tianjin.v0.1.json")


@dataclass(frozen=True)
class RegisteredSource:
    source_id: str
    source_name: str
    canonical_base_url: str
    allowed_url_patterns: tuple[str, ...]
    enabled: bool
    authority_type: str
    source_type: str
    parser_version: str | None
    raw: dict[str, Any]

    def allows_url(self, url: str) -> bool:
        return self.enabled and any(re.match(pattern, url) for pattern in self.allowed_url_patterns)


ADAPTER_FACTORIES = {
    "ccgp_local_notices": CcgpLifecycleAdapter,
    "ccgp_procurement_intent": CcgpIntentAdapter,
    "tjmugh_procurement": TjmughAdapter,
    "tj_first_central_hospital_procurement": FirstCentralHospitalAdapter,
    "tj_public_resource_exchange": TianjinPublicResourceAdapter,
}


def load_registry(path: Path = REGISTRY_PATH) -> list[RegisteredSource]:
    with path.open("r", encoding="utf-8") as handle:
        items = json.load(handle)
    result: list[RegisteredSource] = []
    for item in items:
        result.append(
            RegisteredSource(
                source_id=item["source_id"],
                source_name=item["source_name"],
                canonical_base_url=item["canonical_base_url"],
                allowed_url_patterns=tuple(item.get("allowed_url_patterns", [])),
                enabled=bool(item["enabled"]),
                authority_type=item["authority_type"],
                source_type=item["source_type"],
                parser_version=item.get("parser_version"),
                raw=item,
            )
        )
    return result


def resolve_source(url: str, registry: list[RegisteredSource] | None = None) -> RegisteredSource:
    sources = registry if registry is not None else load_registry()
    matches = [source for source in sources if source.allows_url(url)]
    if len(matches) != 1:
        if not matches:
            raise ValueError("URL does not match any enabled registered source")
        raise ValueError("URL matches more than one registered source; registry is ambiguous")
    return matches[0]


def adapter_for_source(source: RegisteredSource):
    factory = ADAPTER_FACTORIES.get(source.source_id)
    if factory is None:
        raise ValueError(f"no adapter is implemented for source_id={source.source_id}")
    adapter = factory()
    if adapter.source_id != source.source_id:
        raise ValueError("adapter source_id mismatch")
    return adapter
