#!/usr/bin/env python3
"""Multi-market CCGP 中标/成交 result sync (北京/河北/辽宁/吉林/黑龙江).

Runs the shared award keyword plan once per market, sequentially, with the
same fail-closed rules as the Tianjin award sync (row geography must prove
the market, official detail required, scope filter, explicit amount units).
Designed for the self-hosted regional refresh workflow: no 300 s function
limit applies there, but every market still gets its own request budget so
one slow province cannot consume the whole run.

Outputs one merged AWARD_RESULT store and one combined report keyed by
market. Awards from a market whose discovery failed completely are simply
carried forward unchanged; the run never raises for network conditions.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from medical_channel_pipeline.ccgp_award import merge_award_records  # noqa: E402
from medical_channel_pipeline.validation import MARKET_ADMIN_CODES  # noqa: E402
from sync_ccgp_awards import (  # noqa: E402
    load_json_arrays,
    load_plan,
    parse_as_of,
    run_award_sync,
    write_json,
)

DEFAULT_PLAN = PIPELINE_ROOT / "data" / "regional_award_query_plan.json"
DEFAULT_POOL_RECORDS = PIPELINE_ROOT / "data" / "regional_live_ccgp_records.json"


def load_market_codes(path: Path) -> tuple[list[str], float | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("market_codes")
    if not isinstance(raw, list) or not raw:
        raise ValueError("REGIONAL_AWARD_PLAN_MARKET_CODES_INVALID")
    codes: list[str] = []
    for item in raw:
        code = str(item or "").strip().upper()
        if code not in MARKET_ADMIN_CODES:
            raise ValueError(f"REGIONAL_AWARD_PLAN_MARKET_CODE_INVALID:{code}")
        if code == "TJ":
            raise ValueError("REGIONAL_AWARD_PLAN_TIANJIN_HAS_ITS_OWN_PLAN")
        if code not in codes:
            codes.append(code)
    budget = payload.get("per_market_time_budget_seconds")
    if budget is not None:
        budget = float(budget)
        if budget < 30:
            raise ValueError("REGIONAL_AWARD_PLAN_TIME_BUDGET_TOO_LOW")
    return codes, budget


def run_regional_award_sync(
    *,
    plan_path: Path,
    as_of: datetime,
    existing_awards: list[dict],
    pool_records: list[dict],
    market_codes: list[str] | None = None,
    fetch_search=None,
    fetch_detail=None,
    sleep=time.sleep,
    clock=time.monotonic,
) -> tuple[list[dict], dict]:
    planned_codes, per_market_budget = load_market_codes(plan_path)
    codes = [code.strip().upper() for code in (market_codes or planned_codes)]
    unknown = [code for code in codes if code not in planned_codes]
    if unknown:
        raise ValueError(f"REGIONAL_AWARD_MARKET_NOT_IN_PLAN:{unknown}")

    merged = list(existing_awards)
    reports: dict[str, dict] = {}
    started = clock()
    for index, code in enumerate(codes):
        plan = load_plan(plan_path, market_code=code)
        market_pool = [
            record
            for record in pool_records
            if str((record.get("facts") or {}).get("market_code") or "").strip().upper() == code
        ]
        kwargs = {}
        if fetch_search is not None:
            kwargs["fetch_search"] = fetch_search
        if fetch_detail is not None:
            kwargs["fetch_detail"] = fetch_detail
        merged, report = run_award_sync(
            plan=plan,
            as_of=as_of,
            existing_awards=merged,
            pool_records=market_pool,
            time_budget_seconds=per_market_budget,
            sleep=sleep,
            clock=clock,
            **kwargs,
        )
        reports[code] = report
        if index + 1 < len(codes):
            sleep(plan["delay_seconds"])

    merged = merge_award_records([], merged)
    by_market: dict[str, int] = {}
    for record in merged:
        market = str(record["facts"].get("market_code") or "").strip().upper() or "UNKNOWN"
        by_market[market] = by_market.get(market, 0) + 1
    publish_allowed = any(item["publish_allowed"] for item in reports.values())
    combined = {
        "schema_version": "0.1",
        "record_type": "AWARD_RESULT",
        "observed_at": as_of.astimezone(timezone.utc).isoformat(),
        "market_codes": codes,
        "per_market_time_budget_seconds": per_market_budget,
        "elapsed_seconds": round(clock() - started, 3),
        "new_award_record_count": sum(item["new_award_record_count"] for item in reports.values()),
        "out_of_scope_count": sum(item["out_of_scope_count"] for item in reports.values()),
        "region_mismatch_count": sum(item["region_mismatch_count"] for item in reports.values()),
        "failure_count": sum(item["failure_count"] for item in reports.values()),
        "merged_award_record_count": len(merged),
        "merged_award_record_count_by_market": dict(sorted(by_market.items())),
        "markets_publish_allowed": {code: item["publish_allowed"] for code, item in reports.items()},
        "publish_allowed": publish_allowed,
        "publish_gate_reason": "OK" if publish_allowed else "ALL_MARKETS_AWARD_DISCOVERY_FAILED",
        "markets": reports,
        "policy": {
            "one_market_at_a_time_same_keyword_plan": True,
            "row_geography_must_prove_market": True,
            "previous_award_state_is_preserved": True,
            "network_failures_never_raise": True,
        },
    }
    return merged, combined


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-market CCGP 中标/成交 result sync -> AWARD_RESULT records.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--as-of", default=None, help="Optional ISO-8601 timestamp with timezone; defaults to now.")
    parser.add_argument("--market-code", action="append", default=[], help="Repeatable subset of the plan's market_codes.")
    parser.add_argument("--existing-awards-input", action="append", type=Path, default=[])
    parser.add_argument(
        "--records-input",
        action="append",
        type=Path,
        default=None,
        help="Opportunity records used only to report pool matches (defaults to the regional live store).",
    )
    parser.add_argument("--awards-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    args = parser.parse_args()

    as_of = parse_as_of(args.as_of)
    existing_awards = load_json_arrays(args.existing_awards_input, label="existing award records")
    record_paths = args.records_input if args.records_input is not None else (
        [DEFAULT_POOL_RECORDS] if DEFAULT_POOL_RECORDS.exists() else []
    )
    pool_records = load_json_arrays(record_paths, label="opportunity records")

    merged, report = run_regional_award_sync(
        plan_path=args.plan,
        as_of=as_of,
        existing_awards=existing_awards,
        pool_records=pool_records,
        market_codes=args.market_code or None,
    )
    write_json(args.awards_output, merged)
    write_json(args.report_output, report)
    for code, item in report["markets"].items():
        print(
            f"{code}: queries_ok={item['discovery_success_count']}/{item['planned_discovery_query_count']} "
            f"discovered={item['unique_discovered_result_count']} region_mismatch={item['region_mismatch_count']} "
            f"selected={item['selected_detail_count']} new_awards={item['new_award_record_count']} "
            f"out_of_scope={item['out_of_scope_count']} failures={item['failure_count']} "
            f"publish_allowed={item['publish_allowed']} elapsed={item['elapsed_seconds']}s"
        )
    print(
        f"merged={report['merged_award_record_count']} by_market={report['merged_award_record_count_by_market']} "
        f"publish_allowed={report['publish_allowed']} elapsed={report['elapsed_seconds']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
