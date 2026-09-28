"""Pre-generate shared public AI decisions after a verified snapshot refresh.

Calls ``POST <url>?route=prewarm`` (token protected) in rounds until every
top candidate has a durable decision or the round budget is exhausted. Each
server round generates at most ``--limit`` decisions so it stays inside one
function invocation.

Best effort by design: a failed prewarm must never fail the data refresh, so
the script exits 0 unless ``--strict`` is given. Users still get on-demand AI
analysis when a decision is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_TIMEOUT_SECONDS = 75.0
TOKEN_ENV_NAMES = ("AI_PREWARM_TOKEN", "VERIFIED_SNAPSHOT_PUBLISH_TOKEN")


class PrewarmError(RuntimeError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def validate_url(value: str) -> str:
    raw = value.strip()
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PrewarmError("PREWARM_URL_MUST_BE_HTTPS")
    if parsed.username or parsed.password:
        raise PrewarmError("PREWARM_URL_USERINFO_REJECTED")
    separator = "&" if parsed.query else "?"
    return raw if "route=prewarm" in parsed.query else f"{raw}{separator}route=prewarm"


def resolve_token(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    for name in TOKEN_ENV_NAMES:
        value = str(env.get(name, "")).strip()
        if value:
            return value
    raise PrewarmError("PREWARM_TOKEN_REQUIRED")


def build_request(url: str, token: str, limit: int, max_candidates: int) -> urllib.request.Request:
    body = json.dumps({"limit": limit, "max_candidates": max_candidates}).encode("utf-8")
    return urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MedicalChannelAI-prewarm/1",
        },
    )


def post_round(opener, request: urllib.request.Request, timeout: float) -> dict:
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error")
        except Exception:  # noqa: BLE001 - diagnostics only
            detail = None
        raise PrewarmError(f"PREWARM_HTTP_{exc.code}:{detail or 'UNKNOWN'}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PrewarmError(f"PREWARM_TRANSPORT_FAILED:{type(exc).__name__}") from exc
    if not isinstance(payload, dict) or payload.get("mode") != "PREWARM":
        raise PrewarmError("PREWARM_RESPONSE_INVALID")
    return payload


def run(
    *,
    url: str,
    token: str,
    rounds: int,
    limit: int,
    max_candidates: int,
    timeout: float,
    pause_seconds: float,
    opener=None,
    sleep=time.sleep,
) -> dict:
    opener = opener or urllib.request.build_opener(_NoRedirectHandler)
    request_url = validate_url(url)
    totals = {"rounds": 0, "generated": 0, "errors": 0, "remaining": None, "already_cached": None}
    for index in range(max(1, rounds)):
        result = post_round(opener, build_request(request_url, token, limit, max_candidates), timeout)
        totals["rounds"] += 1
        totals["generated"] += int(result.get("generated_count") or 0)
        totals["errors"] += int(result.get("error_count") or 0)
        totals["remaining"] = int(result.get("remaining_miss_count") or 0)
        if totals["already_cached"] is None:
            totals["already_cached"] = int(result.get("already_cached_count") or 0)
        print(
            f"prewarm round {index + 1}: candidates={result.get('candidate_count')} "
            f"cached={result.get('already_cached_count')} generated={result.get('generated_count')} "
            f"errors={result.get('error_count')} remaining={result.get('remaining_miss_count')}",
            flush=True,
        )
        if totals["remaining"] == 0:
            break
        # Stop when a round makes no progress (e.g. provider outage) instead of
        # burning the whole round budget on the same failures.
        if int(result.get("generated_count") or 0) == 0:
            break
        if pause_seconds > 0:
            sleep(pause_seconds)
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("AI_PREWARM_URL", "https://medicalchannelai.vercel.app/api/ai/analyze"))
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-candidates", type=int, default=40)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    parser.add_argument("--strict", action="store_true", help="exit non-zero on failure")
    args = parser.parse_args(argv)

    try:
        totals = run(
            url=args.url,
            token=resolve_token(),
            rounds=args.rounds,
            limit=max(1, min(10, args.limit)),
            max_candidates=max(1, min(100, args.max_candidates)),
            timeout=args.timeout,
            pause_seconds=args.pause_seconds,
        )
    except PrewarmError as exc:
        print(f"AI prewarm skipped: {exc}", file=sys.stderr)
        return 2 if args.strict else 0
    print(f"AI prewarm summary: {json.dumps(totals, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
