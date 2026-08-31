from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .agnes_client import DEFAULT_BASE_URL, DEFAULT_MODEL, validate_base_url


DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "docs/research/benchmarks/agnes-2.5-flash-v0.1.json"
)
DEFAULT_RPM = 12


SYSTEM_PROMPT = """You are a constrained classification component for a medical-channel commercial-intelligence system.
You do NOT create procurement facts. You receive locked public facts that were already verified outside the model.
Return one JSON object only. Do not use markdown. Do not add free-text explanations.
Choose segment, item_detail_status, and risk_flags only from the enums supplied in the user message.
If item-level detail is hidden in an unparsed attachment, choose ATTACHMENT_REQUIRED.
If the notice is a procurement intent, do not treat it as a tender or award.
Never invent a brand, supplier, budget, date, device detail, or lifecycle state."""


class BenchmarkError(RuntimeError):
    pass


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not manifest.get("cases"):
        raise BenchmarkError("benchmark manifest has no cases")
    return manifest


def build_user_prompt(manifest: dict[str, Any], case: dict[str, Any]) -> str:
    payload = {
        "case_id": case["case_id"],
        "locked_input": case["locked_input"],
        "allowed_segments": manifest["segments"],
        "allowed_item_detail_status": manifest["item_detail_status_values"],
        "allowed_risk_flags": manifest["risk_flags"],
        "required_output": {
            "case_id": case["case_id"],
            "segment": "<one allowed segment>",
            "item_detail_status": "<one allowed item detail status>",
            "needs_more_source_data": "<boolean>",
            "risk_flags": ["<zero or more allowed risk flags>"],
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
        raise BenchmarkError(f"model response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BenchmarkError("model response must be one JSON object")
    return parsed


def validate_model_output(manifest: dict[str, Any], case: dict[str, Any], output: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed_keys = {"case_id", "segment", "item_detail_status", "needs_more_source_data", "risk_flags"}
    if set(output) != allowed_keys:
        errors.append("output keys do not exactly match the no-free-text contract")
    if output.get("case_id") != case["case_id"]:
        errors.append("case_id mismatch")
    if output.get("segment") not in manifest["segments"]:
        errors.append("invalid segment enum")
    if output.get("item_detail_status") not in manifest["item_detail_status_values"]:
        errors.append("invalid item_detail_status enum")
    if not isinstance(output.get("needs_more_source_data"), bool):
        errors.append("needs_more_source_data must be boolean")
    flags = output.get("risk_flags")
    if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
        errors.append("risk_flags must be a string array")
    elif any(flag not in manifest["risk_flags"] for flag in flags):
        errors.append("invalid risk flag enum")
    return errors


def score_case(manifest: dict[str, Any], case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    validation_errors = validate_model_output(manifest, case, output)
    expected = case["expected"]
    flags = set(output.get("risk_flags") or []) if isinstance(output.get("risk_flags"), list) else set()
    required_flags = set(expected.get("required_risk_flags") or [])
    required_flag_recall = 1.0 if not required_flags else len(flags & required_flags) / len(required_flags)
    unexpected_flags = flags - required_flags
    unexpected_flag_rate = len(unexpected_flags) / max(1, len(manifest["risk_flags"]))
    return {
        "case_id": case["case_id"],
        "valid_contract": not validation_errors,
        "validation_errors": validation_errors,
        "segment_correct": output.get("segment") in expected["acceptable_segments"],
        "item_detail_status_correct": output.get("item_detail_status") == expected["item_detail_status"],
        "needs_more_source_data_correct": output.get("needs_more_source_data") is expected["needs_more_source_data"],
        "required_risk_flag_recall": required_flag_recall,
        "unexpected_risk_flag_rate": unexpected_flag_rate,
        "output": output,
    }


def aggregate_scores(manifest: dict[str, Any], scored: list[dict[str, Any]], failures: int) -> dict[str, Any]:
    case_count = len(manifest["cases"])
    completed = len(scored)

    def average_boolean(field: str) -> float:
        return sum(1.0 if row[field] else 0.0 for row in scored) / max(1, completed)

    required_flag_recall = sum(row["required_risk_flag_recall"] for row in scored) / max(1, completed)
    invalid_enum_rate = sum(1.0 if not row["valid_contract"] else 0.0 for row in scored) / max(1, completed)
    unexpected_risk_flag_rate = sum(row["unexpected_risk_flag_rate"] for row in scored) / max(1, completed)
    failure_rate = failures / max(1, case_count)
    metrics = {
        "segment_accuracy": average_boolean("segment_correct"),
        "item_detail_status_accuracy": average_boolean("item_detail_status_correct"),
        "needs_more_source_data_accuracy": average_boolean("needs_more_source_data_correct"),
        "required_risk_flag_recall": required_flag_recall,
        "unexpected_risk_flag_rate": unexpected_risk_flag_rate,
        "invalid_enum_rate": invalid_enum_rate,
        "api_or_json_failure_rate": failure_rate,
    }
    gates = manifest["gates"]
    gate_results = {
        "segment_accuracy": metrics["segment_accuracy"] >= gates["segment_accuracy_min"],
        "item_detail_status_accuracy": metrics["item_detail_status_accuracy"] >= gates["item_detail_status_accuracy_min"],
        "needs_more_source_data_accuracy": metrics["needs_more_source_data_accuracy"] >= gates["needs_more_source_data_accuracy_min"],
        "required_risk_flag_recall": metrics["required_risk_flag_recall"] >= gates["required_risk_flag_recall_min"],
        "invalid_enum_rate": metrics["invalid_enum_rate"] <= gates["invalid_enum_rate_max"],
        "api_or_json_failure_rate": metrics["api_or_json_failure_rate"] <= gates["api_or_json_failure_rate_max"],
    }
    return {
        "case_count": case_count,
        "completed_case_count": completed,
        "failure_count": failures,
        "metrics": metrics,
        "gate_results": gate_results,
        "passed": all(gate_results.values()),
    }


def call_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    user_prompt: str,
    timeout_seconds: int = 60,
    retries: int = 0,
    global_lease_granted: bool = False,
) -> str:
    """One provider start only, callable solely from a global-lease holder."""

    if global_lease_granted is not True:
        raise BenchmarkError("DIRECT_PROVIDER_CALL_REQUIRES_GLOBAL_LEASE")
    if retries != 0:
        raise BenchmarkError("BENCHMARK_PROVIDER_RETRY_REQUIRES_NEW_GLOBAL_LEASE")
    if model != DEFAULT_MODEL:
        raise BenchmarkError("BENCHMARK_MODEL_NOT_ALLOWED")
    official_base_url = validate_base_url(base_url)
    endpoint = official_base_url + "/chat/completions"
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 300,
        "stream": False,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MedicalChannelAI-AgnesBenchmark/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(2 * 1024 * 1024)
            data = json.loads(raw.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise BenchmarkError("chat completion content is not a string")
            return content
    except urllib.error.HTTPError as exc:
        raise BenchmarkError(f"Agnes API HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
        raise BenchmarkError(f"Agnes API response failure: {type(exc).__name__}") from exc


def run_benchmark(
    manifest: dict[str, Any], *, base_url: str, api_key: str, model: str, rpm: int
) -> dict[str, Any]:
    raise BenchmarkError("DIRECT_EXECUTION_DISABLED_USE_AGNES_BENCHMARK_SUITE")


def main() -> int:
    parser = argparse.ArgumentParser(description="Agnes 2.5 Flash medical-channel benchmark scoring harness")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true", help="Deprecated and blocked; use agnes_benchmark_suite")
    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, json.JSONDecodeError, BenchmarkError) as exc:
        print(json.dumps({"status": "ERROR", "error_class": type(exc).__name__}, ensure_ascii=False))
        return 2

    if args.execute:
        print(json.dumps({
            "status": "ERROR",
            "error_class": "DIRECT_EXECUTION_DISABLED_USE_AGNES_BENCHMARK_SUITE",
            "network_called": False,
        }, ensure_ascii=False, separators=(",", ":")))
        return 2

    print(json.dumps({
        "status": "DRY_RUN_NO_NETWORK",
        "benchmark_id": manifest["benchmark_id"],
        "target_model": manifest["model_target"],
        "case_count": len(manifest["cases"]),
        "gates": manifest["gates"],
        "network_called": False,
        "execute_via": "python3 -m tools.medical_pilot.agnes_benchmark_suite --execute --maintenance-window",
        "automatic_classifier_admission_allowed": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
