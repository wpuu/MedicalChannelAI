from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Callable
from urllib.parse import urlparse

from .collector_core import HostBoundFetcher, Snapshot
from .collector_ingest import collect_and_persist_url
from .registry import RegisteredSource, adapter_for_source, load_registry


DISCOVERY_READY_LISTINGS = {
    "tjmugh_procurement": "https://www.tjmugh.com.cn/cgxxtzgg/index.shtml",
    "tj_first_central_hospital_procurement": "https://www.tj-fch.com/ywgk/ynbx/index.shtml",
    # CCGP dfgg is a national list. The CcgpLifecycleAdapter admits only records
    # whose same <li> explicitly says 地域：天津/天津市. This remains partial coverage.
    "ccgp_local_notices": "https://www.ccgp.gov.cn/cggg/dfgg/index.htm",
}

# Listing expansion is explicit rather than inferred. Only pages independently
# verified as official listing pages may appear here. In particular, do not derive
# index_N.htm pagination merely because index_1.htm exists.
DISCOVERY_READY_LISTING_PAGES = {
    "tjmugh_procurement": (
        "https://www.tjmugh.com.cn/cgxxtzgg/index.shtml",
    ),
    "tj_first_central_hospital_procurement": (
        "https://www.tj-fch.com/ywgk/ynbx/index.shtml",
    ),
    "ccgp_local_notices": (
        "https://www.ccgp.gov.cn/cggg/dfgg/index.htm",
        "https://www.ccgp.gov.cn/cggg/dfgg/index_1.htm",
    ),
}

# These remain intentionally disabled until a source-specific, Tianjin-scoped listing
# and pagination contract is verified. Never guess undocumented classId/W00x routes or
# bypass CAPTCHA merely to increase the ready-source count.
DISCOVERY_NOT_READY = {
    "tj_government_procurement": "NATIVE_LIST_ROUTE_UNRESOLVED",
    "tj_government_procurement_center": "PUBLIC_TENDER_LIST_CLASS_ID_UNRESOLVED",
    "ccgp_procurement_intent": "SEARCH_DISCOVERY_CAPTCHA_AND_QUERY_CONTRACT_NOT_READY",
    "tj_public_resource_exchange": "RESULT_LIST_DISCOVERY_CONTRACT_NOT_READY",
}


@dataclass(frozen=True)
class DiscoveryRunResult:
    source_id: str
    listing_url: str
    discovered_count: int
    due_count: int
    attempted_count: int
    persisted_count: int
    failed_count: int
    skipped_not_due_count: int
    errors: tuple[dict[str, str], ...]
    listing_urls: tuple[str, ...] = ()
    listing_page_count: int = 1

    def as_dict(self) -> dict:
        listing_urls = self.listing_urls or (self.listing_url,)
        return {
            "schema_version": "0.1",
            "source_id": self.source_id,
            "listing_url": self.listing_url,
            "listing_urls": list(listing_urls),
            "listing_page_count": self.listing_page_count,
            "discovered_count": self.discovered_count,
            "due_count": self.due_count,
            "attempted_count": self.attempted_count,
            "persisted_count": self.persisted_count,
            "failed_count": self.failed_count,
            "skipped_not_due_count": self.skipped_not_due_count,
            "errors": list(self.errors),
        }


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")


def _utc_iso(value: datetime) -> str:
    _require_aware(value)
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require_aware(parsed)
    return parsed


def _source(source_id: str) -> RegisteredSource:
    matches = [item for item in load_registry() if item.source_id == source_id]
    if len(matches) != 1:
        raise ValueError(f"source registry does not resolve {source_id}")
    return matches[0]


def discovery_readiness(source_id: str) -> tuple[bool, str]:
    if source_id == "ccgp_local_notices":
        return True, "VERIFIED_EXPLICIT_TIANJIN_REGION_FILTER_BOUNDED_TWO_PAGE_PARTIAL"
    if source_id in DISCOVERY_READY_LISTINGS:
        return True, "VERIFIED_DEDICATED_LISTING"
    if source_id in DISCOVERY_NOT_READY:
        return False, DISCOVERY_NOT_READY[source_id]
    return False, "SOURCE_NOT_REGISTERED_FOR_DISCOVERY"


def listing_pages_for_source(source_id: str) -> tuple[str, ...]:
    ready, reason = discovery_readiness(source_id)
    if not ready:
        raise ValueError(f"source discovery is not ready: {source_id}:{reason}")
    pages = DISCOVERY_READY_LISTING_PAGES.get(source_id)
    if not pages:
        raise ValueError(f"source discovery has no verified listing pages: {source_id}")
    if pages[0] != DISCOVERY_READY_LISTINGS[source_id]:
        raise ValueError(f"source primary listing diverges from listing page contract: {source_id}")
    if len(pages) != len(set(pages)):
        raise ValueError(f"source listing page contract contains duplicates: {source_id}")
    return pages


class SQLiteDiscoveryUrlLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_discovery_urls ("
                "source_id TEXT NOT NULL, "
                "url TEXT NOT NULL, "
                "title TEXT NOT NULL, "
                "first_seen_at TEXT NOT NULL, "
                "last_seen_at TEXT NOT NULL, "
                "last_attempt_at TEXT NULL, "
                "last_success_at TEXT NULL, "
                "last_error_code TEXT NULL, "
                "consecutive_failures INTEGER NOT NULL DEFAULT 0, "
                "PRIMARY KEY(source_id, url))"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_medical_discovery_due "
                "ON medical_discovery_urls(source_id, last_success_at, last_attempt_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def register(self, source_id: str, links: list[tuple[str, str]], *, now: datetime) -> None:
        _require_aware(now)
        timestamp = _utc_iso(now)
        with self._connect() as conn:
            for url, title in links:
                conn.execute(
                    "INSERT INTO medical_discovery_urls("
                    "source_id, url, title, first_seen_at, last_seen_at"
                    ") VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(source_id, url) DO UPDATE SET "
                    "title=excluded.title, last_seen_at=excluded.last_seen_at",
                    (source_id, url, title, timestamp, timestamp),
                )

    def due_urls(
        self,
        source_id: str,
        *,
        now: datetime,
        success_recheck_minutes: int = 1440,
        failure_base_minutes: int = 15,
        max_failure_backoff_minutes: int = 240,
        limit: int = 30,
    ) -> list[str]:
        _require_aware(now)
        if limit < 1 or limit > 100:
            raise ValueError("limit must be 1..100")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT url, last_attempt_at, last_success_at, consecutive_failures "
                "FROM medical_discovery_urls WHERE source_id=? ORDER BY first_seen_at DESC, url",
                (source_id,),
            ).fetchall()
        due: list[str] = []
        for url, last_attempt_raw, last_success_raw, failures in rows:
            last_attempt = _parse_time(last_attempt_raw)
            last_success = _parse_time(last_success_raw)
            if last_success is not None:
                next_due = last_success + timedelta(minutes=success_recheck_minutes)
            elif last_attempt is not None:
                backoff = min(
                    max_failure_backoff_minutes,
                    failure_base_minutes * (2 ** max(0, int(failures) - 1)),
                )
                next_due = last_attempt + timedelta(minutes=backoff)
            else:
                next_due = now
            if now >= next_due:
                due.append(str(url))
                if len(due) >= limit:
                    break
        return due

    def mark_success(self, source_id: str, url: str, *, now: datetime) -> None:
        timestamp = _utc_iso(now)
        with self._connect() as conn:
            conn.execute(
                "UPDATE medical_discovery_urls SET last_attempt_at=?, last_success_at=?, "
                "last_error_code=NULL, consecutive_failures=0 WHERE source_id=? AND url=?",
                (timestamp, timestamp, source_id, url),
            )

    def mark_failure(self, source_id: str, url: str, *, now: datetime, error_code: str) -> None:
        timestamp = _utc_iso(now)
        with self._connect() as conn:
            conn.execute(
                "UPDATE medical_discovery_urls SET last_attempt_at=?, last_error_code=?, "
                "consecutive_failures=consecutive_failures+1 WHERE source_id=? AND url=?",
                (timestamp, error_code[:120], source_id, url),
            )


def extract_registered_detail_links(source_id: str, listing_html: str) -> list[tuple[str, str]]:
    ready, reason = discovery_readiness(source_id)
    if not ready:
        raise ValueError(f"source discovery is not ready: {source_id}:{reason}")
    source = _source(source_id)
    adapter = adapter_for_source(source)
    discover = getattr(adapter, "discover", None)
    if not callable(discover):
        raise ValueError(f"source adapter has no discover() implementation: {source_id}")
    listing_url = DISCOVERY_READY_LISTINGS[source_id]
    raw_links = discover(listing_html, listing_url)
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for link in raw_links:
        if link.url in seen or not source.allows_url(link.url):
            continue
        seen.add(link.url)
        result.append((link.url, link.title))
    return result


def run_source_discovery_once(
    source_id: str,
    *,
    db_path: Path,
    now: datetime,
    max_details: int = 30,
    fetch_listing: Callable[[str], Snapshot] | None = None,
    ingest_detail: Callable[[str, Path], object] | None = None,
) -> DiscoveryRunResult:
    _require_aware(now)
    ready, reason = discovery_readiness(source_id)
    if not ready:
        raise ValueError(f"source discovery is not ready: {source_id}:{reason}")
    source = _source(source_id)
    listing_url = DISCOVERY_READY_LISTINGS[source_id]
    listing_urls = listing_pages_for_source(source_id)
    listing_hosts = {(urlparse(url).hostname or "").lower().strip(".") for url in listing_urls}
    if not listing_hosts or "" in listing_hosts:
        raise ValueError("listing URL has no host")

    if fetch_listing is None:
        fetcher = HostBoundFetcher(listing_hosts)
        fetch_listing = fetcher.fetch
    if ingest_detail is None:
        ingest_detail = lambda url, path: collect_and_persist_url(url, db_path=path)

    # All explicitly configured listing pages are required for this source run. Fetch
    # them before mutating the URL ledger so a partial list-page outage cannot be
    # recorded as a healthy source scan. Detail failures remain independently tracked.
    snapshots = [fetch_listing(url) for url in listing_urls]
    links: list[tuple[str, str]] = []
    seen_links: set[str] = set()
    for snapshot in snapshots:
        for url, title in extract_registered_detail_links(source_id, snapshot.text):
            if url in seen_links:
                continue
            seen_links.add(url)
            links.append((url, title))

    ledger = SQLiteDiscoveryUrlLedger(db_path)
    ledger.register(source_id, links, now=now)
    due = ledger.due_urls(source_id, now=now, limit=max_details)

    persisted = 0
    errors: list[dict[str, str]] = []
    for url in due:
        try:
            ingest_detail(url, db_path)
        except Exception as exc:  # boundary records sanitized class, not response body/content
            code = getattr(exc, "code", exc.__class__.__name__)
            ledger.mark_failure(source_id, url, now=now, error_code=str(code))
            errors.append({"url": url, "code": str(code)[:120]})
            continue
        ledger.mark_success(source_id, url, now=now)
        persisted += 1

    return DiscoveryRunResult(
        source_id=source_id,
        listing_url=listing_url,
        listing_urls=listing_urls,
        listing_page_count=len(listing_urls),
        discovered_count=len(links),
        due_count=len(due),
        attempted_count=len(due),
        persisted_count=persisted,
        failed_count=len(errors),
        skipped_not_due_count=max(0, len(links) - len(due)),
        errors=tuple(errors),
    )
