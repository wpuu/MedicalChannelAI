#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL_ID = "agnes-3.0-flash"
ALLOWED_LABELS = {
    "DIRECT_MATCH",
    "POSSIBLE_MATCH_NEEDS_CONFIRMATION",
    "NOT_MATCH",
}
MAX_ATTEMPTS = 2


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def api_keys() -> list[str]:
    raw = os.environ.get("AGNES_API_KEYS") or os.environ.get("AGNES_API_KEY") or ""
    return [item.strip() for item in raw.replace(";", ",").replace("\n", ",").split(",") if item.strip()]


def build_messages(profile: dict, opportunity: dict) -> list[dict[str, str]]:
    items = [
        {"id": str(item["id"]), "name": str(item["name"])}
        for item in profile.get("items", [])
        if isinstance(item, dict) and item.get("id") and item.get("name")
    ]
    allowed_ids = [item["id"] for item in items]
    payload = {
        "客户画像": {
            "profile_id": profile.get("profile_id"),
            "name": profile.get("name"),
            "items": items,
        },
        "机会事实": {
            "project_name": opportunity.get("project_name"),
            "product_categories": opportunity.get("product_categories") or [],
            "product_items": opportunity.get("product_items") or [],
        },
        "允许引用的客户产品ID": allowed_ids,
    }
    system = "\n".join(
        [
            "你是医疗渠道项目相关性分类器，只判断机会与客户明确产品范围的语义相关性。",
            "你没有事实创造权，也不能扩大客户经营范围。",
            "DIRECT_MATCH：公告产品与客户某个明确产品或非常明确的同类/子类直接对应。",
            "POSSIBLE_MATCH_NEEDS_CONFIRMATION：只有较宽泛的大类关系，不能确认客户实际经营该具体产品。",
            "NOT_MATCH：无产品重合；医院身份、金额大、医疗行业身份都不能单独构成相关。",
            "matched_profile_item_ids 只能从用户提供的允许ID中选择。",
            "NOT_MATCH 时 matched_profile_item_ids 必须为空数组。",
            "不得输出理由、解释、新产品名、日期、金额、资格、联系人或任何其他字段。",
            '{"classification":"DIRECT_MATCH","matched_profile_item_ids":["A1"]}',
        ]
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]


def parse_content(raw_text: str, allowed_ids: set[str]) -> dict[str, object]:
    cleaned = str(raw_text or "").strip()
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first < 0 or last <= first:
        raise ValueError("AGNES_RELEVANCE_JSON_NOT_FOUND")
    try:
        payload = json.loads(cleaned[first:last + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("AGNES_RELEVANCE_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("AGNES_RELEVANCE_JSON_INVALID")
    if set(payload) != {"classification", "matched_profile_item_ids"}:
        raise ValueError("AGNES_RELEVANCE_UNEXPECTED_FIELD")
    classification = str(payload.get("classification") or "").strip()
    if classification not in ALLOWED_LABELS:
        raise ValueError("AGNES_RELEVANCE_LABEL_INVALID")
    ids = payload.get("matched_profile_item_ids")
    if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
        raise ValueError("AGNES_RELEVANCE_IDS_INVALID")
    normalized = [item.strip() for item in ids if item.strip()]
    if len(normalized) != len(ids) or len(set(normalized)) != len(normalized):
        raise ValueError("AGNES_RELEVANCE_IDS_INVALID")
    if any(item not in allowed_ids for item in normalized):
        raise ValueError("AGNES_RELEVANCE_ID_NOT_GROUNDED")
    if classification == "NOT_MATCH" and normalized:
        raise ValueError("AGNES_RELEVANCE_NOT_MATCH_MUST_BE_EMPTY")
    if classification != "NOT_MATCH" and not normalized:
        raise ValueError("AGNES_RELEVANCE_MATCH_REQUIRES_ID")
    return {
        "classification": classification,
        "matched_profile_item_ids": normalized,
    }


def call_agnes(*, key: str, base_url: str, messages: list[dict[str, str]], timeout: int = 30) -> str:
    body = json.dumps(
        {
            "model": MODEL_ID,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 120,
            "stream": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"AGNES_HTTP_{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("AGNES_NETWORK_ERROR") from exc
    content = payload.get("choices", [{}])[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("AGNES_CONTENT_EMPTY")
    return content


def validate_dataset(payload: object) -> tuple[list[dict], list[dict]]:
    if not isinstance(payload, dict):
        raise ValueError("RELEVANCE_DATASET_INVALID")
    profiles = payload.get("profiles")
    opportunities = payload.get("opportunities")
    if not isinstance(profiles, list) or not profiles or not isinstance(opportunities, list) or not opportunities:
        raise ValueError("RELEVANCE_DATASET_INVALID")
    profile_ids = {str(item.get("profile_id") or "") for item in profiles if isinstance(item, dict)}
    if "" in profile_ids or len(profile_ids) != len(profiles):
        raise ValueError("RELEVANCE_PROFILE_ID_INVALID")
    for opportunity in opportunities:
        if not isinstance(opportunity, dict) or not opportunity.get("case_id"):
            raise ValueError("RELEVANCE_CASE_INVALID")
        expected = opportunity.get("expected")
        if not isinstance(expected, dict) or set(expected) != profile_ids:
            raise ValueError("RELEVANCE_EXPECTED_INVALID")
        if any(value not in ALLOWED_LABELS for value in expected.values()):
            raise ValueError("RELEVANCE_EXPECTED_INVALID")
    return profiles, opportunities


def pct(value: int, total: int) -> float | None:
    return round((value / total) * 100, 1) if total else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agnes 3.0 Flash semantic relevance benchmark for MedicalChannelAI Action Radar.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "action_radar_relevance_gold.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=0.15)
    args = parser.parse_args()

    if args.delay_seconds < 0:
        raise ValueError("delay must be >= 0")
    keys = api_keys()
    if not keys:
        raise RuntimeError("AGNES_API_KEY_NOT_CONFIGURED")
    base_url = os.environ.get("AGNES_API_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL

    profiles, opportunities = validate_dataset(load_json(args.dataset))
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict] = []
    invalid_count = 0
    request_failure_count = 0
    provider_auth_failure_count = 0

    case_index = 0
    for opportunity in opportunities:
        for profile in profiles:
            expected = str(opportunity["expected"][profile["profile_id"]])
            allowed_ids = {
                str(item["id"])
                for item in profile.get("items", [])
                if isinstance(item, dict) and item.get("id")
            }
            predicted = None
            matched_ids: list[str] = []
            error = None
            for attempt in range(MAX_ATTEMPTS):
                key = keys[(case_index + attempt) % len(keys)]
                try:
                    raw = call_agnes(
                        key=key,
                        base_url=base_url,
                        messages=build_messages(profile, opportunity),
                    )
                    parsed = parse_content(raw, allowed_ids)
                    predicted = str(parsed["classification"])
                    matched_ids = list(parsed["matched_profile_item_ids"])
                    error = None
                    break
                except ValueError as exc:
                    error = str(exc)
                    if attempt + 1 == MAX_ATTEMPTS:
                        invalid_count += 1
                except Exception as exc:
                    error = f"{type(exc).__name__}:{str(exc)[:120]}"
                    if attempt + 1 == MAX_ATTEMPTS:
                        request_failure_count += 1
                        if "AGNES_HTTP_401" in error or "AGNES_HTTP_403" in error:
                            provider_auth_failure_count += 1
                if attempt + 1 < MAX_ATTEMPTS:
                    time.sleep(0.25)

            results.append(
                {
                    "case_id": opportunity["case_id"],
                    "profile_id": profile["profile_id"],
                    "expected": expected,
                    "predicted": predicted,
                    "matched_profile_item_ids": matched_ids,
                    "pass": predicted == expected,
                    "error": error,
                }
            )
            case_index += 1
            if args.delay_seconds:
                time.sleep(args.delay_seconds)

    total = len(results)
    exact = sum(1 for row in results if row["pass"])
    hard_negative = [row for row in results if row["expected"] == "NOT_MATCH"]
    hard_negative_fp = sum(1 for row in hard_negative if row["predicted"] not in {None, "NOT_MATCH"})
    direct = [row for row in results if row["expected"] == "DIRECT_MATCH"]
    direct_hit = sum(1 for row in direct if row["predicted"] == "DIRECT_MATCH")
    possible = [row for row in results if row["expected"] == "POSSIBLE_MATCH_NEEDS_CONFIRMATION"]
    possible_overclaim = sum(1 for row in possible if row["predicted"] == "DIRECT_MATCH")
    invalid_final = sum(1 for row in results if row["predicted"] is None)

    metrics = {
        "total_cases": total,
        "exact_match_count": exact,
        "exact_accuracy_pct": pct(exact, total),
        "hard_negative_count": len(hard_negative),
        "hard_negative_false_positive_count": hard_negative_fp,
        "hard_negative_false_positive_pct": pct(hard_negative_fp, len(hard_negative)),
        "direct_match_count": len(direct),
        "direct_match_recall_count": direct_hit,
        "direct_match_recall_pct": pct(direct_hit, len(direct)),
        "possible_match_count": len(possible),
        "possible_to_direct_overclaim_count": possible_overclaim,
        "possible_to_direct_overclaim_pct": pct(possible_overclaim, len(possible)),
        "invalid_final_count": invalid_final,
        "request_failure_count": request_failure_count,
        "provider_auth_failure_count": provider_auth_failure_count,
        "parser_invalid_final_count": invalid_count,
    }
    benchmark_valid = request_failure_count == 0 and invalid_final == 0
    benchmark_status = (
        "BLOCKED_PROVIDER_AUTH"
        if provider_auth_failure_count > 0
        else "BLOCKED_PROVIDER_OR_TRANSPORT"
        if request_failure_count > 0
        else "VALID"
    )
    gates = {
        "hard_negative_false_positive_pct_lte_5": (metrics["hard_negative_false_positive_pct"] or 0) <= 5.0,
        "direct_match_recall_pct_gte_90": (metrics["direct_match_recall_pct"] or 0) >= 90.0,
        "possible_to_direct_overclaim_zero": possible_overclaim == 0,
        "invalid_final_zero": invalid_final == 0,
        "exact_accuracy_pct_gte_90": (metrics["exact_accuracy_pct"] or 0) >= 90.0,
    }
    passed = benchmark_valid and all(gates.values())
    report = {
        "schema_version": "0.1",
        "mode": "AGNES_RELEVANCE_GATE_BENCHMARK",
        "model": MODEL_ID,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "production_data_mutated": False,
        "expected_labels_not_sent_to_model": True,
        "raw_model_text_persisted": False,
        "metrics": metrics,
        "gates": gates,
        "benchmark_valid": benchmark_valid,
        "benchmark_status": benchmark_status,
        "benchmark_pass": passed if benchmark_valid else None,
        "failures": [row for row in results if not row["pass"]],
        "results": results,
    }
    write_json(args.output, report)
    print(
        "AGNES_RELEVANCE_BENCHMARK "
        f"status={benchmark_status} pass={report['benchmark_pass']} exact={metrics['exact_accuracy_pct']}% "
        f"hard_negative_fp={metrics['hard_negative_false_positive_pct']}% "
        f"direct_recall={metrics['direct_match_recall_pct']}% "
        f"possible_overclaim={metrics['possible_to_direct_overclaim_pct']}% "
        f"invalid={invalid_final}/{total}"
    )
    for row in report["failures"][:20]:
        print(
            "FAIL_CASE "
            f"{row['case_id']}/{row['profile_id']} "
            f"expected={row['expected']} predicted={row['predicted']} "
            f"ids={','.join(row['matched_profile_item_ids']) or '-'} "
            f"error={row['error'] or '-'}"
        )
    if not benchmark_valid:
        return 4
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
