from __future__ import annotations

from .ccgp_discovery import DiscoveryCandidate
from .channel_scope import is_medical_channel_relevant_record

OUT_OF_MEDICAL_SCOPE = 'OUT_OF_MEDICAL_SCOPE'
NON_COMPETITIVE_SINGLE_SOURCE = 'NON_COMPETITIVE_SINGLE_SOURCE'
_SINGLE_SOURCE_MARKERS = (
    '单一来源',
    '采购实行单一来源采购方式',
)


def regional_candidate_skip_reason(candidate: DiscoveryCandidate) -> str | None:
    """Classify discovery rows that must not enter competitive detail parsing.

    Search query parameters are discovery-only. A row must independently remain
    in medical-channel scope and represent a competitive procurement window.
    Single-source notices may be useful later as market intelligence, but they
    do not have a competitive bid deadline and therefore must not be forced
    through the open-tender/consultation detail adapters.
    """
    record = {
        'facts': {
            'project_name': candidate.title,
            'buyer_name': candidate.buyer_name,
        },
    }
    if not is_medical_channel_relevant_record(record):
        return OUT_OF_MEDICAL_SCOPE

    notice_evidence = '\n'.join(
        value.strip()
        for value in (candidate.title, candidate.notice_type)
        if isinstance(value, str) and value.strip()
    )
    if any(marker in notice_evidence for marker in _SINGLE_SOURCE_MARKERS):
        return NON_COMPETITIVE_SINGLE_SOURCE
    return None
