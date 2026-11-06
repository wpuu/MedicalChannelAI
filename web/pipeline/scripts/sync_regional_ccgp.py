#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.cookiejar
import json
import math
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(PIPELINE_ROOT.parent))

from collector_diagnostics import failure_row  # noqa: E402

from medical_channel_pipeline.ccgp_detail import fetch_ccgp_detail_html  # noqa: E402
from medical_channel_pipeline.ccgp_discovery import (  # noqa: E402
    CCGP_SEARCH_URL,
    RATE_LIMIT_MARKERS,
    REGION_ZONE_IDS,
    build_search_url,
    is_primary_opportunity_candidate,
    parse_search_html,
)
from medical_channel_pipeline.regional_candidate import (  # noqa: E402
    regional_candidate_priority,
    regional_candidate_selection_key,
    regional_candidate_skip_reason,
)
from medical_channel_pipeline.state import merge_canonical_records  # noqa: E402
from sync_ccgp_query import (  # noqa: E402
    VERIFIED_NOTICE_ADAPTERS,
    load_json_arrays,
    stable_id,
    write_json,
)

DEFAULT_PLAN = PIPELINE_ROOT / 'data' / 'multi_region_query_plan.json'
SHANGHAI = ZoneInfo('Asia/Shanghai')
NATIONAL_FALLBACK_MAX_PAGES = 3
_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


class CliBudgetExceeded(RuntimeError):
    def __init__(self, phase: str) -> None:
        super().__init__('BUDGET_EXCEEDED')
        self.phase = phase


class CliBudget:
    """Cooperative admission checks; cannot preempt synchronous HTTP or file I/O."""
    def __init__(self, monotonic, sleep, *, total_seconds=900, work_seconds=840, started_at=None) -> None:
        now = monotonic()
        origin = now if started_at is None else started_at
        if not all(math.isfinite(v) for v in (now, origin, total_seconds, work_seconds)) or not (
            0 < work_seconds < total_seconds and origin <= now
        ):
            raise ValueError('COOPERATIVE_BUDGET_INVALID')
        self.clock, self.sleeper = monotonic, sleep
        self.started = origin
        self.total_seconds, self.work_seconds = total_seconds, work_seconds
        self.exhausted_phase = None
        self.work_complete = False

    def fail(self, phase: str) -> None:
        self.exhausted_phase = self.exhausted_phase or phase
        raise CliBudgetExceeded(self.exhausted_phase)

    def check(self, phase: str, *, finalize: bool = False) -> None:
        if (self.exhausted_phase and not finalize) or self.clock() >= self.started + (self.total_seconds if finalize else self.work_seconds):
            self.fail(phase)

    def request_timeout(self, cap: float, phase: str) -> float:
        self.check(phase)
        remaining = self.started + self.work_seconds - self.clock()
        if remaining <= 1:
            self.fail(phase)
        timeout = min(cap, remaining - 1)
        if not math.isfinite(timeout) or timeout <= 0:
            self.fail(phase)
        return timeout

    def sleep_checked(self, delay: float, phase: str) -> None:
        self.check(phase)
        if not math.isfinite(delay) or delay < 0 or self.started + self.work_seconds - self.clock() <= delay + 1:
            self.fail(phase)
        self.sleeper(delay)
        self.check(phase)

    def snapshot(self) -> dict:
        return {'total_seconds': self.total_seconds, 'work_seconds': self.work_seconds,
                'finalize_reserve_seconds': self.total_seconds - self.work_seconds,
                'elapsed_seconds': max(0, self.clock() - self.started),
                'exhausted_phase': self.exhausted_phase, 'work_complete': self.work_complete,
                'hard_exit_guaranteed': False}


class CcgpSearchSession:
    def __init__(self, *, on_access_blocked=None, budget=None) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.warmed = False
        self.on_access_blocked = on_access_blocked
        self.budget = budget

    def _read(self, url: str, *, timeout: int) -> str:
        budget = self.budget
        phase = 'WARMUP' if url == 'https://www.ccgp.gov.cn/' else 'SEARCH_READ'
        if budget:
            timeout = budget.request_timeout(timeout, phase)
        request = urllib.request.Request(url, headers=_BROWSER_HEADERS)
        with self.opener.open(request, timeout=timeout) as response:
            if budget:
                budget.check(phase)
            raw = response.read()
            if budget:
                budget.check(phase)
            charset = response.headers.get_content_charset()
        if budget:
            budget.check(phase)
        if charset:
            html = raw.decode(charset, errors='replace')
        else:
            for candidate in ('utf-8', 'gb18030'):
                try:
                    html = raw.decode(candidate)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                html = raw.decode('utf-8', errors='replace')
        if budget:
            budget.check(phase)
        return html

    def warmup(self) -> None:
        if self.warmed:
            return
        try:
            html = self._read('https://www.ccgp.gov.cn/', timeout=30)
            if self.on_access_blocked and any(marker in html for marker in RATE_LIMIT_MARKERS):
                self.on_access_blocked('www.ccgp.gov.cn', 'RATE_LIMITED')
        except CliBudgetExceeded:
            raise
        except Exception as exc:
            # Search can still work if the homepage warm-up is temporarily unavailable.
            # CLI-only feedback prevents later detail requests to a denied host.
            if self.on_access_blocked:
                reason = access_block_reason('index_discovery', exc, 'ccgp_homepage')
                if reason:
                    self.on_access_blocked('www.ccgp.gov.cn', reason)
        if self.budget:
            self.budget.check('WARMUP')
            self.budget.sleep_checked(1.0, 'WARMUP_SLEEP')
        else:
            time.sleep(1.0)
        self.warmed = True

    def fetch(self, url: str) -> str:
        if not url.startswith(CCGP_SEARCH_URL):
            raise ValueError('CCGP_SEARCH_URL_REQUIRED')
        self.warmup()
        if self.budget:
            self.budget.check('SEARCH_READ')
        html = self._read(url, timeout=90)
        if any(marker in html for marker in RATE_LIMIT_MARKERS):
            raise RuntimeError('CCGP_RATE_LIMITED')
        return html


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('--as-of must include timezone')
    return parsed


def load_plan(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema_version') != '0.1':
        raise ValueError('MULTI_REGION_QUERY_PLAN_INVALID')
    markets = payload.get('markets')
    if not isinstance(markets, list) or not markets:
        raise ValueError('MULTI_REGION_MARKETS_REQUIRED')

    seen_codes: set[str] = set()
    for market in markets:
        if not isinstance(market, dict):
            raise ValueError('MULTI_REGION_MARKET_INVALID')
        code = str(market.get('market_code') or '').strip().upper()
        name = str(market.get('name') or '').strip()
        admin_code = str(market.get('admin_code') or '').strip()
        zone_id = str(market.get('ccgp_zone_id') or '').strip()
        if code in seen_codes or not code or not name or len(admin_code) != 6:
            raise ValueError(f'MULTI_REGION_MARKET_INVALID:{market}')
        if REGION_ZONE_IDS.get(name) != zone_id:
            raise ValueError(f'MULTI_REGION_ZONE_MISMATCH:{name}:{zone_id}')
        if admin_code[:2] != zone_id:
            raise ValueError(f'MULTI_REGION_ADMIN_CODE_MISMATCH:{name}:{admin_code}:{zone_id}')
        seen_codes.add(code)

    keywords = payload.get('keywords')
    notice_types = payload.get('notice_types')
    if not isinstance(keywords, list) or not keywords or not all(isinstance(item, str) and item.strip() for item in keywords):
        raise ValueError('MULTI_REGION_KEYWORDS_INVALID')
    if not isinstance(notice_types, list) or not notice_types:
        raise ValueError('MULTI_REGION_NOTICE_TYPES_INVALID')
    if any(item not in VERIFIED_NOTICE_ADAPTERS for item in notice_types):
        raise ValueError('MULTI_REGION_NOTICE_TYPE_UNSUPPORTED')

    lookback_days = int(payload.get('lookback_days', 3))
    max_candidates = int(payload.get('max_candidates_per_market', 10))
    delay_seconds = float(payload.get('delay_seconds', 4.0))
    if not 1 <= lookback_days <= 14:
        raise ValueError('MULTI_REGION_LOOKBACK_INVALID')
    if not 1 <= max_candidates <= 30:
        raise ValueError('MULTI_REGION_MAX_CANDIDATES_INVALID')
    if delay_seconds < 3:
        raise ValueError('MULTI_REGION_DELAY_TOO_LOW')

    return {
        'markets': markets,
        'keywords': [item.strip() for item in keywords],
        'notice_types': list(notice_types),
        'lookback_days': lookback_days,
        'max_candidates_per_market': max_candidates,
        'delay_seconds': delay_seconds,
    }


def date_window(as_of: datetime, lookback_days: int) -> tuple[str, str]:
    local_date = as_of.astimezone(SHANGHAI).date()
    return (local_date - timedelta(days=lookback_days - 1)).isoformat(), local_date.isoformat()


def annotate_market(record: dict, market: dict) -> dict:
    facts = record.setdefault('facts', {})
    facts['market_code'] = str(market['market_code']).strip().upper()
    facts['market_name'] = str(market['name']).strip()
    facts['market_admin_code'] = str(market['admin_code']).strip()
    return record


def candidate_market_code(region: str | None, markets: list[dict]) -> str | None:
    normalized = ''.join(str(region or '').split())
    if not normalized:
        return None
    for market in markets:
        name = str(market['name']).strip()
        aliases = {name, f'{name}省', f'{name}市'}
        if normalized in aliases or any(normalized.startswith(alias) for alias in aliases):
            return str(market['market_code']).strip().upper()
    return None


def fetch_candidates_page(
    session: CcgpSearchSession,
    *,
    keyword: str,
    notice_type: str,
    start_date: str,
    end_date: str,
    region: str | None,
    page_index: int,
) -> list[tuple[str, object]]:
    url = build_search_url(
        keyword=keyword,
        notice_type=notice_type,
        page_index=page_index,
        start_date=start_date,
        end_date=end_date,
        region=region,
    )
    html = session.fetch(url)
    return [
        (notice_type, candidate)
        for candidate in parse_search_html(html, keyword=keyword)
        if is_primary_opportunity_candidate(candidate)
    ]


def paths_alias(left: Path, right: Path) -> bool:
    # resolve catches relative/symlink aliases, samefile also catches hard links.
    return left.resolve() == right.resolve() or (
        left.exists() and right.exists() and left.samefile(right)
    )


def access_block_reason(phase: str, exc: Exception, reference: str) -> str | None:
    # Reuse the runtime's fixed-code classifier, including detail fetch wrappers.
    cause = exc
    for _ in range(6):
        reason = failure_row(phase, cause, reference)['reason']
        if reason in {'RATE_LIMITED', 'HTTP_401', 'HTTP_403', 'HTTP_429',
                      'CCGP_DETAIL_HTTP_401', 'CCGP_DETAIL_HTTP_403', 'CCGP_DETAIL_HTTP_429'}:
            return reason
        if cause.__cause__ is None:
            break
        cause = cause.__cause__
    return None


def finish_cli_outputs(records_target: Path, report_path: Path, records: list, report: dict, budget: CliBudget) -> int:
    """Prepare before replacing one target; never claims a cross-file transaction."""
    stage = None
    report.update(commit_state='NOT_COMMITTED', records_written=False, post_commit_overrun=False)
    if report['acceptance_ready']:
        try:
            budget.check('FINALIZE', finalize=True)
            records_target.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.regional-ccgp-', suffix='.json', dir=records_target.parent)
            stage = Path(name)
            os.close(fd)
            write_json(stage, records)
            budget.check('PRE_COMMIT', finalize=True)
            report.update(commit_state='COMMIT_UNKNOWN', records_written=None)
            os.replace(stage, records_target)
            report.update(commit_state='COMMITTED', records_written=True)
            budget.check('POST_COMMIT', finalize=True)
        except CliBudgetExceeded:
            report['acceptance_ready'] = False
            report['acceptance_blockers'].append('BUDGET_EXCEEDED')
            report['post_commit_overrun'] = report['commit_state'] == 'COMMITTED'
        except Exception:
            report['acceptance_ready'] = False
            report['acceptance_blockers'].append(
                'COMMIT_RESULT_UNKNOWN' if report['commit_state'] == 'COMMIT_UNKNOWN' else 'OUTPUT_PREPARATION_FAILED')
        finally:
            if stage is not None:
                try:
                    stage.unlink(missing_ok=True)
                except OSError:
                    report['acceptance_ready'] = False
                    report['acceptance_blockers'].append('TEMPORARY_CLEANUP_FAILED')

    def emit_status() -> None:
        print(json.dumps({'commit_state': report['commit_state'], 'records_written': report['records_written'],
                          'acceptance_ready': report['acceptance_ready'],
                          'post_commit_overrun': report['post_commit_overrun'],
                          'acceptance_blockers': report['acceptance_blockers'], 'budget': budget.snapshot()}), file=sys.stderr)

    try:
        report['budget'] = budget.snapshot()
        write_json(report_path, report)
        try:
            budget.check('REPORT', finalize=True)
        except CliBudgetExceeded:
            report['acceptance_ready'] = False
            report['post_commit_overrun'] = report['commit_state'] == 'COMMITTED'
            if 'BUDGET_EXCEEDED' not in report['acceptance_blockers']:
                report['acceptance_blockers'].append('BUDGET_EXCEEDED')
            report['budget'] = budget.snapshot()
            # One correction of a now-known late report, never an unbounded retry.
            write_json(report_path, report)
    except Exception:
        report['acceptance_ready'] = False
        try:
            budget.check('REPORT', finalize=True)
        except CliBudgetExceeded:
            report['post_commit_overrun'] = report['records_written'] is True
        if report['records_written'] is True:
            report['commit_state'] = 'COMMITTED_REPORTING_INCOMPLETE'
        report['acceptance_blockers'].append('OUTPUT_REPORT_FAILED')
    if not report['acceptance_ready']:
        emit_status()
        return 2 if report['commit_state'] == 'NOT_COMMITTED' else 3
    return 0


def main(*, monotonic=None, sleep=None, detail_transport=fetch_ccgp_detail_html) -> int:
    budget = CliBudget(monotonic or time.monotonic, sleep or time.sleep)
    parser = argparse.ArgumentParser(
        description='Verified CCGP refresh for Beijing, Hebei, Liaoning, Jilin and Heilongjiang.'
    )
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    parser.add_argument('--as-of', default=None)
    parser.add_argument('--existing-records-input', action='append', type=Path, default=[])
    parser.add_argument('--records-output', required=True, type=Path)
    parser.add_argument('--report-output', required=True, type=Path)
    args = parser.parse_args()

    if any(paths_alias(args.report_output, path) for path in (
        args.plan, args.records_output, *args.existing_records_input
    )):
        parser.error('REPORT_OUTPUT_MUST_NOT_OVERWRITE_INPUT_OR_RECORDS')
    if paths_alias(args.records_output, args.plan):
        parser.error('RECORDS_OUTPUT_MUST_NOT_OVERWRITE_PLAN')
    records_target = args.records_output.resolve()

    plan = load_plan(args.plan)
    as_of = parse_as_of(args.as_of)
    start_date, end_date = date_window(as_of, plan['lookback_days'])
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records = load_json_arrays(args.existing_records_input, label='existing regional records')
    existing_source_urls = {
        str((record.get('source') or {}).get('url') or '')
        for record in existing_records
        if isinstance(record, dict) and str((record.get('source') or {}).get('url') or '')
    }
    blocked_hosts: dict[str, str] = {}

    def work_admitted(phase: str) -> bool:
        try:
            budget.check(phase)
            return True
        except CliBudgetExceeded:
            return False

    def sleep_work(delay: float, phase: str) -> None:
        if not budget.exhausted_phase:
            try:
                budget.sleep_checked(delay, phase)
            except CliBudgetExceeded:
                pass

    input_admitted = work_admitted('INPUT_PREPARATION')
    if input_admitted:
        try:
            budget.request_timeout(90, 'INPUT_PREPARATION')
        except CliBudgetExceeded:
            input_admitted = False
    session = CcgpSearchSession(on_access_blocked=blocked_hosts.setdefault, budget=budget) if input_admitted else None
    search_host = urlsplit(CCGP_SEARCH_URL).hostname

    markets = plan['markets']
    market_by_code = {str(item['market_code']).upper(): item for item in markets}
    market_candidates: dict[str, dict[str, tuple[str, object]]] = {
        code: {} for code in market_by_code
    }
    market_failures: dict[str, list[dict]] = {code: [] for code in market_by_code}
    market_skips: dict[str, dict[str, dict]] = {code: {} for code in market_by_code}
    scoped_success: dict[str, int] = {code: 0 for code in market_by_code}
    scoped_access_skips: dict[str, int] = {code: 0 for code in market_by_code}
    detail_access_skips: dict[str, int] = {code: 0 for code in market_by_code}
    scoped_budget_skips: dict[str, int] = {code: 0 for code in market_by_code}
    detail_budget_skips: dict[str, int] = {code: 0 for code in market_by_code}

    def record_candidate_skip(code: str, notice_type: str, candidate: object, reason: str) -> None:
        detail_url = str(getattr(candidate, 'detail_url', '') or '')
        if not detail_url:
            return
        market_skips[code].setdefault(detail_url, {
            'stage': 'candidate_classification',
            'market_code': code,
            'reason': reason,
            'notice_type': notice_type,
            'candidate_notice_type': getattr(candidate, 'notice_type', None),
            'candidate_region': getattr(candidate, 'region', None),
            'title': getattr(candidate, 'title', None),
            'url': detail_url,
        })
    scoped_region_mismatches: dict[str, int] = {code: 0 for code in market_by_code}

    # Province-scoped search is only discovery. Do not trust the request parameter
    # as proof of geography: every returned row must independently carry an official
    # region label that maps back to the requested market before it can be selected.
    for market in markets:
        code = str(market['market_code']).upper()
        name = str(market['name'])
        for keyword in plan['keywords']:
            for notice_type in plan['notice_types']:
                if not work_admitted('SCOPED_DISCOVERY'):
                    scoped_budget_skips[code] += 1
                    continue
                if search_host in blocked_hosts:
                    scoped_access_skips[code] += 1
                    continue
                try:
                    budget.request_timeout(90, 'SCOPED_DISCOVERY')
                    items = fetch_candidates_page(
                        session,
                        keyword=keyword,
                        notice_type=notice_type,
                        start_date=start_date,
                        end_date=end_date,
                        region=name,
                        page_index=1,
                    )
                    budget.check('SCOPED_PARSE')
                    for item_notice_type, candidate in items:
                        actual_code = candidate_market_code(getattr(candidate, 'region', None), markets)
                        if actual_code != code:
                            scoped_region_mismatches[code] += 1
                            continue
                        skip_reason = regional_candidate_skip_reason(candidate)
                        if skip_reason:
                            record_candidate_skip(code, item_notice_type, candidate, skip_reason)
                            continue
                        market_candidates[code].setdefault(
                            candidate.detail_url,
                            (item_notice_type, candidate),
                        )
                    budget.check('SCOPED_PARSE')
                    scoped_success[code] += 1
                except CliBudgetExceeded:
                    scoped_budget_skips[code] += 1
                except Exception as exc:
                    reason = access_block_reason('scoped_discovery', exc, f'{code}:{keyword}:{notice_type}')
                    if reason:
                        blocked_hosts.setdefault(search_host, reason)
                    market_failures[code].append({
                        'stage': 'scoped_discovery',
                        'market_code': code,
                        'region': name,
                        'keyword': keyword,
                        'notice_type': notice_type,
                        'error': type(exc).__name__,
                        'message': str(exc)[:300],
                    })
                if search_host not in blocked_hosts:
                    sleep_work(plan['delay_seconds'], 'SCOPED_SLEEP')

    empty_codes = {code for code, items in market_candidates.items() if not items}
    fallback_query_success = 0
    fallback_failures: list[dict] = []
    fallback_attempted = False
    fallback_access_blocked = False
    fallback_budget_blocked = False

    # If province-scoped search produces no region-verified candidate for a market,
    # fall back to a bounded national search and distribute rows solely by the
    # official region label on each result. Search rows remain discovery-only;
    # publication still requires parsing the official detail page.
    if empty_codes:
        for keyword in plan['keywords']:
            for notice_type in plan['notice_types']:
                for page_index in range(1, NATIONAL_FALLBACK_MAX_PAGES + 1):
                    if not work_admitted('FALLBACK_DISCOVERY'):
                        fallback_budget_blocked = True
                        break
                    if search_host in blocked_hosts:
                        fallback_access_blocked = True
                        break
                    try:
                        budget.request_timeout(90, 'FALLBACK_DISCOVERY')
                        fallback_attempted = True
                        items = fetch_candidates_page(
                            session,
                            keyword=keyword,
                            notice_type=notice_type,
                            start_date=start_date,
                            end_date=end_date,
                            region=None,
                            page_index=page_index,
                        )
                        budget.check('FALLBACK_PARSE')
                        fallback_query_success += 1
                    except CliBudgetExceeded:
                        fallback_budget_blocked = True
                        break
                    except Exception as exc:
                        reason = access_block_reason('national_fallback_discovery', exc, f'{keyword}:{notice_type}:{page_index}')
                        if reason:
                            blocked_hosts.setdefault(search_host, reason)
                            fallback_access_blocked = True
                        fallback_failures.append({
                            'stage': 'national_fallback_discovery',
                            'keyword': keyword,
                            'notice_type': notice_type,
                            'page_index': page_index,
                            'error': type(exc).__name__,
                            'message': str(exc)[:300],
                        })
                        break
                    if not items:
                        break
                    for item_notice_type, candidate in items:
                        actual_code = candidate_market_code(getattr(candidate, 'region', None), markets)
                        if actual_code not in empty_codes:
                            continue
                        skip_reason = regional_candidate_skip_reason(candidate)
                        if skip_reason:
                            record_candidate_skip(actual_code, item_notice_type, candidate, skip_reason)
                            continue
                        market_candidates[actual_code].setdefault(
                            candidate.detail_url,
                            (item_notice_type, candidate),
                        )
                    sleep_work(plan['delay_seconds'], 'FALLBACK_SLEEP')
                if search_host not in blocked_hosts:
                    sleep_work(plan['delay_seconds'], 'FALLBACK_SLEEP')

    new_records: list[dict] = []
    market_reports: list[dict] = []

    for code, discovered_by_url in market_candidates.items():
        market = market_by_code[code]
        discovered = sorted(
            discovered_by_url.values(),
            key=lambda item: regional_candidate_selection_key(item[1], existing_source_urls),
            reverse=True,
        )
        selected = discovered[: plan['max_candidates_per_market']]
        selected_candidates = [
            {
                'title': getattr(candidate, 'title', None),
                'url': getattr(candidate, 'detail_url', None),
                'published_at': getattr(candidate, 'published_at', None),
                'priority': regional_candidate_priority(candidate),
                'was_existing_verified_url': str(getattr(candidate, 'detail_url', '') or '') in existing_source_urls,
            }
            for _, candidate in selected
        ]
        market_new_count = 0

        for notice_type, candidate in selected:
            if not work_admitted('DETAIL'):
                detail_budget_skips[code] += 1
                continue
            detail_host = urlsplit(candidate.detail_url).hostname
            if detail_host in blocked_hosts:
                detail_access_skips[code] += 1
                continue
            # Final geography guard immediately before detail verification.
            if candidate_market_code(getattr(candidate, 'region', None), markets) != code:
                market_failures[code].append({
                    'stage': 'pre_detail_market_guard',
                    'market_code': code,
                    'candidate_region': getattr(candidate, 'region', None),
                    'url': getattr(candidate, 'detail_url', None),
                })
                continue
            try:
                budget.sleep_checked(plan['delay_seconds'], 'DETAIL_SLEEP')
                fetch_ccgp_detail_html = partial(detail_transport, timeout_seconds=budget.request_timeout(30, 'DETAIL_READ'))
                html = fetch_ccgp_detail_html(candidate.detail_url)
                budget.check('DETAIL_READ')
                if any(marker in html for marker in RATE_LIMIT_MARKERS):
                    raise RuntimeError('CCGP_RATE_LIMITED')
                record = VERIFIED_NOTICE_ADAPTERS[notice_type](
                    html,
                    source_url=candidate.detail_url,
                    observed_at=observed_at,
                    opportunity_id=stable_id(f'ccgp_{code.lower()}', candidate.detail_url),
                )
                budget.check('DETAIL_PARSE')
                new_records.append(annotate_market(record, market))
                market_new_count += 1
            except CliBudgetExceeded:
                detail_budget_skips[code] += 1
            except Exception as exc:
                reason = access_block_reason('verified_detail', exc, candidate.detail_url)
                if reason:
                    blocked_hosts.setdefault(detail_host, reason)
                market_failures[code].append({
                    'stage': 'verified_detail',
                    'market_code': code,
                    'region': market['name'],
                    'notice_type': notice_type,
                    'candidate_region': getattr(candidate, 'region', None),
                    'title': getattr(candidate, 'title', None),
                    'url': getattr(candidate, 'detail_url', None),
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                })

        market_reports.append({
            'market_code': code,
            'market_name': market['name'],
            'admin_code': market['admin_code'],
            'ccgp_zone_id': market['ccgp_zone_id'],
            'scoped_query_success_count': scoped_success[code],
            'scoped_region_mismatch_count': scoped_region_mismatches[code],
            'national_fallback_used': code in empty_codes and fallback_attempted,
            'scoped_queries_skipped_due_to_access': scoped_access_skips[code],
            'details_skipped_due_to_access': detail_access_skips[code],
            'scoped_queries_skipped_due_to_budget': scoped_budget_skips[code],
            'details_skipped_due_to_budget': detail_budget_skips[code],
            'skipped_candidate_count': len(market_skips[code]),
            'skipped_candidates': sorted(market_skips[code].values(), key=lambda item: (item['reason'], item['url'])),
            'unique_candidate_count': len(discovered),
            'selected_candidate_count': len(selected),
            'selected_unseen_candidate_count': sum(
                1 for item in selected_candidates if not item['was_existing_verified_url']
            ),
            'selected_existing_candidate_count': sum(
                1 for item in selected_candidates if item['was_existing_verified_url']
            ),
            'selected_candidates': selected_candidates,
            'new_verified_record_count': market_new_count,
            'failure_count': len(market_failures[code]),
            'failures': market_failures[code],
        })
        print(
            f'market={code} scoped_ok={scoped_success[code]} '
            f'scoped_mismatch={scoped_region_mismatches[code]} fallback={code in empty_codes} '
            f'candidates={len(discovered)} selected={len(selected)} verified={market_new_count} '
            f'failures={len(market_failures[code])}'
        )

    budget.work_complete = work_admitted('WORK_COMPLETE') and not (
        any(market_failures.values()) or fallback_failures or
        sum(scoped_access_skips.values()) or sum(detail_access_skips.values()) or fallback_access_blocked)
    finalize_failure = None
    merged_records = existing_records
    if not budget.exhausted_phase:
        try:
            budget.check('FINALIZE', finalize=True)
            merged_records = merge_canonical_records(existing_records, new_records)
            budget.check('FINALIZE', finalize=True)
        except CliBudgetExceeded:
            pass
        except Exception:
            finalize_failure = 'FINALIZE_MERGE_FAILED'
    acceptance_blockers = sorted({
        failure['stage']
        for failures in market_failures.values()
        for failure in failures
    } | {failure['stage'] for failure in fallback_failures})
    if sum(scoped_success.values()) + fallback_query_success <= 0:
        acceptance_blockers.append('ALL_MULTI_REGION_DISCOVERY_QUERIES_FAILED')
    if sum(scoped_access_skips.values()) or sum(detail_access_skips.values()) or fallback_access_blocked:
        acceptance_blockers.append('ACCESS_BLOCKED_SCAN_INCOMPLETE')
    if budget.exhausted_phase:
        acceptance_blockers.append('BUDGET_EXCEEDED')
    if finalize_failure:
        acceptance_blockers.append(finalize_failure)
    acceptance_ready = not acceptance_blockers
    report = {
        'schema_version': '0.1',
        # Completeness of this configured bounded scan, not full historical recall
        # or independent per-market commits/watermarks.
        'acceptance_scope': 'CONFIGURED_BOUNDED_REGIONAL_SCAN',
        'acceptance_ready': acceptance_ready,
        'acceptance_blockers': acceptance_blockers,
        'records_written': acceptance_ready,
        'access_blocked_hosts': blocked_hosts,
        'scoped_queries_skipped_due_to_access': sum(scoped_access_skips.values()),
        'details_skipped_due_to_access': sum(detail_access_skips.values()),
        'national_fallback_access_blocked': fallback_access_blocked,
        'scoped_queries_skipped_due_to_budget': sum(scoped_budget_skips.values()),
        'details_skipped_due_to_budget': sum(detail_budget_skips.values()),
        'national_fallback_budget_blocked': fallback_budget_blocked,
        'observed_at': observed_at,
        'start_date': start_date,
        'end_date': end_date,
        'markets': market_reports,
        'national_fallback_query_success_count': fallback_query_success,
        'national_fallback_failure_count': len(fallback_failures),
        'national_fallback_failures': fallback_failures,
        'existing_record_count': len(existing_records),
        'new_verified_record_count': len(new_records),
        'merged_record_count': len(merged_records),
        'policy': {
            'business_market_is_explicit_not_geolocated': True,
            'market_admin_codes_are_validated_against_configured_ccgp_zone': True,
            'scoped_query_parameter_is_not_geography_evidence': True,
            'every_candidate_requires_official_search_result_region_match': True,
            'scoped_empty_does_not_mean_no_market_activity': True,
            'national_fallback_uses_official_search_result_region_only': True,
            'national_fallback_max_pages_per_query': NATIONAL_FALLBACK_MAX_PAGES,
            'official_detail_required_before_publication': True,
            'candidate_prefilter_only_rejects_explicit_exclusions': True,
            'candidate_detail_budget_uses_recall_preserving_priority': True,
            'candidate_detail_budget_prioritizes_unseen_urls_before_rechecks': True,
            'cross_market_project_number_dedupe_is_forbidden': True,
            'regional_event_monitoring_deferred_until_composite_market_event_key_is_enabled': True,
            'rate_limit_bypass': False,
            'minimum_request_delay_seconds': plan['delay_seconds'],
        },
    }
    exit_code = finish_cli_outputs(records_target, args.report_output, merged_records, report, budget)
    print(
        f'markets={len(markets)} scoped_queries_ok={sum(scoped_success.values())} '
        f'fallback_queries_ok={fallback_query_success} new_verified={len(new_records)} '
        f'merged_records={len(merged_records)} acceptance_ready={report["acceptance_ready"]} '
        f'records_written={report["records_written"]} commit_state={report["commit_state"]}'
    )
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
