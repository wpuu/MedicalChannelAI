#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medical_channel_pipeline import build_public_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a frontend-safe MedicalChannelAI snapshot")
    parser.add_argument(
        "--input",
        required=True,
        action="append",
        type=Path,
        help="Verified canonical-record JSON array. Repeat --input to merge official source classes.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--as-of", required=True, help="ISO-8601 timestamp, e.g. 2026-08-31T08:00:00+00:00")
    args = parser.parse_args()

    records = []
    for path in args.input:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"input must contain a JSON array: {path}")
        records.extend(payload)

    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    payload = build_public_snapshot(records, as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
