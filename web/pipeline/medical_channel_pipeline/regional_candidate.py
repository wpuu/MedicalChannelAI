from __future__ import annotations

from .ccgp_discovery import DiscoveryCandidate
from .channel_scope import (
    has_explicit_medical_channel_exclusion_text,
    has_medical_channel_context_text,
    is_medical_channel_relevant_record,
)

OUT_OF_MEDICAL_SCOPE = 'OUT_OF_MEDICAL_SCOPE'
NON_COMPETITIVE_SINGLE_SOURCE = 'NON_COMPETITIVE_SINGLE_SOURCE'
_SINGLE_SOURCE_MARKERS = (
    '单一来源',
    '采购实行单一来源采购方式',
)
_BROAD_MEDICAL_PROCUREMENT_MARKERS = (
    '设备', '专用设备', '系统', '软件', '平台', '仪', '机',
    '试剂', '耗材', '诊疗', '检验', '检测', '实验室', '影像',
    '放射', '采血', '血液', '病理', '超声', '内镜', '监护',
    '治疗', '手术', '康复', '药品', '疫苗',
)


def _candidate_scope_record(candidate: DiscoveryCandidate) -> dict:
    return {
        'facts': {
            'project_name': candidate.title,
            'buyer_name': candidate.buyer_name,
        },
    }


def regional_candidate_skip_reason(candidate: DiscoveryCandidate) -> str | None:
    """Reject only rows that sparse official search evidence can prove unusable.

    Search titles are discovery evidence, not the final medical-scope fact layer.
    Ambiguous rows continue to the official detail page, where the verified
    record is subjected to the strict publication scope classifier.
    """
    notice_evidence = '\n'.join(
        value.strip()
        for value in (candidate.title, candidate.notice_type)
        if isinstance(value, str) and value.strip()
    )
    if any(marker in notice_evidence for marker in _SINGLE_SOURCE_MARKERS):
        return NON_COMPETITIVE_SINGLE_SOURCE
    if has_explicit_medical_channel_exclusion_text(candidate.title):
        return OUT_OF_MEDICAL_SCOPE
    return None


def regional_candidate_priority(candidate: DiscoveryCandidate) -> int:
    """Rank detail-verification budget without claiming publication relevance.

    A positive sparse-title scope match is useful as a ranking hint, but a
    negative sparse-title result is never used to reject the candidate. Titles
    carrying explicit medical context plus device/IT/lab markers receive the
    next priority tier. Everything else remains eligible at the lowest tier.
    """
    if is_medical_channel_relevant_record(_candidate_scope_record(candidate)):
        return 3
    title = str(candidate.title or '')
    if has_medical_channel_context_text(title) and any(
        marker in title for marker in _BROAD_MEDICAL_PROCUREMENT_MARKERS
    ):
        return 2
    return 1
