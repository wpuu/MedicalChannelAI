from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .collector_ingest import collect_and_persist_url
from .registry import resolve_source


DEFAULT_MANIFEST = Path("deploy/tianjin-pilot-bootstrap-urls-2026-08-30.json")


@dataclass(frozen=True)
class SeedEntry:
    expected_project_code: str
    url: str


def _required_text(value: Any, name: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    text = value.strip()
    if len(text) > max_length:
        raise ValueError(f"{name} is too long")
    return text


def load_manifest(path: Path) -> list[SeedEntry]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("schema_version") != "0.1":
        raise ValueError("bootstrap manifest schema_version must be 0.1")
    if set(payload) != {"schema_version", "purpose", "snapshot_date", "entries"}:
        raise ValueError("bootstrap manifest contains unsupported fields")
    _required_text(payload.get("purpose"), "purpose", max_length=500)
    _required_text(payload.get("snapshot_date"), "snapshot_date", max_length=32)
    entries_raw = payload.get("entries")
    if not isinstance(entries_raw, list) or not entries_raw or len(entries_raw) > 50:
        raise ValueError("bootstrap manifest entries must contain 1..50 items")

    result: list[SeedEntry] = []
    seen_urls: set[str] = set()
    seen_codes: set[str] = set()
    for index, item in enumerate(entries_raw):
        if not isinstance(item, dict) or set(item) != {"expected_project_code", "url"}:
            raise ValueError(f"entries[{index}] must contain expected_project_code and url only")
        code = _required_text(item.get("expected_project_code"), f"entries[{index}].expected_project_code", max_length=100)
        url = _required_text(item.get("url"), f"entries[{index}].url", max_length=1000)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError(f"entries[{index}].url must be a plain HTTPS official detail URL")
        if url in seen_urls or code in seen_codes:
            raise ValueError("bootstrap manifest contains duplicate URL or project code")
        source = resolve_source(url)
        if source.authority_type != "OFFICIAL_GOVERNMENT":
            raise ValueError("bootstrap source must be an enabled official government source")
        seen_urls.add(url)
        seen_codes.add(code)
        result.append(SeedEntry(expected_project_code=code, url=url))
    return result


def _opportunity_summary(opportunity: dict[str, Any]) -> dict[str, Any]:
    return {
        "opportunity_id": opportunity.get("opportunity_id"),
        "project_name": opportunity.get("project_name"),
        "verification_status": opportunity.get("verification_status"),
        "lifecycle_state": opportunity.get("lifecycle_state"),
        "product_labels": list(opportunity.get("product_labels") or []),
    }


def run_seed(
    *,
    db_path: Path,
    manifest_path: Path,
    collector: Callable[..., tuple[Any, dict[str, Any]]] = collect_and_persist_url,
) -> tuple[int, dict[str, Any]]:
    entries = load_manifest(manifest_path)
    rows: list[dict[str, Any]] = []
    success = 0
    for index, entry in enumerate(entries):
        try:
            collected, opportunity = collector(entry.url, db_path=Path(db_path))
            parsed_code = getattr(collected.parsed, "project_number", None) or getattr(collected.parsed, "project_code", None)
            if parsed_code is not None and str(parsed_code).strip() != entry.expected_project_code:
                raise ValueError("collected project code does not match manifest expectation")
            row = {
                "index": index,
                "status": "OK",
                "expected_project_code": entry.expected_project_code,
                **_opportunity_summary(opportunity),
            }
            success += 1
        except Exception as exc:
            row = {
                "index": index,
                "status": "FAILED",
                "expected_project_code": entry.expected_project_code,
                "error_type": type(exc).__name__,
            }
        rows.append(row)

    summary = {
        "schema_version": "0.1",
        "input_count": len(entries),
        "success_count": success,
        "failure_count": len(entries) - success,
        "results": rows,
        "warning": "Only official public facts were imported. Customer context and Agnes decisions are never seeded.",
    }
    if success == len(entries):
        return 0, summary
    if success > 0:
        return 1, summary
    return 2, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap real Tianjin public procurement URLs into Pilot SQLite")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    exit_code, summary = run_seed(db_path=args.db, manifest_path=args.manifest)
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
