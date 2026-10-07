#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DIRECT = "DIRECT_MATCH"
POSSIBLE = "POSSIBLE_MATCH_NEEDS_CONFIRMATION"
NO_MATCH = "NOT_MATCH"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value):
    return re.sub(r"[\s\-_—–·,，。；;：:（）()【】\[\]/]+", "", str(value or "").strip().lower())


def list_norm(values):
    result = []
    for value in values if isinstance(values, list) else []:
        value = norm(value)
        if value and value not in result:
            result.append(value)
    return result


def buyer_scope(row):
    text = norm(" ".join(str(row.get(k) or "") for k in ("buyer_name", "hospital_name", "project_name")))
    if any(x in text for x in ("医院", "卫生院", "妇幼保健院", "急救中心", "医疗中心")):
        return "CLINICAL_PROVIDER"
    if any(x in text for x in ("疾病预防控制中心", "疾控中心")):
        return "CDC"
    if any(x in text for x in ("市场监督", "食品药品检验", "药品检验", "药检院", "检验检测认证中心", "医疗器械检验研究院")):
        return "REGULATORY_LAB"
    if any(x in text for x in ("大学", "学院", "研究院", "研究所")):
        return "RESEARCH_OR_EDUCATION"
    return "UNKNOWN"


def hit(term, values, symmetric=False):
    for value in values:
        if term == value or term in value or (symmetric and value in term):
            return True
    return False


def classify_item(item, row):
    mode = item.get("match_mode")
    direct = list_norm(item.get("direct_aliases"))
    possible = list_norm(item.get("possible_aliases"))
    related = list_norm(item.get("related_categories"))
    products = list_norm(row.get("product_items"))
    categories = list_norm(row.get("product_categories"))
    title = [norm(row.get("project_name"))]

    if mode == "EXACT_PRODUCT":
        if any(hit(a, products) or hit(a, title) for a in direct):
            return DIRECT
    elif mode == "CATEGORY":
        if any(hit(a, products, True) or hit(a, categories, True) or hit(a, title) for a in direct):
            return DIRECT
    elif mode == "BROAD_CATEGORY":
        if any(a == v for a in direct for v in products):
            return DIRECT
        if any(a == v for a in direct for v in categories):
            return POSSIBLE
    else:
        raise ValueError(f"UNKNOWN_MATCH_MODE:{mode}")

    if any(hit(a, products, True) or hit(a, categories, True) or hit(a, title) for a in possible):
        return POSSIBLE
    if any(c == r or c in r or r in c for c in categories for r in related):
        return POSSIBLE
    if mode == "BROAD_CATEGORY" and any(a in title[0] for a in direct):
        return POSSIBLE
    return NO_MATCH


def classify(profile, row):
    scope = buyer_scope(row)
    allowed = set(profile.get("allowed_buyer_scopes") or [])
    if allowed and scope not in allowed:
        return NO_MATCH, []

    direct_ids, possible_ids = [], []
    for item in profile.get("items") or []:
        label = classify_item(item, row)
        if label == DIRECT:
            direct_ids.append(item["id"])
        elif label == POSSIBLE:
            possible_ids.append(item["id"])

    if direct_ids:
        return DIRECT, direct_ids
    if possible_ids:
        return POSSIBLE, possible_ids

    surface = [norm(row.get("project_name")), *list_norm(row.get("product_categories")), *list_norm(row.get("product_items"))]
    if any(hit(t, surface, True) for t in list_norm(profile.get("possible_terms"))):
        return POSSIBLE, []
    return NO_MATCH, []


def pct(n, d):
    return round(n * 100 / d, 1) if d else None


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--rules", type=Path, default=root / "data" / "action_radar_relevance_rules_v1.json")
    args = ap.parse_args()

    gold = load_json(args.gold)
    rules = load_json(args.rules)
    profiles = {p["profile_id"]: p for p in rules["profiles"]}
    rows = []
    for case in gold["opportunities"]:
        for pid, expected in case["expected"].items():
            predicted, ids = classify(profiles[pid], case)
            rows.append((case["case_id"], pid, expected, predicted, ids))

    total = len(rows)
    exact = sum(expected == predicted for _, _, expected, predicted, _ in rows)
    neg = [r for r in rows if r[2] == NO_MATCH]
    fp = sum(r[3] != NO_MATCH for r in neg)
    direct = [r for r in rows if r[2] == DIRECT]
    recall = sum(r[3] == DIRECT for r in direct)
    possible = [r for r in rows if r[2] == POSSIBLE]
    overclaim = sum(r[3] == DIRECT for r in possible)

    metrics = {
        "total_cases": total,
        "exact_accuracy_pct": pct(exact, total),
        "hard_negative_false_positive_pct": pct(fp, len(neg)),
        "direct_match_recall_pct": pct(recall, len(direct)),
        "possible_to_direct_overclaim_count": overclaim,
    }
    print("RELEVANCE_V1=" + json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    failures = [r for r in rows if r[2] != r[3]]
    print("FAILURE_COUNT=" + str(len(failures)))
    for cid, pid, expected, predicted, ids in failures:
        print(f"FAIL_CASE={cid}/{pid} expected={expected} predicted={predicted} ids={','.join(ids)}")
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
