from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

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


def _starter_profile(*, tenant_id: str, company_name: str, now: datetime) -> dict[str, Any]:
    """Create a safe, schema-shaped profile that cannot be personalized yet."""

    return {
        "schema_version": "0.1",
        "profile_id": f"mprof_{uuid.uuid4()}",
        "tenant_id": tenant_id,
        "company_name": company_name,
        "business_role": "OTHER",
        "operating_regions": [
            {
                "province": "天津市",
                "city": "天津市",
                "scope_mode": "ENTIRE_CITY",
                "districts": [],
            }
        ],
        "customer_types": ["OTHER"],
        "product_capabilities": [
            {
                "category": "待客户填写",
                "subcategory": None,
                "taxonomy_ids": ["MEDICAL_CONSUMABLE_GENERAL"],
                "brands": [],
                "capability_type": "UNKNOWN",
                "notes": "BOOTSTRAP_PLACEHOLDER_NOT_CUSTOMER_CONFIRMED",
            }
        ],
        "partnering_policy": {
            "can_seek_temporary_manufacturer": False,
            "can_cooperate_with_channel_partner": False,
            "can_do_rental_projects": False,
        },
        "opportunity_thresholds": {
            "minimum_project_amount_cny": "0",
            "owner_attention_amount_cny": None,
            "preferred_stages": ["PROCUREMENT_INTENT"],
        },
        "exclusion_rules": [],
        "hospital_relationships": [],
        "confirmation_flags": {
            "region_scope_confirmed": False,
            "customer_types_confirmed": False,
            "product_capabilities_confirmed": False,
            "partnering_policy_confirmed": False,
            "opportunity_preferences_confirmed": False,
            "exclusion_rules_confirmed": False,
        },
        "profile_status": "INCOMPLETE",
        "profile_completeness": 0,
        "missing_required_conditions": ["CUSTOMER_PROFILE_NOT_CONFIRMED"],
        "updated_at": now.astimezone(timezone.utc).isoformat(),
    }


def _invite_result(*, issued, login_url: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "type": "one_time_invite",
        "code": issued.code,
        "expires_at": issued.expires_at.astimezone(timezone.utc).isoformat(),
        "warning": "This code is shown once. Do not commit it or paste it into logs/issues.",
    }
    if login_url:
        base = str(login_url).rstrip("/")
        result["login_url"] = f"{base}/login#code={issued.code}"
    return result


def _account_json(account) -> dict[str, Any]:
    return {
        "tenant_id": account.tenant_id,
        "profile_id": account.profile_id,
        "company_name": account.company_name,
        "status": account.status,
        "created_at": account.created_at,
        "activated_at": account.activated_at,
        "disabled_at": account.disabled_at,
        "last_login_at": account.last_login_at,
    }


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

    invite = subparsers.add_parser("invite", help="issue a fresh one-time login link for an account")
    invite.add_argument("--tenant", required=True)
    invite.add_argument("--profile", required=True)
    invite.add_argument("--ttl", type=int, default=1800)
    invite.add_argument("--login-url", default=None)

    bootstrap = subparsers.add_parser(
        "bootstrap-invite",
        help="create an INVITED Pilot account/profile and issue its registration link",
    )
    bootstrap.add_argument("--tenant", default=None, help="optional stable tenant id; generated when omitted")
    bootstrap.add_argument("--company", required=True)
    bootstrap.add_argument("--ttl", type=int, default=1800)
    bootstrap.add_argument("--login-url", default=None)

    for name, help_text in (
        ("account-status", "show one Pilot account lifecycle record"),
        ("account-disable", "disable one Pilot account immediately"),
        ("account-enable", "restore one disabled Pilot account"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--tenant", required=True)
        command.add_argument("--profile", required=True)

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
        principal = TrustedPrincipal(args.tenant, args.profile)
        issued = runtime.issue_profile_invite(
            principal=principal,
            now=now,
            ttl_seconds=args.ttl,
        )
        result = _invite_result(issued=issued, login_url=args.login_url)
        result["type"] = "account_login_invite"
        _print(result)
        return

    if args.command == "bootstrap-invite":
        now = datetime.now(timezone.utc)
        tenant_id = str(args.tenant).strip() if args.tenant else f"tenant_{uuid.uuid4()}"
        company_name = str(args.company).strip()
        if not company_name:
            raise ValueError("company is required")
        profile = _starter_profile(tenant_id=tenant_id, company_name=company_name, now=now)
        runtime.repository.upsert_profile(profile)
        principal = TrustedPrincipal(tenant_id, profile["profile_id"])
        issued = runtime.issue_profile_invite(
            principal=principal,
            now=now,
            ttl_seconds=args.ttl,
        )
        account = runtime.account_store.get(principal)
        if account is None:
            raise RuntimeError("account was not provisioned")
        result = _invite_result(issued=issued, login_url=args.login_url)
        result["type"] = "customer_registration_invite"
        result["tenant_id"] = tenant_id
        result["profile_id"] = profile["profile_id"]
        result["account_status"] = account.status
        _print(result)
        return

    if args.command in {"account-status", "account-disable", "account-enable"}:
        now = datetime.now(timezone.utc)
        principal = TrustedPrincipal(args.tenant, args.profile)
        if args.command == "account-disable":
            if not runtime.account_store.set_disabled(principal, disabled=True, now=now):
                raise ValueError("account not found")
        elif args.command == "account-enable":
            if not runtime.account_store.set_disabled(principal, disabled=False, now=now):
                raise ValueError("account not found")
        account = runtime.account_store.get(principal)
        if account is None:
            raise ValueError("account not found")
        _print({"ok": True, "type": "account", "account": _account_json(account)})
        return

    raise RuntimeError("unsupported command")


if __name__ == "__main__":
    main()
