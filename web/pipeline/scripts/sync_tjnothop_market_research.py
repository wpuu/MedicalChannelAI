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
from medical_channel_pipeline.tjnothop_discovery import (  # noqa: E402
    INDEX_URL,
    fetch_tjnothop_page,
    parse_tjnothop_index_html,
    select_candidates_since,
    stable_opportunity_id,
)
from medical_channel_pipeline.tjnothop_market_research import (  # noqa: E402
    parse_tjnothop_market_research,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
MIN_DETAIL_DELAY_SECONDS = 3.0


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
    new_verified_record_count: int,
) -> tuple[bool, str]:
    if not index_discovery_succeeded:
        return False, "INDEX_DISCOVERY_FAILED"
    if selected_candidate_count > 0 and new_verified_record_count <= 0:
        return False, "ALL_SELECTED_DETAILS_FAILED_VERIFICATION"
    return True, "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync supported Tianjin Hospital medical-equipment procurement research notices."
    )
    parser.add_argument("--as-of", default=None, help="ISO-8601 timestamp with timezone; defaults to now.")
    parser.add_argument("--lookback-days", type=int, default=21)
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--delay-seconds", type=float, default=MIN_DETAIL_DELAY_SECONDS)
    parser.add_argument("--existing-records-input", action="append", type=Path, default=[])
    parser.add_argument("--records-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    args = parser.parse_args()

    if not 1 <= args.lookback_days <= 60:
        raise ValueError("--lookback-days must be between 1 and 60")
    if not 1 <= args.max_candidates <= 50:
        raise ValueError("--max-candidates must be between 1 and 50")
    if args.delay_seconds < MIN_DETAIL_DELAY_SECONDS:
        raise ValueError(f"--delay-seconds must be >= {MIN_DETAIL_DELAY_SECONDS:g}")

    as_of = parse_as_of(args.as_of)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=args.lookback_days - 1)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records = load_json_arrays(args.existing_records_input)
    failures: list[dict] = []

    try:
        index_html = fetch_tjnothop_page(INDEX_URL)
        discovered = parse_tjnothop_index_html(index_html)
    except Exception as exc:
        report = {
            "schema_version": "0.1",
            "observed_at": observed_at,
            "source": "TJNOTHOP_NEWS_INDEX",
            "index_url": INDEX_URL,
            "publish_allowed": False,
            "publish_gate_reason": "INDEX_DISCOVERY_FAILED",
            "failure_count": 1,
            "failures": [
                {
                    "stage": "index_discovery",
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            ],
        }
        write_json(args.report_output, report)
        print("Tianjin Hospital index discovery failed; refusing to mark source state fresh", file=sys.stderr)
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
            if not candidate.published_at:
                raise ValueError("TJNOTHOP_INDEX_PUBLISHED_DATE_REQUIRED")
            detail_html = fetch_tjnothop_page(candidate.detail_url)
            record = parse_tjnothop_market_research(
                detail_html,
                source_url=candidate.detail_url,
                index_url=INDEX_URL,
                index_published_at=candidate.published_at,
                expected_title=candidate.title,
                observed_at=observed_at,
                opportunity_id=stable_opportunity_id(candidate.detail_url),
            )
            new_records.append(record)
        except Exception as exc:
            failures.append(
                {
                    "stage": "verified_detail",
                    "title": candidate.title,
                    "published_at": candidate.published_at,
                    "url": candidate.detail_url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    merged_records = merge_canonical_records(existing_records, new_records)
    publish_allowed, publish_gate_reason = publish_gate(
        index_discovery_succeeded=True,
        selected_candidate_count=len(selected),
        new_verified_record_count=len(new_records),
    )
    report = {
        "schema_version": "0.1",
        "observed_at": observed_at,
        "source": "TJNOTHOP_NEWS_INDEX",
        "index_url": INDEX_URL,
        "start_date": start_date.isoformat(),
        "end_date": local_date.isoformat(),
        "discovered_supported_count": len(discovered),
        "selected_candidate_count": len(selected),
        "new_verified_record_count": len(new_records),
        "existing_record_count": len(existing_records),
        "merged_record_count": len(merged_records),
        "failure_count": len(failures),
        "failures": failures,
        "publish_allowed": publish_allowed,
        "publish_gate_reason": publish_gate_reason,
        "policy": {
            "official_index_required": True,
            "only_standard_medical_equipment_procurement_research_titles": True,
            "index_and_detail_title_must_match": True,
            "published_date_requires_official_index_evidence": True,
            "date_only_deadline_never_invented_as_exact_time": True,
            "detail_must_pass_verified_parser": True,
            "failed_detail_never_replaces_existing_verified_record": True,
            "all_selected_details_failed_verification_blocks_publish": True,
            "rate_limit_bypass": False,
            "minimum_detail_delay_seconds": args.delay_seconds,
        },
    }
    write_json(args.records_output, merged_records)
    write_json(args.report_output, report)
    print(
        f"discovered={len(discovered)} selected={len(selected)} verified={len(new_records)} "
        f"records={len(merged_records)} failures={len(failures)} gate={publish_gate_reason}"
    )
    if not publish_allowed:
        print(f"Tianjin Hospital refresh publish blocked: {publish_gate_reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
