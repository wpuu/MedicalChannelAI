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
from medical_channel_pipeline.tjfch_test_discovery import (  # noqa: E402
    INDEX_URL,
    fetch_tjfch_page,
    parse_tjfch_test_index_html,
    stable_opportunity_id,
)
from medical_channel_pipeline.tjfch_test_recruitment import (  # noqa: E402
    TjfchTestParseError,
    parse_tjfch_test_recruitment,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
MIN_DETAIL_DELAY_SECONDS = 3.0
UNSUPPORTED_DETAIL_CODES = {"TJFCH_TEST_REGISTRATION_WINDOW_UNSUPPORTED"}


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync First Central Hospital pre-procurement test-enterprise recruitment signals.")
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--max-candidates", type=int, default=30)
    parser.add_argument("--delay-seconds", type=float, default=MIN_DETAIL_DELAY_SECONDS)
    parser.add_argument("--existing-records-input", action="append", type=Path, default=[])
    parser.add_argument("--records-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    args = parser.parse_args()

    if not 1 <= args.lookback_days <= 30:
        raise ValueError("--lookback-days must be between 1 and 30")
    if not 1 <= args.max_candidates <= 50:
        raise ValueError("--max-candidates must be between 1 and 50")
    if args.delay_seconds < MIN_DETAIL_DELAY_SECONDS:
        raise ValueError(f"--delay-seconds must be >= {MIN_DETAIL_DELAY_SECONDS:g}")

    as_of = parse_as_of(args.as_of)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=args.lookback_days - 1)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records = load_json_arrays(args.existing_records_input)

    try:
        index_html = fetch_tjfch_page(INDEX_URL)
        discovered = parse_tjfch_test_index_html(index_html, max_candidates=args.max_candidates)
    except Exception as exc:
        write_json(args.report_output, {
            "schema_version": "0.1",
            "observed_at": observed_at,
            "source": "TJFCH_TEST_ENTERPRISE_RECRUITMENT",
            "index_url": INDEX_URL,
            "publish_allowed": False,
            "publish_gate_reason": "INDEX_DISCOVERY_FAILED",
            "failure_count": 1,
            "failures": [{"stage": "index_discovery", "error": type(exc).__name__, "message": str(exc)[:300]}],
        })
        return 2

    new_records: list[dict] = []
    failures: list[dict] = []
    unsupported: list[dict] = []
    out_of_window_count = 0

    for candidate in discovered:
        time.sleep(args.delay_seconds)
        try:
            detail_html = fetch_tjfch_page(candidate.detail_url)
            record = parse_tjfch_test_recruitment(
                detail_html,
                source_url=candidate.detail_url,
                index_url=INDEX_URL,
                expected_title=candidate.title,
                observed_at=observed_at,
                opportunity_id=stable_opportunity_id(candidate.detail_url),
            )
            published = datetime.fromisoformat(record["facts"]["published_at"]).date()
            if not start_date <= published <= local_date:
                out_of_window_count += 1
                continue
            new_records.append(record)
        except TjfchTestParseError as exc:
            if str(exc) in UNSUPPORTED_DETAIL_CODES:
                unsupported.append({"title": candidate.title, "url": candidate.detail_url, "reason": str(exc)})
                continue
            failures.append({
                "stage": "verified_detail",
                "title": candidate.title,
                "url": candidate.detail_url,
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            })
        except Exception as exc:
            failures.append({
                "stage": "verified_detail",
                "title": candidate.title,
                "url": candidate.detail_url,
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            })

    publish_allowed = not failures
    reason = "PASS" if publish_allowed else "CANDIDATE_VERIFICATION_INCOMPLETE"
    merged = merge_canonical_records(existing_records, new_records) if publish_allowed else existing_records
    if publish_allowed:
        write_json(args.records_output, merged)

    write_json(args.report_output, {
        "schema_version": "0.1",
        "observed_at": observed_at,
        "source": "TJFCH_TEST_ENTERPRISE_RECRUITMENT",
        "index_url": INDEX_URL,
        "start_date": start_date.isoformat(),
        "end_date": local_date.isoformat(),
        "discovered_candidate_count": len(discovered),
        "new_verified_record_count": len(new_records),
        "out_of_window_count": out_of_window_count,
        "unsupported_candidate_count": len(unsupported),
        "existing_record_count": len(existing_records),
        "merged_record_count": len(merged),
        "failure_count": len(failures),
        "failures": failures,
        "unsupported": unsupported,
        "publish_allowed": publish_allowed,
        "publish_gate_reason": reason,
        "policy": {
            "official_ywgk_entry_required": True,
            "detail_publication_date_required": True,
            "url_path_date_is_not_publication_evidence": True,
            "relative_seven_day_window_never_published_as_official_deadline": True,
            "true_fetch_or_parse_failure_blocks_state_update": True,
            "rate_limit_bypass": False,
            "minimum_detail_delay_seconds": args.delay_seconds,
        },
    })
    return 0 if publish_allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
