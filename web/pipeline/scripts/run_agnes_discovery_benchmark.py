#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline.agnes_discovery import (  # noqa: E402
    MAX_ANCHORS_PER_PROMPT,
    AgnesParseResult,
    build_agnes_discovery_messages,
    discovery_benchmark_metrics,
    extract_official_anchors,
    known_gold_urls_from_snapshot,
    parse_agnes_discovery_content,
)

DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL_ID = "agnes-2.5-flash"
MIN_FETCH_DELAY_SECONDS = 2.0


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def api_keys() -> list[str]:
    raw = os.environ.get("AGNES_API_KEYS") or os.environ.get("AGNES_API_KEY") or ""
    return [item.strip() for item in raw.replace(";", ",").replace("\n", ",").split(",") if item.strip()]


def fetch_html(url: str, *, timeout: int = 25) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "MedicalChannelAI/0.1 (+AI discovery shadow benchmark)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            declared = response.headers.get_content_charset()
    except HTTPError as exc:
        raise RuntimeError(f"SOURCE_HTTP_{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("SOURCE_NETWORK_ERROR") from exc

    encodings = [declared, "utf-8", "gb18030"]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def call_agnes(*, key: str, base_url: str, messages: list[dict[str, str]], timeout: int = 25) -> str:
    body = json.dumps(
        {
            "model": MODEL_ID,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 1800,
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


def batched(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def validate_registry(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("AGNES_SOURCE_REGISTRY_INVALID")
    result: list[dict] = []
    for row in payload["sources"]:
        if not isinstance(row, dict):
            raise ValueError("AGNES_SOURCE_REGISTRY_INVALID")
        source_id = str(row.get("source_id") or "").strip()
        display_name = str(row.get("display_name") or "").strip()
        seed_urls = row.get("seed_urls")
        allowed_hosts = row.get("allowed_hosts")
        if not source_id or not display_name or not isinstance(seed_urls, list) or not seed_urls:
            raise ValueError("AGNES_SOURCE_REGISTRY_INVALID")
        if not isinstance(allowed_hosts, list) or not allowed_hosts:
            raise ValueError("AGNES_SOURCE_REGISTRY_INVALID")
        result.append(
            {
                "source_id": source_id,
                "display_name": display_name,
                "seed_urls": [str(item) for item in seed_urls],
                "allowed_hosts": {str(item).lower() for item in allowed_hosts},
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Agnes as a shadow opportunity miner against official source indexes, then compare its discoveries "
            "with the repository's independently verified opportunity set. The AI output never enters production data."
        )
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=PIPELINE_ROOT / "data" / "agnes_discovery_sources.json",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=PIPELINE_ROOT.parent / "public" / "data" / "today-actions.public.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--fetch-delay-seconds", type=float, default=MIN_FETCH_DELAY_SECONDS)
    args = parser.parse_args()

    if args.fetch_delay_seconds < MIN_FETCH_DELAY_SECONDS:
        raise ValueError(f"--fetch-delay-seconds must be >= {MIN_FETCH_DELAY_SECONDS:g}")
    keys = api_keys()
    if not keys:
        raise RuntimeError("AGNES_API_KEY_NOT_CONFIGURED")
    base_url = os.environ.get("AGNES_API_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    registry = validate_registry(load_json(args.registry))
    if args.source_id:
        requested = set(args.source_id)
        registry = [item for item in registry if item["source_id"] in requested]
        missing = requested - {item["source_id"] for item in registry}
        if missing:
            raise ValueError(f"UNKNOWN_SOURCE_ID:{','.join(sorted(missing))}")
    snapshot = load_json(args.snapshot)
    if not isinstance(snapshot, dict):
        raise ValueError("VERIFIED_SNAPSHOT_INVALID")

    started_at = datetime.now(timezone.utc).isoformat()
    source_reports: list[dict] = []
    all_scores: list[float] = []

    for source_index, source in enumerate(registry):
        anchors = []
        failures: list[dict] = []
        for seed_index, seed_url in enumerate(source["seed_urls"]):
            if seed_index:
                time.sleep(args.fetch_delay_seconds)
            try:
                html = fetch_html(seed_url)
                anchors.extend(
                    extract_official_anchors(
                        html,
                        base_url=seed_url,
                        allowed_hosts=source["allowed_hosts"],
                    )
                )
            except Exception as exc:
                failures.append(
                    {
                        "stage": "seed_fetch",
                        "url": seed_url,
                        "error": type(exc).__name__,
                        "message": str(exc)[:200],
                    }
                )

        deduped = {item.url: item for item in anchors}
        anchors = list(deduped.values())
        parse_results: list[AgnesParseResult] = []
        candidate_rows: dict[str, dict] = {}
        for batch_index, batch in enumerate(batched(anchors, MAX_ANCHORS_PER_PROMPT)):
            if batch_index:
                time.sleep(0.4)
            key = keys[(source_index + batch_index) % len(keys)]
            try:
                content = call_agnes(
                    key=key,
                    base_url=base_url,
                    messages=build_agnes_discovery_messages(
                        source_name=source["display_name"],
                        anchors=batch,
                    ),
                )
                parsed = parse_agnes_discovery_content(content, allowed_anchors=batch)
                parse_results.append(parsed)
                for item in parsed.candidates:
                    candidate_rows[item.url] = {
                        "title": item.title,
                        "url": item.url,
                        "signal_type": item.signal_type,
                        "confidence": item.confidence,
                        "reason": item.reason,
                        "verification_status": "DISCOVERED_UNVERIFIED",
                    }
            except Exception as exc:
                failures.append(
                    {
                        "stage": "agnes_discovery",
                        "batch": batch_index,
                        "error": type(exc).__name__,
                        "message": str(exc)[:200],
                    }
                )

        gold_urls = known_gold_urls_from_snapshot(snapshot, allowed_hosts=source["allowed_hosts"])
        metrics = discovery_benchmark_metrics(parse_results, gold_urls=gold_urls)
        if isinstance(metrics["discovery_score"], (int, float)):
            all_scores.append(float(metrics["discovery_score"]))
        source_reports.append(
            {
                "source_id": source["source_id"],
                "display_name": source["display_name"],
                "seed_count": len(source["seed_urls"]),
                "official_anchor_count": len(anchors),
                "candidate_count": len(candidate_rows),
                "candidates": sorted(candidate_rows.values(), key=lambda row: (-row["confidence"], row["url"])),
                "metrics": metrics,
                "failure_count": len(failures),
                "failures": failures,
            }
        )

    overall = round(sum(all_scores) / len(all_scores), 1) if all_scores else None
    report = {
        "schema_version": "0.1",
        "mode": "AGNES_DISCOVERY_SHADOW_BENCHMARK",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "model_family": "agnes-2.5-flash",
        "production_data_mutated": False,
        "policy": {
            "manual_search_results_are_not_input": True,
            "official_index_links_are_the_only_candidate_url_surface": True,
            "ungrounded_model_urls_are_rejected": True,
            "ai_candidates_remain_unverified": True,
            "verified_repository_snapshot_is_gold_only_for_benchmarking": True,
            "novel_candidates_require_independent_official_verification_before_publish": True,
        },
        "overall_discovery_score": overall,
        "overall_score_scope": "KNOWN_VERIFIED_SET_ONLY",
        "sources": source_reports,
    }
    write_json(args.output, report)
    print(
        f"sources={len(source_reports)} overall_discovery_score={overall if overall is not None else 'NA'} "
        f"output={args.output}"
    )
    return 2 if any(item["failure_count"] for item in source_reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
