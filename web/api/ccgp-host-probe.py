from __future__ import annotations

import hmac
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

WEB_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = WEB_ROOT / "pipeline"
SCRIPT_DIR = PIPELINE_ROOT / "scripts"
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from medical_channel_pipeline.ccgp_discovery import build_search_url, fetch_search_page, parse_search_html  # noqa: E402
from sync_tianjin_plan import load_plan, plan_date_window  # noqa: E402

_ACCEPTANCE_PROBE = "mca-v023-8f3a6d9c2e7141c9b84fd87a52f64c11"
SHANGHAI = ZoneInfo("Asia/Shanghai")


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        supplied = str(self.headers.get("x-medicalchannelai-probe") or "")
        if not supplied or not hmac.compare_digest(supplied, _ACCEPTANCE_PROBE):
            return self._send_json(403, {"error": "PROBE_FORBIDDEN"})

        try:
            plan = load_plan(PIPELINE_ROOT / "data" / "tianjin_query_plan.json")
            now = datetime.now(timezone.utc)
            start_date, end_date = plan_date_window(now, plan["lookback_days"])
            keyword = plan["keywords"][0]
            notice_type = plan["notice_types"][0]
            search_url = build_search_url(
                keyword=keyword,
                region=plan["region"],
                notice_type=notice_type,
                page_index=1,
                start_date=start_date,
                end_date=end_date,
            )
            html = fetch_search_page(search_url)
            candidates = parse_search_html(html, keyword=keyword)
            hosts = Counter((urlparse(item.detail_url).hostname or "").lower() for item in candidates)
            samples = [
                {
                    "host": (urlparse(item.detail_url).hostname or "").lower(),
                    "url": item.detail_url,
                    "title": item.title,
                }
                for item in candidates[:5]
            ]
            return self._send_json(
                200,
                {
                    "schema_version": "0.1",
                    "source": "CCGP_PUBLIC_SEARCH",
                    "region": plan["region"],
                    "keyword": keyword,
                    "notice_type": notice_type,
                    "start_date": start_date,
                    "end_date": end_date,
                    "candidate_count": len(candidates),
                    "host_counts": dict(hosts),
                    "samples": samples,
                },
            )
        except Exception as exc:
            return self._send_json(
                503,
                {
                    "error": "CCGP_HOST_PROBE_FAILED",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:300],
                },
            )

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
