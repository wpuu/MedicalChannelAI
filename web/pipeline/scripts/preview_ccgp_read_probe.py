"""One read-only CCGP query during the named Vercel Preview build; never publishes."""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from medical_channel_pipeline.ccgp_discovery import (  # noqa: E402
    build_search_url, classify_search_failure, fetch_search_page, parse_search_html,
)


def main() -> None:
    if (os.environ.get("VERCEL_ENV"), os.environ.get("VERCEL_GIT_COMMIT_REF")) != (
        "preview", "candidate/daily-refresh-preview-20261121"
    ):
        return
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    url = build_search_url(keyword="医院", notice_type="公开招标", region="天津",
                           start_date=(day - timedelta(days=2)).isoformat(),
                           end_date=day.isoformat())
    phase = "fetch"
    try:
        html = fetch_search_page(url, timeout_seconds=10)
        phase = "parse"
        rows = parse_search_html(html, keyword="医院", require_result_list=True)
        report = {"outcome": "QUERY_OK", "candidate_count": len(rows)}
    except Exception as exc:
        report = {"outcome": classify_search_failure(exc, phase=phase)}
    print("CCGP_PREVIEW_BUILD_PROBE=" + json.dumps({**report, "read_only": True}))


if __name__ == "__main__":
    main()
