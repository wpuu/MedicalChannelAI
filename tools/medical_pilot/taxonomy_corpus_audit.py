from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from .collector_core import ID_NAMESPACE
from .product_classifier import classify_product_facts


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "docs/research/fixtures"
DEFAULT_OUTPUT = REPO_ROOT / "docs/research/benchmarks/tianjin-deterministic-taxonomy-coverage-v0.1.json"
OPPORTUNITY_FIXTURE_FILES = (
    "tianjin-opportunity-cases-v0.1.json",
    "tianjin-opportunity-attachment-backed-cases-v0.1.json",
    "tianjin-procurement-intent-identity-cases-v0.1.json",
    "tianjin-expanded-opportunity-cases-v0.1.json",
    "tianjin-expanded-opportunity-cases-v0.2.json",
    "tianjin-expanded-opportunity-cases-v0.3.json",
)


def _load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for filename in OPPORTUNITY_FIXTURE_FILES:
        payload = json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))
        cases.extend(item for item in payload.get("cases", []) if isinstance(item, dict))
    return cases


def _fact(case_id: str, index: int, value: str, source_url: str) -> dict[str, Any]:
    fact_uuid = uuid.uuid5(ID_NAMESPACE, f"taxonomy-audit|{case_id}|{index}|{value}")
    return {
        "fact_id": f"fact_{fact_uuid}",
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "field_name": "taxonomy_audit_text",
        "field_value": value,
        "verification_status": "VERIFIED",
        "model_generated": False,
        "source_url": source_url,
    }


def _official_product_texts(case: dict[str, Any]) -> list[str]:
    values: list[str] = []
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    project_name = expected.get("project_name")
    if isinstance(project_name, str) and project_name.strip():
        values.append(project_name.strip())

    need_summary = case.get("official_need_summary")
    if isinstance(need_summary, str) and need_summary.strip():
        values.append(need_summary.strip())

    for key in ("official_scope",):
        items = case.get(key)
        if isinstance(items, list):
            values.extend(item.strip() for item in items if isinstance(item, str) and item.strip())

    award_items = case.get("official_award_item_samples")
    if isinstance(award_items, list):
        for item in award_items:
            if isinstance(item, dict):
                name = item.get("raw_name")
                if isinstance(name, str) and name.strip():
                    values.append(name.strip())

    installed = case.get("official_installed_base_samples")
    if isinstance(installed, list):
        for item in installed:
            if isinstance(item, dict):
                equipment = item.get("equipment")
                if isinstance(equipment, str) and equipment.strip():
                    values.append(equipment.strip())

    # De-duplicate exact text only. Do not semantically rewrite official text.
    return list(dict.fromkeys(values))


def audit_corpus() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in _load_cases():
        case_id = str(case.get("case_id") or "")
        source_url = str(case.get("source_url") or "")
        texts = _official_product_texts(case)
        facts = [_fact(case_id, index, text, source_url) for index, text in enumerate(texts)]
        classification = classify_product_facts(facts)
        rows.append(
            {
                "case_id": case_id,
                "source_url": source_url,
                "input_text_count": len(texts),
                "taxonomy_ids": list(classification.labels),
                "deterministically_classified": bool(classification.labels),
                "supporting_fact_ids": list(classification.supporting_fact_ids),
                "needs_controlled_model_or_human": not bool(classification.labels),
            }
        )

    classified = sum(1 for row in rows if row["deterministically_classified"])
    total = len(rows)
    return {
        "schema_version": "0.1",
        "audit_type": "DETERMINISTIC_TAXONOMY_COVERAGE",
        "corpus_case_count": total,
        "deterministically_classified_count": classified,
        "unresolved_count": total - classified,
        "deterministic_coverage_rate": round(classified / total, 4) if total else 0.0,
        "important_interpretation": "COVERAGE_RATE_IS_NOT_MODEL_ACCURACY",
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit deterministic product-taxonomy coverage across the verified fixture corpus.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path. Without this flag, JSON is printed only.")
    args = parser.parse_args(argv)
    result = audit_corpus()
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
