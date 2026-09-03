#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PIPELINE_ROOT.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline import build_public_snapshot  # noqa: E402


def load_array(path: Path, *, label: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{label} must contain a JSON array")
    return payload


def main() -> int:
    output = WEB_ROOT / "public" / "data" / "today-actions.public.json"
    current = json.loads(output.read_text(encoding="utf-8"))
    published_as_of = datetime.fromisoformat(
        current["snapshot_as_of"].replace("Z", "+00:00")
    )

    live_ccgp = load_array(
        PIPELINE_ROOT / "data" / "tianjin_live_ccgp_records.json",
        label="live CCGP state",
    )
    live_tjmugh = load_array(
        PIPELINE_ROOT / "data" / "tianjin_live_tjmugh_records.json",
        label="live TMUGH state",
    )
    live_tjnothop = load_array(
        PIPELINE_ROOT / "data" / "tianjin_live_tjnothop_records.json",
        label="live Tianjin Hospital state",
    )
    live_teda = load_array(
        PIPELINE_ROOT / "data" / "tianjin_live_teda_records.json",
        label="live TEDA Hospital state",
    )
    live_tjfch = load_array(
        PIPELINE_ROOT / "data" / "tianjin_live_tjfch_records.json",
        label="live First Central Hospital state",
    )

    ccgp_source = live_ccgp if live_ccgp else load_array(
        PIPELINE_ROOT / "data" / "tianjin_verified_seed.json",
        label="CCGP seed",
    )
    tmugh_source = live_tjmugh if live_tjmugh else load_array(
        PIPELINE_ROOT / "data" / "tianjin_official_institution_seed.json",
        label="TMUGH seed",
    )
    notice_events = load_array(
        PIPELINE_ROOT / "data" / "tianjin_notice_events.json",
        label="notice events",
    )

    payload = build_public_snapshot(
        [*ccgp_source, *tmugh_source, *live_tjnothop, *live_teda, *live_tjfch],
        published_as_of,
        notice_events,
    )
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Bundled snapshot refreshed with current ranking logic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
