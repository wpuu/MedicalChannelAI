from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'web/pipeline/scripts/sync_regional_ccgp.py'


def patch(old: str, new: str, *, expected: int = 1) -> None:
    text = TARGET.read_text(encoding='utf-8')
    count = text.count(old)
    if count != expected:
        raise SystemExit(f'PATCH_COUNT expected={expected} got={count}\n--- target ---\n{old}')
    TARGET.write_text(text.replace(old, new), encoding='utf-8')


patch(
    "from medical_channel_pipeline.state import merge_canonical_records  # noqa: E402\n",
    "from medical_channel_pipeline.regional_candidate import regional_candidate_skip_reason  # noqa: E402\nfrom medical_channel_pipeline.state import merge_canonical_records  # noqa: E402\n",
)

patch(
    "    market_failures: dict[str, list[dict]] = {code: [] for code in market_by_code}\n    scoped_success: dict[str, int] = {code: 0 for code in market_by_code}\n",
    """    market_failures: dict[str, list[dict]] = {code: [] for code in market_by_code}\n    market_skips: dict[str, dict[str, dict]] = {code: {} for code in market_by_code}\n    scoped_success: dict[str, int] = {code: 0 for code in market_by_code}\n\n    def record_candidate_skip(code: str, notice_type: str, candidate: object, reason: str) -> None:\n        detail_url = str(getattr(candidate, 'detail_url', '') or '')\n        if not detail_url:\n            return\n        market_skips[code].setdefault(detail_url, {\n            'stage': 'candidate_classification',\n            'market_code': code,\n            'reason': reason,\n            'notice_type': notice_type,\n            'candidate_notice_type': getattr(candidate, 'notice_type', None),\n            'candidate_region': getattr(candidate, 'region', None),\n            'title': getattr(candidate, 'title', None),\n            'url': detail_url,\n        })\n""",
)

patch(
    """                        if actual_code != code:\n                            scoped_region_mismatches[code] += 1\n                            continue\n                        market_candidates[code].setdefault(\n""",
    """                        if actual_code != code:\n                            scoped_region_mismatches[code] += 1\n                            continue\n                        skip_reason = regional_candidate_skip_reason(candidate)\n                        if skip_reason:\n                            record_candidate_skip(code, item_notice_type, candidate, skip_reason)\n                            continue\n                        market_candidates[code].setdefault(\n""",
)

patch(
    """                        if actual_code not in empty_codes:\n                            continue\n                        market_candidates[actual_code].setdefault(\n""",
    """                        if actual_code not in empty_codes:\n                            continue\n                        skip_reason = regional_candidate_skip_reason(candidate)\n                        if skip_reason:\n                            record_candidate_skip(actual_code, item_notice_type, candidate, skip_reason)\n                            continue\n                        market_candidates[actual_code].setdefault(\n""",
)

patch(
    """            'national_fallback_used': code in empty_codes,\n            'unique_candidate_count': len(discovered),\n""",
    """            'national_fallback_used': code in empty_codes,\n            'skipped_candidate_count': len(market_skips[code]),\n            'skipped_candidates': sorted(market_skips[code].values(), key=lambda item: (item['reason'], item['url'])),\n            'unique_candidate_count': len(discovered),\n""",
)

print('regional candidate classification patch applied')
