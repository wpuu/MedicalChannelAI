#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LABEL_DIRECT = "DIRECT_MATCH"
LABEL_POSSIBLE = "POSSIBLE_MATCH_NEEDS_CONFIRMATION"
LABEL_NONE = "NOT_MATCH"


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: object) -> str:
    return re.sub(r"[\s\-_—–·,，。；;：:（）()【】\[\]/]+", "", str(value or "").strip().lower())


def normalized_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = normalize(value)
        if text and text not in result:
            result.append(text)
    return result


def classify_item(item: dict, opportunity: dict) -> str:
    mode = str(item.get("match_mode") or "").strip()
    aliases = normalized_list(item.get("aliases"))
    related = normalized_list(item.get("related_categories"))
    product_items = normalized_list(opportunity.get("product_items"))
    categories = normalized_list(opportunity.get("product_categories"))
    title = normalize(opportunity.get("project_name"))

    if not aliases:
        return LABEL_NONE

    if mode == "EXACT_PRODUCT":
        for alias in aliases:
            if any(alias == product or alias in product for product in product_items):
                return LABEL_DIRECT
        if not product_items and any(alias in title for alias in aliases):
            return LABEL_POSSIBLE
        return LABEL_NONE

    if mode == "CATEGORY":
        for alias in aliases:
            if any(alias in product or product in alias for product in product_items):
                return LABEL_DIRECT
            if any(alias in category or category in alias for category in categories):
                return LABEL_DIRECT
        if not product_items and any(alias in title for alias in aliases):
            return LABEL_POSSIBLE
        return LABEL_NONE

    if mode == "BROAD_CATEGORY":
        for alias in aliases:
            if any(alias == product for product in product_items):
                return LABEL_DIRECT
            if any(alias in category or category in alias for category in categories):
                return LABEL_POSSIBLE
            if alias in title:
                return LABEL_POSSIBLE
        for category in categories:
            if any(category == relation or category in relation or relation in category for relation in related):
                return LABEL_POSSIBLE
        return LABEL_NONE

    raise ValueError(f"UNKNOWN_MATCH_MODE:{mode}")


def classify_profile(profile: dict, opportunity: dict) -> dict[str, object]:
    direct_ids: list[str] = []
    possible_ids: list[str] = []
    for item in profile.get("items") or []:
        if not isinstance(item, dict):
            continue
        label = classify_item(item, opportunity)
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        if label == LABEL_DIRECT:
            direct_ids.append(item_id)
        elif label == LABEL_POSSIBLE:
            possible_ids.append(item_id)

    if direct_ids:
        return {"classification": LABEL_DIRECT, "matched_profile_item_ids": direct_ids}
    if possible_ids:
        return {"classification": LABEL_POSSIBLE, "matched_profile_item_ids": possible_ids}
    return {"classification": LABEL_NONE, "matched_profile_item_ids": []}


def pct(value: int, total: int) -> float | None:
    return round((value / total) * 100, 1) if total else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark deterministic Action Radar relevance rules.")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--gold",
        type=Path,
        default=root / "data" / "action_radar_relevance_gold.json",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=root / "data" / "action_radar_relevance_rules_v0.json",
    )
    args = parser.parse_args()

    gold = load_json(args.gold)
    rules = load_json(args.rules)
    gold_opportunities = gold.get("opportunities") if isinstance(gold, dict) else None
    profiles = rules.get("profiles") if isinstance(rules, dict) else None
    if not isinstance(gold_opportunities, list) or not isinstance(profiles, list):
        raise ValueError("RELEVANCE_BASELINE_INPUT_INVALID")

    profile_map = {str(row.get("profile_id")): row for row in profiles if isinstance(row, dict)}
    rows: list[dict[str, object]] = []

    for opportunity in gold_opportunities:
        expected = opportunity.get("expected") or {}
        for profile_id, expected_label in expected.items():
            profile = profile_map.get(str(profile_id))
            if not profile:
                raise ValueError(f"PROFILE_RULE_MISSING:{profile_id}")
            predicted = classify_profile(profile, opportunity)
            rows.append(
                {
                    "case_id": opportunity.get("case_id"),
                    "profile_id": profile_id,
                    "expected": expected_label,
                    "predicted": predicted["classification"],
                    "matched_profile_item_ids": predicted["matched_profile_item_ids"],
                    "pass": predicted["classification"] == expected_label,
                }
            )

    total = len(rows)
    exact = sum(1 for row in rows if row["pass"])
    negatives = [row for row in rows if row["expected"] == LABEL_NONE]
    false_positive = sum(1 for row in negatives if row["predicted"] != LABEL_NONE)
    direct = [row for row in rows if row["expected"] == LABEL_DIRECT]
    direct_hit = sum(1 for row in direct if row["predicted"] == LABEL_DIRECT)
    possible = [row for row in rows if row["expected"] == LABEL_POSSIBLE]
    possible_overclaim = sum(1 for row in possible if row["predicted"] == LABEL_DIRECT)

    metrics = {
        "total_cases": total,
        "exact_accuracy_pct": pct(exact, total),
        "hard_negative_false_positive_pct": pct(false_positive, len(negatives)),
        "direct_match_recall_pct": pct(direct_hit, len(direct)),
        "possible_to_direct_overclaim_count": possible_overclaim,
    }
    print("DETERMINISTIC_RELEVANCE_BASELINE=" + json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    failures = [row for row in rows if not row["pass"]]
    print("FAILURE_COUNT=" + str(len(failures)))
    for row in failures:
        print(
            "FAIL_CASE="
            + str(row["case_id"]) + "/" + str(row["profile_id"])
            + " expected=" + str(row["expected"])
            + " predicted=" + str(row["predicted"])
            + " ids=" + ",".join(row["matched_profile_item_ids"])
        )

    # This benchmark is only a safety baseline. Passing it proves that obvious
    # cases can be handled deterministically; it does not prove market accuracy.
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
