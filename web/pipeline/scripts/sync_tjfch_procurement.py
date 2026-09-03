#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline.state import merge_canonical_records  # noqa: E402
from medical_channel_pipeline.tjfch_discovery import (  # noqa: E402
    INDEX_URL,
    fetch_tjfch_page,
    parse_tjfch_index_html,
    select_candidates_since,
    stable_opportunity_id,
)
from medical_channel_pipeline.tjfch_procurement import (  # noqa: E402
    TjfchParseError,
    parse_tjfch_procurement_notice,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
MIN_DETAIL_DELAY_SECONDS = 3.0
UNSUPPORTED_DETAIL_CODES = {"TJFCH_NOTICE_TYPE_UNSUPPORTED"}


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--as-of must include timezone")
    return parsed


def load_json_arrays(paths: list[Path]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"input must contain a JSON array: {path}")
        records.extend(payload)
    return records


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish_gate(
    *,
    index_discovery_succeeded: bool,
    selected_candidate_count: int,
    unsupported_candidate_count: int,
    new_verified_record_count: int,
) -> tuple[bool, str]:
    if not index_discovery_succeeded:
        return False, "INDEX_DISCOVERY_FAILED"
    actionable_candidate_count = max(0, selected_candidate_count - unsupported_candidate_count)
    if actionable_candidate_count > 0 and new_verified_record_count <= 0:
        return False, "ALL_ACTIONABLE_DETAILS_FAILED_VERIFICATION"
    return True, "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync Tianjin First Central Hospital official in-hospital procurement notices."
    )
    parser.add_argument("--as-of", default=None, help="ISO-8601 timestamp with timezone; defaults to now.")
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--max-candidates", type=int, default=20)
    parser.add_argument("--delay-seconds", type=float, default=MIN_DETAIL_DELAY_SECONDS)
    parser.add_argument("--existing-records-input", action="append", type=Path, default=[])
    parser.add_argument("--records-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    args = parser.parse_args()

    if not 1 <= args.lookback_days <= 90:
        raise ValueError("--lookback-days must be between 1 and 90")
    if not 1 <= args.max_candidates <= 30:
        raise ValueError("--max-candidates must be between 1 and 30")
    if args.delay_seconds < MIN_DETAIL_DELAY_SECONDS:
        raise ValueError(f"--delay-seconds must be >= {MIN_DETAIL_DELAY_SECONDS:g}")

    as_of = parse_as_of(args.as_of)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=args.lookback_days - 1)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records = load_json_arrays(args.existing_records_input)
    failures: list[dict] = []
    unsupported: list[dict] = []

    try:
        index_html = fetch_tjfch_page(INDEX_URL)
        discovered = parse_tjfch_index_html(index_html)
    except Exception as exc:
        report = {
            "schema_version": "0.1",
            "observed_at": observed_at,
            "source": "TJFCH_IN_HOSPITAL_PROCUREMENT",
            "index_url": INDEX_URL,
            "publish_allowed": False,
            "publish_gate_reason": "INDEX_DISCOVERY_FAILED",
            "failure_count": 1,
            "failures": [{
                "stage": "index_discovery",
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            }],
        }
        write_json(args.report_output, report)
        print("TJFCH index discovery failed; refusing to mark source state fresh", file=sys.stderr)
        return 2

    selected = select_candidates_since(
        discovered,
        start_date=start_date,
        end_date=local_date,
        max_candidates=args.max_candidates,
    )
    new_records: list[dict] = []
    for candidate in selected:
        time.sleep(args.delay_seconds)
        try:
            detail_html = fetch_tjfch_page(candidate.detail_url)
            record = parse_tjfch_procurement_notice(
                detail_html,
                source_url=candidate.detail_url,
                index_url=INDEX_URL,
                index_published_at=candidate.published_at,
                expected_title=candidate.title,
                observed_at=observed_at,
                opportunity_id=stable_opportunity_id(candidate.detail_url),
            )
            new_records.append(record)
        except TjfchParseError as exc:
            if str(exc) in UNSUPPORTED_DETAIL_CODES:
                unsupported.append({
                    "title": candidate.title,
                    "published_at": candidate.published_at,
                    "url": candidate.detail_url,
                    "reason": str(exc),
                })
                continue
            failures.append({
                "stage": "verified_detail",
                "title": candidate.title,
                "published_at": candidate.published_at,
                "url": candidate.detail_url,
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            })
        except Exception as exc:
            failures.append({
                "stage": "verified_detail",
                "title": candidate.title,
                "published_at": candidate.published_at,
                "url": candidate.detail_url,
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            })

    merged_records = merge_canonical_records(existing_records, new_records)
    publish_allowed, publish_gate_reason = publish_gate(
        index_discovery_succeeded=True,
        selected_candidate_count=len(selected),
        unsupported_candidate_count=len(unsupported),
        new_verified_record_count=len(new_records),
    )
    report = {
        "schema_version": "0.1",
        "observed_at": observed_at,
        "source": "TJFCH_IN_HOSPITAL_PROCUREMENT",
        "index_url": INDEX_URL,
        "start_date": start_date.isoformat(),
        "end_date": local_date.isoformat(),
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "unsupported_candidate_count": len(unsupported),
        "existing_record_count": len(existing_records),
        "merged_record_count": len(merged_records),
        "failure_count": len(failures),
        "failures": failures,
        "unsupported": unsupported,
        "publish_allowed": publish_allowed,
        "publish_gate_reason": publish_gate_reason,
        "policy": {
            "official_procurement_index_required": True,
            "truncated_index_title_requires_full_detail_h1_verification": True,
            "result_and_award_notices_excluded": True,
            "ambiguous_result_detail_is_unsupported_not_opportunity": True,
            "index_and_detail_title_or_prefix_must_match": True,
            "detail_published_date_must_confirm_url_date": True,
            "exact_bid_deadline_required": True,
            "relative_workday_deadline_not_invented": True,
            "failed_detail_never_replaces_existing_verified_record": True,
            "all_actionable_details_failed_verification_blocks_publish": True,
            "rate_limit_bypass": False,
            "minimum_detail_delay_seconds": args.delay_seconds,
        },
    }
    write_json(args.records_output, merged_records)
    write_json(args.report_output, report)
    print(
        f"discovered={len(discovered)} selected={len(selected)} verified={len(new_records)} "
        f"unsupported={len(unsupported)} records={len(merged_records)} failures={len(failures)} gate={publish_gate_reason}"
    )
    if not publish_allowed:
        print(f"TJFCH refresh publish blocked: {publish_gate_reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
