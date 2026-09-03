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
    'from medical_channel_pipeline.tjfch_procurement import (  # noqa: E402\n'
    '    TjfchParseError,\n'
    '    parse_tjfch_procurement_notice,\n'
    ')\n'
    'from medical_channel_pipeline.teda_discovery import stable_opportunity_id as teda_opportunity_id  # noqa: E402\n',
    'from medical_channel_pipeline.tjfch_procurement import (  # noqa: E402\n'
    '    TjfchParseError,\n'
    '    parse_tjfch_procurement_notice,\n'
    ')\n'
    'from medical_channel_pipeline.tjfch_test_discovery import (  # noqa: E402\n'
    '    INDEX_URL as TJFCH_TEST_INDEX_URL,\n'
    '    parse_tjfch_test_index_html,\n'
    ')\n'
    'from medical_channel_pipeline.tjfch_test_recruitment import (  # noqa: E402\n'
    '    TjfchTestParseError,\n'
    '    parse_tjfch_test_recruitment,\n'
    ')\n'
    'from medical_channel_pipeline.teda_discovery import stable_opportunity_id as teda_opportunity_id  # noqa: E402\n',
    'imports',
)

replace_once(
    'TJFCH_LOOKBACK_DAYS = 45\n'
    'TJFCH_MAX_CANDIDATES = 20\n'
    'TJFCH_REQUEST_DELAY_SECONDS = 3.0\n',
    'TJFCH_LOOKBACK_DAYS = 45\n'
    'TJFCH_MAX_CANDIDATES = 20\n'
    'TJFCH_TEST_LOOKBACK_DAYS = 14\n'
    'TJFCH_TEST_MAX_CANDIDATES = 30\n'
    'TJFCH_REQUEST_DELAY_SECONDS = 3.0\n',
    'constants',
)

old_function = '''def _run_tjfch(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
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

new_function = '''def _run_tjfch(cache: RuntimeCache, state: dict[str, Any]) -> dict[str, Any]:
    as_of = _cycle_as_of(state)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=TJFCH_LOOKBACK_DAYS - 1)
    early_start_date = local_date - timedelta(days=TJFCH_TEST_LOOKBACK_DAYS - 1)
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
                        "feed": "in_hospital_procurement",
                        "title": candidate.title,
                        "url": candidate.detail_url,
                        "reason": str(exc),
                    }
                )
                continue
            failures.append(
                {
                    "stage": "verified_detail",
                    "feed": "in_hospital_procurement",
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
                    "feed": "in_hospital_procurement",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    try:
        early_index_html = fetch_tjfch_page(TJFCH_TEST_INDEX_URL)
        early_discovered = parse_tjfch_test_index_html(
            early_index_html,
            max_candidates=TJFCH_TEST_MAX_CANDIDATES,
        )
    except Exception as exc:
        raise CollectorStageBlocked(f"TJFCH_TEST_INDEX_DISCOVERY_FAILED:{type(exc).__name__}") from exc

    early_new_verified_record_count = 0
    early_out_of_window_count = 0
    for candidate in early_discovered:
        time.sleep(TJFCH_REQUEST_DELAY_SECONDS)
        try:
            detail_html = fetch_tjfch_page(candidate.detail_url)
            record = parse_tjfch_test_recruitment(
                detail_html,
                source_url=candidate.detail_url,
                index_url=TJFCH_TEST_INDEX_URL,
                expected_title=candidate.title,
                observed_at=observed_at,
                opportunity_id=tjfch_opportunity_id(candidate.detail_url),
            )
            published_at = datetime.fromisoformat(record["facts"]["published_at"]).date()
            if not early_start_date <= published_at <= local_date:
                early_out_of_window_count += 1
                continue
            new_records.append(record)
            early_new_verified_record_count += 1
        except TjfchTestParseError as exc:
            if str(exc) == "TJFCH_TEST_REGISTRATION_WINDOW_UNSUPPORTED":
                unsupported.append(
                    {
                        "feed": "pre_procurement_test_recruitment",
                        "title": candidate.title,
                        "url": candidate.detail_url,
                        "reason": str(exc),
                    }
                )
                continue
            failures.append(
                {
                    "stage": "verified_detail",
                    "feed": "pre_procurement_test_recruitment",
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
                    "feed": "pre_procurement_test_recruitment",
                    "title": candidate.title,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    # The two First Central Hospital feeds share one canonical cache state. Any
    # true fetch/parse inconsistency in either feed blocks the stage before the
    # combined state is written. Unsupported relative/exact-deadline formats are
    # explicit non-facts and never become invented public deadlines.
    if failures:
        diagnostic = ";".join(
            f"{item.get('feed')}:{item.get('error')}:{item.get('message')}"
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
        "new_verified_record_count": len(new_records) - early_new_verified_record_count,
        "early_discovered": len(early_discovered),
        "early_new_verified_record_count": early_new_verified_record_count,
        "early_out_of_window_count": early_out_of_window_count,
        "unsupported_candidate_count": len(unsupported),
        "merged_record_count": len(merged),
        "failure_count": 0,
        "bootstrapped_records": bootstrapped,
        "publish_gate_reason": "PASS",
    }
'''

replace_once(old_function, new_function, 'run-tjfch')
path.write_text(source, encoding='utf-8')
