from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .adapters import TjmughAdapter
from .ccgp_lifecycle_adapter import CcgpLifecycleAdapter
from .first_central_adapter import FirstCentralHospitalAdapter
from .intent_adapter import CcgpIntentAdapter
from .tianjin_government_procurement_adapter import TianjinGovernmentProcurementAdapter
from .tianjin_public_resource_adapter import TianjinPublicResourceAdapter


REGISTRY_PATH = Path(__file__).with_name("source_registry.tianjin.v0.1.json")
KNOWN_OFFICIAL_MIRRORS = {
    "ccgp_local_notices",
    "ccgp_procurement_intent",
    "tj_public_resource_exchange",
}
TIANJIN_GOVERNMENT_DETAIL_HOSTS = {
    "tjgp.cz.tj.gov.cn",
    "ccgp-tianjin.gov.cn",
    "www.ccgp-tianjin.gov.cn",
}


def _allows_tianjin_government_detail(url: str) -> bool:
    """Fail-closed structural check for the two official Tianjin procurement hosts.

    Query parameter order may be rewritten by clients/caches, so identity is parsed
    structurally instead of relying on one serialized order. No extra or duplicate
    query parameters are accepted in v0.1.
    """

    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if (parsed.hostname or "").lower() not in TIANJIN_GOVERNMENT_DETAIL_HOSTS:
        return False
    if parsed.path != "/portal/documentView.do" or parsed.fragment:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    if set(query) != {"method", "id", "ver"}:
        return False
    if any(len(values) != 1 for values in query.values()):
        return False
    method = query["method"][0]
    document_id = query["id"][0]
    version = query["ver"][0]
    return method == "view" and document_id.isdigit() and version == "2"


@dataclass(frozen=True)
class RegisteredSource:
    source_id: str
    source_name: str
    canonical_base_url: str
    allowed_url_patterns: tuple[str, ...]
    enabled: bool
    authority_type: str
    source_type: str
    provenance_role: str
    parser_version: str | None
    raw: dict[str, Any]

    def allows_url(self, url: str) -> bool:
        if not self.enabled:
            return False
        if self.source_id == "tj_government_procurement":
            return _allows_tianjin_government_detail(url)
        return any(re.match(pattern, url) for pattern in self.allowed_url_patterns)


ADAPTER_FACTORIES = {
    "tj_government_procurement": TianjinGovernmentProcurementAdapter,
    "ccgp_local_notices": CcgpLifecycleAdapter,
    "ccgp_procurement_intent": CcgpIntentAdapter,
    "tjmugh_procurement": TjmughAdapter,
    "tj_first_central_hospital_procurement": FirstCentralHospitalAdapter,
    "tj_public_resource_exchange": TianjinPublicResourceAdapter,
}


def _default_provenance_role(source_id: str) -> str:
    return "OFFICIAL_MIRROR" if source_id in KNOWN_OFFICIAL_MIRRORS else "PRIMARY_SOURCE"


def load_registry(path: Path = REGISTRY_PATH) -> list[RegisteredSource]:
    with path.open("r", encoding="utf-8") as handle:
        items = json.load(handle)
    result: list[RegisteredSource] = []
    for item in items:
        source_id = item["source_id"]
        result.append(
            RegisteredSource(
                source_id=source_id,
                source_name=item["source_name"],
                canonical_base_url=item["canonical_base_url"],
                allowed_url_patterns=tuple(item.get("allowed_url_patterns", [])),
                enabled=bool(item["enabled"]),
                authority_type=item["authority_type"],
                source_type=item["source_type"],
                provenance_role=item.get("provenance_role", _default_provenance_role(source_id)),
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
