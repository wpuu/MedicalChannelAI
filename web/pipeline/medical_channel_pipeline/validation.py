from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlparse
from typing import Any

CRITICAL_FACT_PATHS = {
    "facts.project_number",
    "facts.project_name",
    "facts.buyer_name",
    "facts.hospital_name",
    "facts.department",
    "facts.region",
    "facts.lifecycle_state",
    "facts.notice_type",
    "facts.published_at",
    "facts.registration_deadline",
    "facts.registration_deadline_date",
    "facts.bid_deadline",
    "facts.expected_procurement_at",
    "facts.budget_cny",
    "facts.procurement_method",
    "facts.product_categories",
    "facts.product_items",
    "facts.public_contact",
}

ALLOWED_SOURCE_TYPES = {"CCGP_NOTICE", "OFFICIAL_INSTITUTION_NOTICE"}
MARKET_ADMIN_CODES = {
    "BJ": ("北京", "110000"),
    "TJ": ("天津", "120000"),
    "HE": ("河北", "130000"),
    "LN": ("辽宁", "210000"),
    "JL": ("吉林", "220000"),
    "HL": ("黑龙江", "230000"),
}
LEGACY_DEFAULT_MARKET_CODE = "TJ"


class ValidationError(ValueError):
    pass


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _parse_dateish(value: str, path: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"INVALID_DATE:{path}:{value}") from exc


def _parse_date_only(value: str, path: str) -> None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"INVALID_DATE_ONLY:{path}:{value}") from exc
    if parsed.isoformat() != value:
        raise ValidationError(f"INVALID_DATE_ONLY:{path}:{value}")


def _validate_source(source: dict[str, Any]) -> None:
    source_type = source.get("source_type")
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValidationError(f"UNSUPPORTED_SOURCE_TYPE:{source_type}")
    url = source.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("SOURCE_URL_REQUIRED")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationError(f"INVALID_SOURCE_URL:{url}")
    if source_type == "CCGP_NOTICE" and not (
        parsed.hostname == "ccgp.gov.cn" or parsed.hostname.endswith(".ccgp.gov.cn")
    ):
        raise ValidationError(f"CCGP_HOST_MISMATCH:{parsed.hostname}")
    observed_at = source.get("observed_at")
    if not isinstance(observed_at, str):
        raise ValidationError("SOURCE_OBSERVED_AT_REQUIRED")
    _parse_dateish(observed_at, "source.observed_at")


def _evidence_source_allowed(record_source: dict[str, Any], evidence_url: str) -> bool:
    source_url = record_source["url"]
    if evidence_url == source_url:
        return True
    if record_source.get("source_type") != "OFFICIAL_INSTITUTION_NOTICE":
        return False
    source_host = urlparse(source_url).hostname
    parsed = urlparse(evidence_url)
    return parsed.scheme == "https" and bool(parsed.hostname) and parsed.hostname == source_host


def _evidence_index(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = record.get("evidence")
    if not isinstance(items, list):
        raise ValidationError("EVIDENCE_LIST_REQUIRED")
    out: dict[str, dict[str, Any]] = {}
    source = record["source"]
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("EVIDENCE_ITEM_INVALID")
        path = item.get("field_path")
        locator = item.get("locator")
        evidence_url = item.get("source_url")
        if not isinstance(path, str) or not path.startswith("facts."):
            raise ValidationError(f"EVIDENCE_FIELD_PATH_INVALID:{path}")
        if not isinstance(locator, str) or not locator.strip():
            raise ValidationError(f"EVIDENCE_LOCATOR_REQUIRED:{path}")
        if not isinstance(evidence_url, str) or not _evidence_source_allowed(source, evidence_url):
            raise ValidationError(f"EVIDENCE_SOURCE_MISMATCH:{path}")
        if path in out:
            raise ValidationError(f"DUPLICATE_EVIDENCE_PATH:{path}")
        out[path] = item
    return out


def _validate_market_fields(facts: dict[str, Any]) -> str:
    code = str(facts.get("market_code") or LEGACY_DEFAULT_MARKET_CODE).strip().upper()
    if code not in MARKET_ADMIN_CODES:
        raise ValidationError(f"MARKET_CODE_INVALID:{code}")
    expected_name, expected_admin_code = MARKET_ADMIN_CODES[code]
    market_name = facts.get("market_name")
    market_admin_code = facts.get("market_admin_code")
    if market_name is not None and str(market_name).strip() != expected_name:
        raise ValidationError(f"MARKET_NAME_MISMATCH:{code}:{market_name}")
    if market_admin_code is not None and str(market_admin_code).strip() != expected_admin_code:
        raise ValidationError(f"MARKET_ADMIN_CODE_MISMATCH:{code}:{market_admin_code}")
    return code


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("schema_version") != "0.1":
        raise ValidationError("SCHEMA_VERSION_UNSUPPORTED")
    opportunity_id = record.get("opportunity_id")
    if not isinstance(opportunity_id, str) or not opportunity_id.strip():
        raise ValidationError("OPPORTUNITY_ID_REQUIRED")
    source = record.get("source")
    if not isinstance(source, dict):
        raise ValidationError("SOURCE_REQUIRED")
    _validate_source(source)
    facts = record.get("facts")
    if not isinstance(facts, dict):
        raise ValidationError("FACTS_REQUIRED")
    _validate_market_fields(facts)

    for key in ("project_name", "buyer_name", "notice_type", "published_at"):
        if not _nonempty(facts.get(key)):
            raise ValidationError(f"REQUIRED_FACT_MISSING:facts.{key}")

    for key in ("published_at", "registration_deadline", "bid_deadline", "expected_procurement_at"):
        value = facts.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise ValidationError(f"INVALID_DATE_TYPE:facts.{key}")
            _parse_dateish(value, f"facts.{key}")

    registration_deadline_date = facts.get("registration_deadline_date")
    if registration_deadline_date is not None:
        if not isinstance(registration_deadline_date, str):
            raise ValidationError("INVALID_DATE_TYPE:facts.registration_deadline_date")
        _parse_date_only(registration_deadline_date, "facts.registration_deadline_date")
    if facts.get("registration_deadline") is not None and registration_deadline_date is not None:
        raise ValidationError("REGISTRATION_DEADLINE_PRECISION_CONFLICT")

    budget = facts.get("budget_cny")
    if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int) or budget < 0):
        raise ValidationError("INVALID_BUDGET_CNY")

    evidence = _evidence_index(record)
    for path in CRITICAL_FACT_PATHS:
        key = path.split(".", 1)[1]
        if _nonempty(facts.get(key)) and path not in evidence:
            raise ValidationError(f"UNSUPPORTED_CRITICAL_FACT:{path}")

    return record


def validate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise ValidationError("RECORD_LIST_REQUIRED")
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, ...]] = set()
    result = []
    for record in records:
        validate_record(record)
        opportunity_id = record["opportunity_id"]
        if opportunity_id in seen_ids:
            raise ValidationError(f"DUPLICATE_OPPORTUNITY_ID:{opportunity_id}")
        seen_ids.add(opportunity_id)
        facts = record["facts"]
        market_code = str(facts.get("market_code") or LEGACY_DEFAULT_MARKET_CODE).strip().upper()
        project_number = facts.get("project_number")
        if _nonempty(project_number):
            dedupe_key = ("project_number", market_code, str(project_number).strip().lower())
        else:
            dedupe_key = (
                "fallback",
                market_code,
                str(facts.get("buyer_name") or "").strip().lower(),
                str(facts.get("project_name") or "").strip().lower(),
                str(facts.get("published_at") or "").strip(),
            )
        if dedupe_key in seen_keys:
            raise ValidationError(f"DUPLICATE_CANONICAL_OPPORTUNITY:{dedupe_key}")
        seen_keys.add(dedupe_key)
        result.append(record)
    return result
