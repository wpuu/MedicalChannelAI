from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .award_items import build_award_items_fact, extract_official_award_items
from .ccgp_lifecycle_adapter import (
    ParsedCcgpLifecycleNotice,
    build_ccgp_lifecycle_event_and_facts,
)
from .ccgp_procurement_demand import build_ccgp_procurement_demand_facts
from .collector_core import HostBoundFetcher, ParsedNotice, Snapshot, build_event_and_facts
from .collector_store import SQLitePublicEventLedger, persist_collector_result
from .intent_adapter import ParsedIntentNotice, build_intent_event_and_facts
from .registry import (
    TIANJIN_GOVERNMENT_DETAIL_HOSTS,
    RegisteredSource,
    adapter_for_source,
    resolve_source,
)
from .today_repo import SQLiteTodayActionsRepository


@dataclass(frozen=True)
class CollectedNotice:
    source: RegisteredSource
    snapshot: Snapshot
    parsed: ParsedNotice
    event: dict
    facts: list[dict]


def _allowed_fetch_hosts(source: RegisteredSource, requested_url: str) -> set[str]:
    """Return only hosts already admitted by the registered source URL policy.

    `resolve_source()` validates the requested URL before this function is called.
    The initial request host must therefore be included even when it is an approved
    alias of the registry's canonical base host. Tianjin government detail pages have
    three explicitly allowlisted official hosts and may redirect between them.
    """

    requested_host = (urlparse(requested_url).hostname or "").lower().strip(".")
    canonical_host = (urlparse(source.canonical_base_url).hostname or "").lower().strip(".")
    hosts = {host for host in (requested_host, canonical_host) if host}
    if source.source_id == "tj_government_procurement":
        hosts.update(TIANJIN_GOVERNMENT_DETAIL_HOSTS)
    if not hosts:
        raise ValueError("registered source has no valid fetch host")
    return hosts


def collect_registered_url(url: str) -> CollectedNotice:
    """Fetch, parse and ground one already-registered public notice URL."""

    source = resolve_source(url)
    adapter = adapter_for_source(source)
    fetcher = HostBoundFetcher(_allowed_fetch_hosts(source, url))
    snapshot = fetcher.fetch(url)
    parsed = adapter.parse_notice(snapshot)
    if isinstance(parsed, ParsedIntentNotice):
        event, facts = build_intent_event_and_facts(parsed, snapshot)
    elif isinstance(parsed, ParsedCcgpLifecycleNotice):
        event, facts = build_ccgp_lifecycle_event_and_facts(parsed, snapshot)
        facts.extend(
            build_ccgp_procurement_demand_facts(
                event=event,
                snapshot=snapshot,
                source_id=parsed.source_id,
                source_url=parsed.source_url,
                published_at=parsed.published_at,
                verification_reason=parsed.verification_reason,
            )
        )
    else:
        event, facts = build_event_and_facts(parsed, snapshot)

    if isinstance(parsed, ParsedCcgpLifecycleNotice) and parsed.notice_type == "AWARD":
        award_items = extract_official_award_items(snapshot.text)
        award_fact = build_award_items_fact(
            event=event,
            snapshot=snapshot,
            source_id=parsed.source_id,
            source_url=parsed.source_url,
            published_at=parsed.published_at,
            items=award_items,
        )
        if award_fact is not None:
            facts.append(award_fact)

    return CollectedNotice(
        source=source,
        snapshot=snapshot,
        parsed=parsed,
        event=event,
        facts=facts,
    )


def persist_collected_notice(collected: CollectedNotice, *, db_path: Path) -> dict:
    repository = SQLiteTodayActionsRepository(db_path)
    ledger = SQLitePublicEventLedger(db_path)
    return persist_collector_result(
        repository=repository,
        event_ledger=ledger,
        event=collected.event,
        facts=collected.facts,
    )


def collect_and_persist_url(url: str, *, db_path: Path) -> tuple[CollectedNotice, dict]:
    collected = collect_registered_url(url)
    opportunity = persist_collected_notice(collected, db_path=db_path)
    return collected, opportunity
