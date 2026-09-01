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
DEFAULT_TIMEOUT_SECONDS = 12.0


class SnapshotRoundTripError(RuntimeError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def validate_read_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise SnapshotRoundTripError("SNAPSHOT_READ_URL_REQUIRED")
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SnapshotRoundTripError("SNAPSHOT_READ_URL_MUST_BE_HTTPS")
    if parsed.username or parsed.password:
        raise SnapshotRoundTripError("SNAPSHOT_READ_URL_USERINFO_REJECTED")
    return raw


def _load_json_bytes(payload: bytes, *, source: str) -> dict:
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise SnapshotRoundTripError(f"SNAPSHOT_{source}_TOO_LARGE")
    try:
        root = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotRoundTripError(f"SNAPSHOT_{source}_JSON_INVALID") from exc
    if not isinstance(root, dict):
        raise SnapshotRoundTripError(f"SNAPSHOT_{source}_ROOT_INVALID")
    if root.get("schema_version") != "0.1" or root.get("mode") != "TODAY_ACTIONS":
        raise SnapshotRoundTripError(f"SNAPSHOT_{source}_SCHEMA_INVALID")
    if not isinstance(root.get("snapshot_as_of"), str) or not root["snapshot_as_of"].strip():
        raise SnapshotRoundTripError(f"SNAPSHOT_{source}_AS_OF_INVALID")
    if not isinstance(root.get("cards"), list):
        raise SnapshotRoundTripError(f"SNAPSHOT_{source}_CARDS_INVALID")
    pool = root.get("opportunity_pool", root["cards"])
    if not isinstance(pool, list):
        raise SnapshotRoundTripError(f"SNAPSHOT_{source}_POOL_INVALID")
    return root


def load_local_snapshot(path: Path) -> tuple[bytes, dict]:
    payload = path.read_bytes()
    return payload, _load_json_bytes(payload, source="LOCAL")


def fetch_remote_snapshot(url: str, *, timeout_seconds: float) -> tuple[bytes, dict]:
    if timeout_seconds <= 0 or timeout_seconds > 60:
        raise SnapshotRoundTripError("SNAPSHOT_READ_TIMEOUT_INVALID")
    read_url = validate_read_url(url)
    request = urllib.request.Request(
        read_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "MedicalChannelAI-SnapshotRoundTripVerifier/0.1",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 0) or 0)
            if status < 200 or status >= 300:
                raise SnapshotRoundTripError(f"SNAPSHOT_READ_HTTP_{status}")
            declared_length = int(response.headers.get("Content-Length") or "0")
            if declared_length > MAX_SNAPSHOT_BYTES:
                raise SnapshotRoundTripError("SNAPSHOT_REMOTE_TOO_LARGE")
            payload = response.read(MAX_SNAPSHOT_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise SnapshotRoundTripError(f"SNAPSHOT_READ_HTTP_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SnapshotRoundTripError("SNAPSHOT_READ_NETWORK_ERROR") from exc
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise SnapshotRoundTripError("SNAPSHOT_REMOTE_TOO_LARGE")
    return payload, _load_json_bytes(payload, source="REMOTE")


def _opportunity_ids(items: list, *, label: str) -> list[str]:
    ids: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SnapshotRoundTripError(f"SNAPSHOT_{label}_CARD_INVALID:{index}")
        opportunity_id = item.get("opportunity_id")
        if not isinstance(opportunity_id, str) or not opportunity_id.strip():
            raise SnapshotRoundTripError(f"SNAPSHOT_{label}_ID_INVALID:{index}")
        ids.append(opportunity_id)
    if len(ids) != len(set(ids)):
        raise SnapshotRoundTripError(f"SNAPSHOT_{label}_DUPLICATE_ID")
    return ids


def compare_snapshots(local: dict, remote: dict) -> dict[str, object]:
    local_cards = local["cards"]
    remote_cards = remote["cards"]
    local_pool = local.get("opportunity_pool", local_cards)
    remote_pool = remote.get("opportunity_pool", remote_cards)

    local_card_ids = _opportunity_ids(local_cards, label="LOCAL_TOP5")
    remote_card_ids = _opportunity_ids(remote_cards, label="REMOTE_TOP5")
    local_pool_ids = _opportunity_ids(local_pool, label="LOCAL_POOL")
    remote_pool_ids = _opportunity_ids(remote_pool, label="REMOTE_POOL")

    checks = {
        "snapshot_as_of": local.get("snapshot_as_of") == remote.get("snapshot_as_of"),
        "top5_ids": local_card_ids == remote_card_ids,
        "pool_ids": local_pool_ids == remote_pool_ids,
        "card_count": local.get("card_count") == remote.get("card_count") == len(local_cards),
        "matched_count": local.get("matched_count") == remote.get("matched_count"),
        "pool_count": (
            local.get("opportunity_pool_count", len(local_pool))
            == remote.get("opportunity_pool_count", len(remote_pool))
            == len(local_pool)
            == len(remote_pool)
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise SnapshotRoundTripError("SNAPSHOT_ROUNDTRIP_MISMATCH:" + ",".join(failed))
    return {
        "snapshot_as_of": local["snapshot_as_of"],
        "today_card_count": len(local_cards),
        "opportunity_pool_count": len(local_pool),
        "checks": checks,
    }


def verify_roundtrip(
    *,
    local_path: Path,
    read_url: str,
    timeout_seconds: float,
) -> dict[str, object]:
    local_bytes, local = load_local_snapshot(local_path)
    remote_bytes, remote = fetch_remote_snapshot(read_url, timeout_seconds=timeout_seconds)
    result = compare_snapshots(local, remote)
    local_sha = hashlib.sha256(local_bytes).hexdigest()
    remote_sha = hashlib.sha256(remote_bytes).hexdigest()
    result["local_sha256"] = local_sha
    result["remote_sha256"] = remote_sha
    result["byte_identical"] = local_sha == remote_sha
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a published read-only snapshot matches the local verified snapshot."
    )
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--url-env",
        default="VERIFIED_SNAPSHOT_READ_URL",
        help="Environment variable containing the public/read-only HTTPS snapshot URL.",
    )
    args = parser.parse_args()

    read_url = os.environ.get(args.url_env, "")
    try:
        result = verify_roundtrip(
            local_path=args.snapshot,
            read_url=read_url,
            timeout_seconds=args.timeout_seconds,
        )
    except SnapshotRoundTripError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    host = urlparse(validate_read_url(read_url)).hostname or "unknown"
    print(
        "snapshot round-trip verified: "
        f"host={host} as_of={result['snapshot_as_of']} "
        f"today={result['today_card_count']} pool={result['opportunity_pool_count']} "
        f"byte_identical={str(result['byte_identical']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
