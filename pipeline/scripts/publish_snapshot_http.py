from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 15.0
ALLOWED_METHODS = {"PUT", "POST"}


class SnapshotPublishError(RuntimeError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def validate_publish_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_URL_REQUIRED")
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_URL_MUST_BE_HTTPS")
    if parsed.username or parsed.password:
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_URL_USERINFO_REJECTED")
    return raw


def load_snapshot_payload(path: Path) -> bytes:
    payload = path.read_bytes()
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_PAYLOAD_TOO_LARGE")
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_JSON_INVALID") from exc
    if not isinstance(parsed, dict):
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_ROOT_INVALID")
    if parsed.get("schema_version") != "0.1" or parsed.get("mode") != "TODAY_ACTIONS":
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_SCHEMA_INVALID")
    snapshot_as_of = parsed.get("snapshot_as_of")
    if not isinstance(snapshot_as_of, str) or not snapshot_as_of.strip():
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_AS_OF_INVALID")
    if not isinstance(parsed.get("cards"), list):
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_CARDS_INVALID")
    return payload


def build_request(
    *,
    url: str,
    payload: bytes,
    method: str,
    bearer_token: str | None,
) -> urllib.request.Request:
    normalized_method = method.strip().upper()
    if normalized_method not in ALLOWED_METHODS:
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_METHOD_REJECTED")
    digest = hashlib.sha256(payload).hexdigest()
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(payload)),
        "X-Content-SHA256": digest,
        "User-Agent": "MedicalChannelAI-VerifiedSnapshotPublisher/0.1",
    }
    token = (bearer_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(
        url=url,
        data=payload,
        headers=headers,
        method=normalized_method,
    )


def publish_snapshot(
    *,
    snapshot_path: Path,
    publish_url: str,
    bearer_token: str | None,
    method: str,
    timeout_seconds: float,
) -> tuple[int, str]:
    if timeout_seconds <= 0 or timeout_seconds > 60:
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_TIMEOUT_INVALID")
    url = validate_publish_url(publish_url)
    payload = load_snapshot_payload(snapshot_path)
    request = build_request(
        url=url,
        payload=payload,
        method=method,
        bearer_token=bearer_token,
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 0) or 0)
            if status < 200 or status >= 300:
                raise SnapshotPublishError(f"SNAPSHOT_PUBLISH_HTTP_{status}")
    except urllib.error.HTTPError as exc:
        raise SnapshotPublishError(f"SNAPSHOT_PUBLISH_HTTP_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SnapshotPublishError("SNAPSHOT_PUBLISH_NETWORK_ERROR") from exc
    return status, hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a verified public snapshot to a configured HTTPS endpoint."
    )
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--method", default="PUT", choices=sorted(ALLOWED_METHODS))
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--url-env",
        default="VERIFIED_SNAPSHOT_PUBLISH_URL",
        help="Environment variable containing the HTTPS publish URL.",
    )
    parser.add_argument(
        "--token-env",
        default="VERIFIED_SNAPSHOT_PUBLISH_TOKEN",
        help="Optional environment variable containing a Bearer token.",
    )
    args = parser.parse_args()

    publish_url = os.environ.get(args.url_env, "")
    bearer_token = os.environ.get(args.token_env, "")
    try:
        status, digest = publish_snapshot(
            snapshot_path=args.snapshot,
            publish_url=publish_url,
            bearer_token=bearer_token,
            method=args.method,
            timeout_seconds=args.timeout_seconds,
        )
    except SnapshotPublishError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    host = urlparse(validate_publish_url(publish_url)).hostname or "unknown"
    print(f"snapshot published: host={host} status={status} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
