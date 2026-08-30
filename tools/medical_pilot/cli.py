from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .award_items import extract_official_award_items
from .ccgp_lifecycle_adapter import ParsedCcgpLifecycleNotice
from .collector_core import FetchError
from .collector_ingest import collect_registered_url, persist_collected_notice
from .intent_adapter import ParsedIntentNotice


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evidence-backed one-URL medical collector with optional Pilot persistence."
    )
    parser.add_argument("url", help="Registered public notice URL")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="optional persistent Pilot SQLite path; when set, verified output is projected into Today repository",
    )
    args = parser.parse_args()

    try:
        collected = collect_registered_url(args.url)
    except (FetchError, ValueError) as exc:
        code = getattr(exc, "code", "INVALID_SOURCE")
        print(json.dumps({"status": "ERROR", "code": code, "message": str(exc)}, ensure_ascii=False))
        return 2

    source = collected.source
    snapshot = collected.snapshot
    parsed = collected.parsed
    event = collected.event
    facts = collected.facts

    parsed_payload = {
        "source_id": parsed.source_id,
        "source_authority": parsed.source_authority,
        "notice_type": parsed.notice_type,
        "project_name": parsed.project_name,
        "buyer_name": parsed.buyer_name,
        "project_number": parsed.project_number,
        "published_at": parsed.published_at,
        "published_at_precision": parsed.published_at_precision,
        "budget_cny": parsed.budget_cny,
        "registration_deadline": parsed.registration_deadline,
        "bid_deadline": parsed.bid_deadline,
        "procurement_method": parsed.procurement_method,
        "product_items": list(parsed.product_items),
        "eligible_for_verified": parsed.eligible_for_verified,
        "verification_reason": parsed.verification_reason,
    }
    if isinstance(parsed, ParsedIntentNotice):
        parsed_payload["expected_procurement_at"] = parsed.expected_procurement_at
        parsed_payload["procurement_need"] = parsed.procurement_need

    if isinstance(parsed, ParsedCcgpLifecycleNotice):
        parsed_payload["page_title"] = parsed.page_title
        parsed_payload["termination_reason"] = parsed.termination_reason
        parsed_payload["amendment_subject"] = parsed.amendment_subject
        parsed_payload["amendment_summary"] = parsed.amendment_summary
        parsed_payload["award_total_cny"] = parsed.award_total_cny
        parsed_payload["award_packages"] = [
            {
                "package_name": item.package_name,
                "supplier_name": item.supplier_name,
                "award_amount_cny": item.award_amount_cny,
            }
            for item in parsed.award_packages
        ]
        if parsed.notice_type == "AWARD":
            parsed_payload["award_items"] = [
                {
                    "package_name": item.package_name,
                    "item_type": item.item_type,
                    "raw_name": item.raw_name,
                    "brand": item.brand,
                    "model": item.model,
                    "quantity": item.quantity,
                    "unit_price_cny": item.unit_price_cny,
                }
                for item in extract_official_award_items(snapshot.text)
            ]

    persistence = None
    if args.db is not None:
        try:
            opportunity = persist_collected_notice(collected, db_path=args.db)
        except (ValueError, RuntimeError) as exc:
            print(
                json.dumps(
                    {
                        "status": "ERROR",
                        "code": "PERSISTENCE_REJECTED",
                        "message": str(exc),
                        "event_id": event.get("event_id"),
                    },
                    ensure_ascii=False,
                )
            )
            return 3
        persistence = {
            "status": "PERSISTED",
            "db_path": str(args.db),
            "opportunity_id": opportunity["opportunity_id"],
            "canonical_project_id": opportunity["canonical_project_id"],
            "lifecycle_state": opportunity["lifecycle_state"],
            "verification_status": opportunity["verification_status"],
            "product_labels": list(opportunity.get("product_labels") or []),
            "customer_type": opportunity.get("customer_type"),
            "is_rental_project": opportunity.get("is_rental_project"),
        }

    result = {
        "status": "OK",
        "source_registry": {
            "source_id": source.source_id,
            "source_name": source.source_name,
            "authority_type": source.authority_type,
            "source_type": source.source_type,
            "provenance_role": source.provenance_role,
            "parser_version": source.parser_version,
        },
        "snapshot": {
            "snapshot_id": snapshot.snapshot_id,
            "source_url": snapshot.source_url,
            "fetched_at": snapshot.fetched_at,
            "status_code": snapshot.status_code,
            "content_type": snapshot.content_type,
            "sha256": snapshot.sha256,
        },
        "parsed": parsed_payload,
        "event": event,
        "facts": facts,
        "persistence": persistence,
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
