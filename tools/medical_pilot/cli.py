from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

from .award_items import build_award_items_fact, extract_official_award_items
from .ccgp_lifecycle_adapter import (
    ParsedCcgpLifecycleNotice,
    build_ccgp_lifecycle_event_and_facts,
)
from .collector_core import FetchError, HostBoundFetcher, build_event_and_facts
from .intent_adapter import ParsedIntentNotice, build_intent_event_and_facts
from .registry import adapter_for_source, resolve_source


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Research-only one-URL collector for evidence-backed medical opportunity facts."
    )
    parser.add_argument("url", help="Registered public notice URL")
    args = parser.parse_args()

    try:
        source = resolve_source(args.url)
        adapter = adapter_for_source(source)
        host = urlparse(source.canonical_base_url).hostname
        if not host:
            raise ValueError("registered source has no valid canonical host")
        fetcher = HostBoundFetcher({host})
        snapshot = fetcher.fetch(args.url)
        parsed = adapter.parse_notice(snapshot)
        if isinstance(parsed, ParsedIntentNotice):
            event, facts = build_intent_event_and_facts(parsed, snapshot)
        elif isinstance(parsed, ParsedCcgpLifecycleNotice):
            event, facts = build_ccgp_lifecycle_event_and_facts(parsed, snapshot)
        else:
            event, facts = build_event_and_facts(parsed, snapshot)
    except (FetchError, ValueError) as exc:
        code = getattr(exc, "code", "INVALID_SOURCE")
        print(json.dumps({"status": "ERROR", "code": code, "message": str(exc)}, ensure_ascii=False))
        return 2

    parsed_payload = {
        "source_id": parsed.source_id,
        "source_authority": parsed.source_authority,
        "notice_type": parsed.notice_type,
        "project_name": parsed.project_name,
        "buyer_name": parsed.buyer_name,
        "project_number": parsed.project_number,
        "published_at": parsed.published_at,
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
            award_items = extract_official_award_items(snapshot.text)
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
                for item in award_items
            ]
            award_items_fact = build_award_items_fact(
                event=event,
                snapshot=snapshot,
                source_id=parsed.source_id,
                source_url=parsed.source_url,
                published_at=parsed.published_at,
                items=award_items,
            )
            if award_items_fact is not None:
                facts.append(award_items_fact)

    result = {
        "status": "OK",
        "source_registry": {
            "source_id": source.source_id,
            "source_name": source.source_name,
            "authority_type": source.authority_type,
            "source_type": source.source_type,
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
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
