"""Offline historical comparison; no network, cache writes, collection or new clock.

Run from any directory with --baseline pointing at the saved DATABASE response.
This uses the static publication pipeline, not collector_runtime._run_publish.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PIPELINE = ROOT / "web/pipeline"
sys.path.insert(0, str(PIPELINE))
from medical_channel_pipeline import build_public_snapshot
from medical_channel_pipeline.validation import validate_records
from medical_channel_pipeline.ccgp_events import validate_notice_events

SPEC = importlib.util.spec_from_file_location("static_publish", PIPELINE / "scripts/publish_web_snapshot.py")
PUBLISH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLISH)
PRODUCTION = "62299590dd3898e040ccc9db5fda1298d4509d51"
FILES = [
    "tianjin_live_ccgp_records.json", "tianjin_live_tjmugh_records.json",
    "tianjin_live_tjnothop_records.json", "tianjin_live_tjzxfc_records.json",
    "tianjin_live_tjzyefy_records.json", "tianjin_live_tjzyefy_intent_records.json",
    "tianjin_live_teda_records.json", "tianjin_live_tjfch_records.json",
    "regional_live_ccgp_records.json",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    baseline_bytes = args.baseline.read_bytes()
    baseline = json.loads(baseline_bytes)
    as_of = datetime.fromisoformat(baseline["snapshot_as_of"].replace("Z", "+00:00"))
    assert as_of.tzinfo is not None
    with tempfile.TemporaryDirectory(prefix="medicalchannelai-history-") as directory:
        paths = []
        for filename in [*FILES, "tianjin_notice_events.json"]:
            raw = subprocess.check_output(
                ["git", "show", f"{PRODUCTION}:web/pipeline/data/{filename}"], cwd=ROOT,
            )
            path = Path(directory) / filename
            path.write_bytes(raw)
            if filename in FILES:
                validate_records(json.loads(raw))
                paths.append(path)
            else:
                events = validate_notice_events(json.loads(raw))
        # Same source-specific metadata normalization as static publication.
        records = PUBLISH.load_arrays(paths, label="historical canonical")
    tianjin = [row for row in records if row["facts"]["market_code"] == "TJ"]
    regional = [row for row in records if row["facts"]["market_code"] != "TJ"]
    rebuilt = PUBLISH.combine_snapshots(
        build_public_snapshot(tianjin, as_of, events),
        build_public_snapshot(regional, as_of, []), records, as_of,
    )
    actual = {row["opportunity_id"]: row for row in baseline["opportunity_pool"]}
    expected = {row["opportunity_id"]: row for row in rebuilt["opportunity_pool"]}
    differing = [key for key in actual.keys() & expected.keys() if actual[key] != expected[key]]
    files = [
        PIPELINE / "scripts/publish_web_snapshot.py",
        PIPELINE / "medical_channel_pipeline/public_snapshot.py",
        PIPELINE / "medical_channel_pipeline/validation.py",
    ]
    print(json.dumps({
        "canonical_source_commit": PRODUCTION,
        "transform": "current checked-out static publication pipeline; load_arrays market normalization, separate TJ/events and regional builds, combine_snapshots metadata injection and global reranking",
        "transform_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "baseline_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "historical_as_of": as_of.isoformat(), "canonical_count": len(records),
        "rebuilt_pool_count": len(expected), "baseline_pool_count": len(actual),
        "ids_only_in_baseline": sorted(actual.keys() - expected.keys()),
        "ids_only_in_rebuilt": sorted(expected.keys() - actual.keys()),
        "different_card_count": len(differing),
        "candidate_runtime_recovery_verified": False,
        "network_or_production_writes": False,
    }, ensure_ascii=False, indent=2))
    assert actual == expected, "Historical static-publication card comparison failed"


if __name__ == "__main__":
    main()
