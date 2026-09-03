from pathlib import Path

path = Path('web/collector_runtime.py')
source = path.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global source
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, got {count}')
    source = source.replace(old, new, 1)


replace_once(
    'from medical_channel_pipeline.state import (  # noqa: E402\n'
    '    active_ccgp_project_numbers,\n'
    '    merge_canonical_records,\n'
    '    merge_notice_events,\n'
    ')\n'
    'from medical_channel_pipeline.teda_discovery import stable_opportunity_id as teda_opportunity_id  # noqa: E402\n',
    'from medical_channel_pipeline.state import (  # noqa: E402\n'
    '    active_ccgp_project_numbers,\n'
    '    merge_canonical_records,\n'
    '    merge_notice_events,\n'
    ')\n'
    'from medical_channel_pipeline.tjfch_discovery import (  # noqa: E402\n'
    '    INDEX_URL as TJFCH_INDEX_URL,\n'
    '    fetch_tjfch_page,\n'
    '    parse_tjfch_index_html,\n'
    '    select_candidates_since as select_tjfch_candidates,\n'
    '    stable_opportunity_id as tjfch_opportunity_id,\n'
    ')\n'
    'from medical_channel_pipeline.tjfch_procurement import (  # noqa: E402\n'
    '    TjfchParseError,\n'
    '    parse_tjfch_procurement_notice,\n'
    ')\n'
    'from medical_channel_pipeline.teda_discovery import stable_opportunity_id as teda_opportunity_id  # noqa: E402\n',
    'imports',
)

replace_once(
    'TEDA_REQUEST_DELAY_SECONDS = 3.0\n\n'
    'META_KEY = "medicalchannelai:collector-runtime-state:v1"',
    'TEDA_REQUEST_DELAY_SECONDS = 3.0\n'
    'TJFCH_LOOKBACK_DAYS = 45\n'
    'TJFCH_MAX_CANDIDATES = 20\n'
    'TJFCH_REQUEST_DELAY_SECONDS = 3.0\n\n'
    'META_KEY = "medicalchannelai:collector-runtime-state:v1"',
    'constants',
)

replace_once(
    'TEDA_RECORDS_KEY = "medicalchannelai:collector-teda-records:v1"\n'
    'LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v1"',
    'TEDA_RECORDS_KEY = "medicalchannelai:collector-teda-records:v1"\n'
    'TJFCH_RECORDS_KEY = "medicalchannelai:collector-tjfch-records:v1"\n'
    'LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v1"',
    'cache-key',
)

replace_once(
    '    "tjnothop",\n'
    '    "teda",\n'
    '    "publish",\n',
    '    "tjnothop",\n'
    '    "teda",\n'
    '    "tjfch",\n'
    '    "publish",\n',
    'stage-order',
)

replace_once(
    '    "tjnothop": "20 2 * * *",\n'
    '    "teda": "35 2 * * *",\n'
    '    "publish": "50 2 * * *",\n',
    '    "tjnothop": "20 2 * * *",\n'
    '    "teda": "35 2 * * *",\n'
    '    "tjfch": "50 2 * * *",\n'
    '    "publish": "5 3 * * *",\n',
    'schedule-description',
)

replace_once(
    'def _bootstrap_teda_records() -> list[dict[str, Any]]:\n'
    '    return merge_canonical_records([], _load_array(DATA_ROOT / "tianjin_live_teda_records.json"))\n\n\n'
    'def _cached_list',
    'def _bootstrap_teda_records() -> list[dict[str, Any]]:\n'
    '    return merge_canonical_records([], _load_array(DATA_ROOT / "tianjin_live_teda_records.json"))\n\n\n'
    'def _bootstrap_tjfch_records() -> list[dict[str, Any]]:\n'
    '    return merge_canonical_records([], _load_array(DATA_ROOT / "tianjin_live_tjfch_records.json"))\n\n\n'
    'def _cached_list',
    'bootstrap',
)

marker = '\n\ndef _digest(value: Any) -> str:\n'
if source.count(marker) != 1:
    raise SystemExit('tjfch-function-marker mismatch')

tjfch_function = '''


def _run_tjfch(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    as_of = _cycle_as_of(state)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=TJFCH_LOOKBACK_DAYS - 1)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records, bootstrapped = _cached_list(cache, TJFCH_RECORDS_KEY, _bootstrap_tjfch_records)

    try:
        index_html = fetch_tjfch_page(TJFCH_INDEX_URL)
        discovered = parse_tjfch_index_html(index_html)
    except Exception as exc:
        raise CollectorStageBlocked(f"TJFCH_INDEX_DISCOVERY_FAILED:{type(exc).__name__}") from exc

    selected = select_tjfch_candidates(
        discovered,
        start_date=start_date,
        end_date=local_date,
        max_candidates=TJFCH_MAX_CANDIDATES,
    )
    new_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    for candidate in selected:
        time.sleep(TJFCH_REQUEST_DELAY_SECONDS)
        try:
            detail_html = fetch_tjfch_page(candidate.detail_url)
            new_records.append(
                parse_tjfch_procurement_notice(
                    detail_html,
                    source_url=candidate.detail_url,
                    index_url=TJFCH_INDEX_URL,
                    index_published_at=candidate.published_at,
                    expected_title=candidate.title,
                    observed_at=observed_at,
                    opportunity_id=tjfch_opportunity_id(candidate.detail_url),
                )
            )
        except TjfchParseError as exc:
            if str(exc) == "TJFCH_BID_DEADLINE_NOT_EXACT":
                unsupported.append(
                    {
                        "title": candidate.title,
                        "url": candidate.detail_url,
                        "reason": str(exc),
                    }
                )
                continue
            failures.append(
                {
                    "stage": "verified_detail",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "stage": "verified_detail",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    if failures:
        diagnostic = ";".join(
            f"{item.get('error')}:{item.get('message')}"
            for item in failures[:3]
        )
        raise CollectorStageBlocked(
            f"TJFCH_CANDIDATE_VERIFICATION_INCOMPLETE:{len(failures)}:{diagnostic}"
        )

    merged = merge_canonical_records(existing_records, new_records)
    _cache_set(cache, TJFCH_RECORDS_KEY, merged, tag="medicalchannelai-collector-canonical")
    return {
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "unsupported_candidate_count": len(unsupported),
        "merged_record_count": len(merged),
        "failure_count": 0,
        "bootstrapped_records": bootstrapped,
        "publish_gate_reason": "PASS",
    }
'''
source = source.replace(marker, tjfch_function + marker, 1)

replace_once(
    '    teda_records = cache.get(TEDA_RECORDS_KEY)\n'
    '    if not all(\n'
    '        isinstance(value, list)\n'
    '        for value in (ccgp_records, events, tjmugh_records, tjnothop_records, teda_records)\n'
    '    ):',
    '    teda_records = cache.get(TEDA_RECORDS_KEY)\n'
    '    tjfch_records = cache.get(TJFCH_RECORDS_KEY)\n'
    '    if not all(\n'
    '        isinstance(value, list)\n'
    '        for value in (ccgp_records, events, tjmugh_records, tjnothop_records, teda_records, tjfch_records)\n'
    '    ):',
    'publish-precondition',
)

replace_once(
    '    records = list(ccgp_records) + list(tjmugh_records) + list(tjnothop_records) + list(teda_records)\n',
    '    records = (\n'
    '        list(ccgp_records)\n'
    '        + list(tjmugh_records)\n'
    '        + list(tjnothop_records)\n'
    '        + list(teda_records)\n'
    '        + list(tjfch_records)\n'
    '    )\n',
    'publish-records',
)

replace_once(
    '        elif stage == "teda":\n'
    '            result = _run_teda(cache, state)\n'
    '        elif stage == "publish":',
    '        elif stage == "teda":\n'
    '            result = _run_teda(cache, state)\n'
    '        elif stage == "tjfch":\n'
    '            result = _run_tjfch(cache, state)\n'
    '        elif stage == "publish":',
    'dispatch',
)

path.write_text(source, encoding='utf-8')
