from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .today_actions_http import TrustedPrincipal
from .today_runtime import build_sqlite_today_runtime


def _load_object(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def main() -> None:
    parser = argparse.ArgumentParser(description="MedicalChannelAI Pilot admin bootstrap")
    parser.add_argument("--db", required=True, type=Path, help="persistent Pilot SQLite path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_put = subparsers.add_parser("profile-put", help="upsert one tenant-private profile JSON")
    profile_put.add_argument("--file", required=True, type=Path)

    opportunity_put = subparsers.add_parser("opportunity-put", help="upsert one public opportunity JSON")
    opportunity_put.add_argument("--file", required=True, type=Path)

    evidence_put = subparsers.add_parser("evidence-put", help="upsert one public evidence JSON")
    evidence_put.add_argument("--file", required=True, type=Path)

    invite = subparsers.add_parser("invite", help="issue one-time login invite for an existing profile")
    invite.add_argument("--tenant", required=True)
    invite.add_argument("--profile", required=True)
    invite.add_argument("--ttl", type=int, default=1800)
    invite.add_argument("--login-url", default=None)

    args = parser.parse_args()
    runtime = build_sqlite_today_runtime(args.db)

    if args.command == "profile-put":
        profile = _load_object(args.file)
        runtime.repository.upsert_profile(profile)
        _print(
            {
                "ok": True,
                "type": "profile",
                "tenant_id": profile.get("tenant_id"),
                "profile_id": profile.get("profile_id"),
            }
        )
        return

    if args.command == "opportunity-put":
        item = _load_object(args.file)
        runtime.repository.upsert_public_opportunity(item)
        _print({"ok": True, "type": "opportunity", "opportunity_id": item.get("opportunity_id")})
        return

    if args.command == "evidence-put":
        item = _load_object(args.file)
        runtime.repository.upsert_public_evidence(item)
        _print(
            {
                "ok": True,
                "type": "evidence",
                "fact_id": item.get("fact_id"),
                "opportunity_id": item.get("opportunity_id"),
            }
        )
        return

    if args.command == "invite":
        now = datetime.now(timezone.utc)
        issued = runtime.issue_profile_invite(
            principal=TrustedPrincipal(args.tenant, args.profile),
            now=now,
            ttl_seconds=args.ttl,
        )
        result: dict[str, Any] = {
            "ok": True,
            "type": "one_time_invite",
            "code": issued.code,
            "expires_at": issued.expires_at.astimezone(timezone.utc).isoformat(),
            "warning": "This code is shown once. Do not commit it or paste it into logs/issues.",
        }
        if args.login_url:
            base = str(args.login_url).rstrip("/")
            result["login_url"] = f"{base}/login#code={issued.code}"
        _print(result)
        return

    raise RuntimeError("unsupported command")


if __name__ == "__main__":
    main()
