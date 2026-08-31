from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any, Callable, Mapping

from .agnes_client import DEFAULT_BASE_URL, validate_base_url
from .agnes_provider_smoke import run_provider_smoke
from .attachment_live_probe import probe_attachment, validate_probe_filename, validate_tianjin_finance_attachment_url
from .pilot_api import CanonicalOriginPolicy
from .pilot_live_seed import run_seed


DEFAULT_ACCEPTANCE_MANIFEST = Path("deploy/pilot-host-acceptance-v0.1.json")
EXPECTED_BOOTSTRAP_MANIFEST = "deploy/tianjin-pilot-bootstrap-urls-2026-08-30.json"
REQUIRED_ENVIRONMENT = ("MCAI_CANONICAL_ORIGIN", "MCAI_AGNES_API_KEY")


@dataclass(frozen=True)
class HostAcceptanceManifest:
    bootstrap_manifest: str
    attachment_project_code: str
    attachment_filename: str
    attachment_url: str
    expected_bootstrap_success_count: int


class PilotHostAcceptanceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _required_text(value: Any, code: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PilotHostAcceptanceError(code)
    text = value.strip()
    if len(text) > max_length:
        raise PilotHostAcceptanceError(code)
    return text


def load_acceptance_manifest(path: Path) -> HostAcceptanceManifest:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotHostAcceptanceError("ACCEPTANCE_MANIFEST_UNREADABLE") from exc

    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "purpose",
        "bootstrap_manifest",
        "attachment",
        "required_environment",
        "acceptance_requires",
    }:
        raise PilotHostAcceptanceError("ACCEPTANCE_MANIFEST_SHAPE_INVALID")
    if payload.get("schema_version") != "0.1":
        raise PilotHostAcceptanceError("ACCEPTANCE_MANIFEST_VERSION_INVALID")
    _required_text(payload.get("purpose"), "ACCEPTANCE_MANIFEST_PURPOSE_INVALID", max_length=500)

    bootstrap_manifest = _required_text(
        payload.get("bootstrap_manifest"),
        "ACCEPTANCE_BOOTSTRAP_MANIFEST_INVALID",
        max_length=300,
    )
    posix_path = PurePosixPath(bootstrap_manifest)
    if (
        posix_path.is_absolute()
        or ".." in posix_path.parts
        or bootstrap_manifest != EXPECTED_BOOTSTRAP_MANIFEST
    ):
        raise PilotHostAcceptanceError("ACCEPTANCE_BOOTSTRAP_MANIFEST_NOT_ALLOWED")

    required_environment = payload.get("required_environment")
    if required_environment != list(REQUIRED_ENVIRONMENT):
        raise PilotHostAcceptanceError("ACCEPTANCE_REQUIRED_ENVIRONMENT_INVALID")

    attachment = payload.get("attachment")
    if not isinstance(attachment, dict) or set(attachment) != {"project_code", "filename", "url"}:
        raise PilotHostAcceptanceError("ACCEPTANCE_ATTACHMENT_INVALID")
    project_code = _required_text(
        attachment.get("project_code"), "ACCEPTANCE_ATTACHMENT_PROJECT_CODE_INVALID", max_length=100
    )
    filename = _required_text(
        attachment.get("filename"), "ACCEPTANCE_ATTACHMENT_FILENAME_INVALID", max_length=300
    )
    url = _required_text(attachment.get("url"), "ACCEPTANCE_ATTACHMENT_URL_INVALID", max_length=1200)
    try:
        validate_probe_filename(filename)
        validate_tianjin_finance_attachment_url(url)
    except Exception as exc:
        raise PilotHostAcceptanceError("ACCEPTANCE_ATTACHMENT_NOT_ALLOWED") from exc

    requirements = payload.get("acceptance_requires")
    if not isinstance(requirements, dict) or set(requirements) != {
        "official_bootstrap_success_count",
        "official_bootstrap_failure_count",
        "attachment_binary_capture",
        "attachment_parser_pass",
        "agnes_authenticated_contract_smoke",
    }:
        raise PilotHostAcceptanceError("ACCEPTANCE_REQUIREMENTS_INVALID")
    expected_success = requirements.get("official_bootstrap_success_count")
    if (
        not isinstance(expected_success, int)
        or isinstance(expected_success, bool)
        or expected_success < 1
        or expected_success > 50
        or requirements.get("official_bootstrap_failure_count") != 0
        or requirements.get("attachment_binary_capture") is not True
        or requirements.get("attachment_parser_pass") is not True
        or requirements.get("agnes_authenticated_contract_smoke") is not True
    ):
        raise PilotHostAcceptanceError("ACCEPTANCE_REQUIREMENTS_INVALID")

    return HostAcceptanceManifest(
        bootstrap_manifest=bootstrap_manifest,
        attachment_project_code=project_code,
        attachment_filename=filename,
        attachment_url=url,
        expected_bootstrap_success_count=expected_success,
    )


def _safe_error(exc: Exception) -> dict[str, Any]:
    code = getattr(exc, "code", None) or getattr(exc, "error_class", None) or type(exc).__name__
    return {"status": "FAIL", "error_class": str(code)[:120]}


def _validate_environment(environ: Mapping[str, str]) -> tuple[str, str]:
    origin = (environ.get("MCAI_CANONICAL_ORIGIN") or "").strip()
    api_key = (environ.get("MCAI_AGNES_API_KEY") or "").strip()
    if not origin:
        raise PilotHostAcceptanceError("MCAI_CANONICAL_ORIGIN_MISSING")
    if not api_key:
        raise PilotHostAcceptanceError("MCAI_AGNES_API_KEY_MISSING")
    CanonicalOriginPolicy.parse(origin)
    base_url = (environ.get("MCAI_AGNES_BASE_URL") or DEFAULT_BASE_URL).strip()
    base_url = validate_base_url(base_url)
    return api_key, base_url


def _bootstrap_result(
    *,
    exit_code: int,
    summary: dict[str, Any],
    expected_success_count: int,
) -> dict[str, Any]:
    success = summary.get("success_count")
    failure = summary.get("failure_count")
    passed = exit_code == 0 and success == expected_success_count and failure == 0
    rows = []
    for item in summary.get("results") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "expected_project_code": item.get("expected_project_code"),
                "status": item.get("status"),
                "verification_status": item.get("verification_status"),
                "lifecycle_state": item.get("lifecycle_state"),
                "product_label_count": len(item.get("product_labels") or []),
                "error_type": item.get("error_type"),
            }
        )
    return {
        "status": "PASS" if passed else "FAIL",
        "success_count": success,
        "failure_count": failure,
        "results": rows,
    }


def _attachment_result(result: dict[str, Any], *, expected_project_code: str) -> dict[str, Any]:
    sha256 = result.get("sha256")
    passed = (
        result.get("status_code") == 200
        and isinstance(result.get("size_bytes"), int)
        and result.get("size_bytes") > 0
        and isinstance(sha256, str)
        and len(sha256) == 64
        and isinstance(result.get("parser_version"), str)
        and bool(result.get("parser_version"))
        and isinstance(result.get("block_count"), int)
        and result.get("block_count") > 0
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "project_code": expected_project_code,
        "content_type": result.get("content_type"),
        "size_bytes": result.get("size_bytes"),
        "sha256": sha256,
        "parser_version": result.get("parser_version"),
        "block_count": result.get("block_count"),
        "taxonomy_validation_status": result.get("taxonomy_validation_status"),
        "taxonomy_labels": list(result.get("taxonomy_labels") or []),
    }


def _provider_result(result: dict[str, Any]) -> dict[str, Any]:
    passed = result.get("status") == "PASS" and result.get("contract_validation_passed") is True
    safe = {
        "status": "PASS" if passed else "FAIL",
        "provider_call_executed": bool(result.get("provider_call_executed")),
        "contract_validation_passed": bool(result.get("contract_validation_passed")),
        "lease_status": result.get("lease_status"),
    }
    if passed:
        safe["action_type"] = result.get("action_type")
        safe["supporting_fact_count"] = result.get("supporting_fact_count")
        safe["requires_human_confirmation"] = result.get("requires_human_confirmation")
    else:
        safe["error_class"] = result.get("error_class")
        safe["retryable"] = result.get("retryable")
        safe["retry_after"] = result.get("retry_after")
    return safe


def run_host_acceptance(
    *,
    manifest_path: Path,
    environ: Mapping[str, str] | None = None,
    bootstrap_runner: Callable[..., tuple[int, dict[str, Any]]] = run_seed,
    attachment_runner: Callable[..., dict[str, Any]] = probe_attachment,
    provider_runner: Callable[..., dict[str, Any]] = run_provider_smoke,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    manifest = load_acceptance_manifest(manifest_path)
    env = os.environ if environ is None else environ

    try:
        api_key, base_url = _validate_environment(env)
        environment_result: dict[str, Any] = {"status": "PASS"}
    except Exception as exc:
        return {
            "schema_version": "0.1",
            "status": "FAIL",
            "environment": _safe_error(exc),
            "official_bootstrap": {"status": "SKIPPED"},
            "attachment": {"status": "SKIPPED"},
            "agnes_provider": {"status": "SKIPPED"},
            "production_data_touched": False,
        }

    repo_root = manifest_path.resolve().parent.parent
    bootstrap_manifest_path = repo_root / manifest.bootstrap_manifest

    with tempfile.TemporaryDirectory(prefix="mcai-pilot-host-acceptance-") as temp_dir:
        temp_root = Path(temp_dir)
        bootstrap_db = temp_root / "bootstrap.sqlite"
        lease_db = temp_root / "agnes-lease.sqlite"

        try:
            exit_code, summary = bootstrap_runner(
                db_path=bootstrap_db,
                manifest_path=bootstrap_manifest_path,
            )
            bootstrap_result = _bootstrap_result(
                exit_code=exit_code,
                summary=summary,
                expected_success_count=manifest.expected_bootstrap_success_count,
            )
        except Exception as exc:
            bootstrap_result = _safe_error(exc)

        try:
            attachment_raw = attachment_runner(
                url=manifest.attachment_url,
                filename=manifest.attachment_filename,
            )
            attachment_result = _attachment_result(
                attachment_raw,
                expected_project_code=manifest.attachment_project_code,
            )
        except Exception as exc:
            attachment_result = _safe_error(exc)
            attachment_result["project_code"] = manifest.attachment_project_code

        try:
            provider_raw = provider_runner(
                api_key=api_key,
                base_url=base_url,
                lease_db_path=lease_db,
            )
            provider_result = _provider_result(provider_raw)
        except Exception as exc:
            provider_result = _safe_error(exc)

    passed = all(
        item.get("status") == "PASS"
        for item in (environment_result, bootstrap_result, attachment_result, provider_result)
    )
    return {
        "schema_version": "0.1",
        "status": "PASS" if passed else "FAIL",
        "environment": environment_result,
        "official_bootstrap": bootstrap_result,
        "attachment": attachment_result,
        "agnes_provider": provider_result,
        "production_data_touched": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run fail-closed Tianjin Pilot host acceptance using only temporary SQLite, "
            "official public URLs and synthetic Agnes smoke data."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_ACCEPTANCE_MANIFEST)
    args = parser.parse_args()
    try:
        result = run_host_acceptance(manifest_path=args.manifest)
    except Exception as exc:
        result = {
            "schema_version": "0.1",
            "status": "FAIL",
            "manifest": _safe_error(exc),
            "production_data_touched": False,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
