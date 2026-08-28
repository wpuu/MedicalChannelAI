from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .product_classifier import taxonomy_ids


DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "docs/research/benchmarks/agnes-2.5-flash-product-taxonomy-v0.1.json"
)
DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_MODEL = "agnes-2.5-flash"
DEFAULT_RPM = 18

SYSTEM_PROMPT = """You are a constrained medical-product taxonomy classifier.
The input facts are locked and were verified outside the model. You do not create procurement facts.
Return exactly one JSON object, no markdown and no free-text explanation.
Use only taxonomy IDs supplied in the user message.
If the input is too generic to support a taxonomy ID, return taxonomy_ids=[] and needs_more_detail=true.
Do not infer hidden attachment contents, brands, suppliers, hospital relationships, budgets, dates, or lifecycle states."""


class TaxonomyBenchmarkError(RuntimeError):
    pass


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload.get("cases"), list) or not payload["cases"]:
        raise TaxonomyBenchmarkError("benchmark manifest has no cases")
    return payload


def build_user_prompt(case: dict[str, Any]) -> str:
    payload = {
        "case_id": case["case_id"],
        "locked_input": case["locked_input"],
        "allowed_taxonomy_ids": sorted(taxonomy_ids()),
        "required_output": {
            "case_id": case["case_id"],
            "taxonomy_ids": ["<zero or more allowed ids>"],
            "needs_more_detail": "<boolean>",
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def extract_json_object(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise TaxonomyBenchmarkError(f"model response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise TaxonomyBenchmarkError("model response must be one JSON object")
    return parsed


def validate_output(case: dict[str, Any], output: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if set(output) != {"case_id", "taxonomy_ids", "needs_more_detail"}:
        errors.append("output keys do not match exact no-free-text contract")
    if output.get("case_id") != case["case_id"]:
        errors.append("case_id mismatch")
    labels = output.get("taxonomy_ids")
    allowed = taxonomy_ids()
    if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
        errors.append("taxonomy_ids must be a string array")
    else:
        if len(labels) != len(set(labels)):
            errors.append("taxonomy_ids contains duplicates")
        if any(label not in allowed for label in labels):
            errors.append("taxonomy_ids contains unknown id")
    if not isinstance(output.get("needs_more_detail"), bool):
        errors.append("needs_more_detail must be boolean")
    return errors


def score_case(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    errors = validate_output(case, output)
    labels = output.get("taxonomy_ids") if isinstance(output.get("taxonomy_ids"), list) else []
    output_set = set(label for label in labels if isinstance(label, str))
    acceptable_sets = [set(item) for item in case["acceptable_label_sets"]]
    acceptable = any(output_set == expected for expected in acceptable_sets)
    safety_case = case.get("safety_case") == "ABSTAIN"
    safe_abstention = (not safety_case) or (output_set == set() and output.get("needs_more_detail") is True)
    return {
        "case_id": case["case_id"],
        "contract_valid": not errors,
        "validation_errors": errors,
        "acceptable_label_set": acceptable,
        "needs_more_detail_correct": output.get("needs_more_detail") is case["needs_more_detail"],
        "safe_abstention": safe_abstention,
        "unknown_taxonomy_id": any(label not in taxonomy_ids() for label in output_set),
        "output": output,
    }


def aggregate(manifest: dict[str, Any], scored: list[dict[str, Any]], failures: int) -> dict[str, Any]:
    total = len(manifest["cases"])
    completed = len(scored)
    safety_rows = [row for row, case in zip(scored, manifest["cases"]) if case.get("safety_case") == "ABSTAIN"] if completed == total else []

    def rate(field: str) -> float:
        return sum(1 for row in scored if row[field]) / max(1, completed)

    metrics = {
        "acceptable_label_set_accuracy": rate("acceptable_label_set"),
        "needs_more_detail_accuracy": rate("needs_more_detail_correct"),
        "abstention_safety_accuracy": (
            sum(1 for row in safety_rows if row["safe_abstention"]) / max(1, len(safety_rows))
            if safety_rows else 0.0
        ),
        "unknown_taxonomy_id_rate": sum(1 for row in scored if row["unknown_taxonomy_id"]) / max(1, completed),
        "contract_failure_rate": sum(1 for row in scored if not row["contract_valid"]) / max(1, completed),
        "api_or_json_failure_rate": failures / max(1, total),
    }
    gates = manifest["gates"]
    gate_results = {
        "acceptable_label_set_accuracy": metrics["acceptable_label_set_accuracy"] >= gates["acceptable_label_set_accuracy_min"],
        "needs_more_detail_accuracy": metrics["needs_more_detail_accuracy"] >= gates["needs_more_detail_accuracy_min"],
        "abstention_safety_accuracy": metrics["abstention_safety_accuracy"] >= gates["abstention_safety_accuracy_min"],
        "unknown_taxonomy_id_rate": metrics["unknown_taxonomy_id_rate"] <= gates["unknown_taxonomy_id_rate_max"],
        "contract_failure_rate": metrics["contract_failure_rate"] <= gates["contract_failure_rate_max"],
        "api_or_json_failure_rate": metrics["api_or_json_failure_rate"] <= gates["api_or_json_failure_rate_max"],
    }
    return {
        "case_count": total,
        "completed_case_count": completed,
        "failure_count": failures,
        "metrics": metrics,
        "gate_results": gate_results,
        "passed": completed == total and all(gate_results.values()),
    }


def call_model(*, api_key: str, base_url: str, model: str, prompt: str, timeout: int = 60) -> str:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 240,
                "stream": False,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MedicalChannelAI-AgnesTaxonomyBenchmark/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TaxonomyBenchmarkError("response content is not text")
            return content
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
        raise TaxonomyBenchmarkError(f"Agnes request failed: {type(exc).__name__}: {exc}") from exc


def run(manifest: dict[str, Any], *, api_key: str, base_url: str, model: str, rpm: int) -> dict[str, Any]:
    interval = 60.0 / max(1, rpm)
    scored: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, case in enumerate(manifest["cases"]):
        if index:
            time.sleep(interval)
        try:
            raw = call_model(api_key=api_key, base_url=base_url, model=model, prompt=build_user_prompt(case))
            output = extract_json_object(raw)
            scored.append(score_case(case, output))
        except TaxonomyBenchmarkError as exc:
            failures.append({"case_id": case["case_id"], "error": str(exc)})
    return {
        "benchmark_id": manifest["benchmark_id"],
        "model": model,
        "aggregate": aggregate(manifest, scored, len(failures)),
        "cases": scored,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Agnes controlled product-taxonomy benchmark")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true", help="Actually call Agnes; default is dry-run")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--rpm", type=int, default=DEFAULT_RPM)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    if not args.execute:
        print(json.dumps({
            "status": "DRY_RUN_NO_NETWORK",
            "benchmark_id": manifest["benchmark_id"],
            "case_count": len(manifest["cases"]),
            "taxonomy_id_count": len(taxonomy_ids()),
            "classifier_id_if_passed": manifest["classifier_id_if_passed"],
        }, ensure_ascii=False, indent=2))
        return 0

    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        raise SystemExit("AGNES_API_KEY is required only when --execute is supplied")
    result = run(manifest, api_key=api_key, base_url=args.base_url, model=args.model, rpm=args.rpm)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["aggregate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
