from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / 'pipeline'


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise SystemExit(f'PATCH_CONTRACT_MISMATCH:{path}:{text.count(old)}')
    path.write_text(text.replace(old, new), encoding='utf-8')


regional = PIPELINE / 'medical_channel_pipeline' / 'regional_candidate.py'
regional_text = regional.read_text(encoding='utf-8')
anchor = """def regional_candidate_priority(candidate: DiscoveryCandidate) -> int:\n    \"\"\"Rank detail-verification budget without claiming publication relevance.\n\n    A positive sparse-title scope match is useful as a ranking hint, but a\n    negative sparse-title result is never used to reject the candidate. Titles\n    carrying explicit medical context plus device/IT/lab markers receive the\n    next priority tier. Everything else remains eligible at the lowest tier.\n    \"\"\"\n    if is_medical_channel_relevant_record(_candidate_scope_record(candidate)):\n        return 3\n    title = str(candidate.title or '')\n    if has_medical_channel_context_text(title) and any(\n        marker in title for marker in _BROAD_MEDICAL_PROCUREMENT_MARKERS\n    ):\n        return 2\n    return 1\n"""
replacement = anchor + """\n\ndef regional_candidate_selection_key(\n    candidate: DiscoveryCandidate,\n    existing_source_urls: set[str] | frozenset[str],\n) -> tuple[int, int, str, str]:\n    \"\"\"Spend bounded detail budget on unseen official URLs before rechecks.\n\n    Existing verified URLs remain eligible for periodic re-verification, but\n    they must not crowd newly discovered candidates out of the same refresh\n    window. Relevance priority and recency are secondary ordering signals.\n    \"\"\"\n    url = str(candidate.detail_url or '')\n    return (\n        1 if url and url not in existing_source_urls else 0,\n        regional_candidate_priority(candidate),\n        str(candidate.published_at or ''),\n        url,\n    )\n"""
if anchor not in regional_text:
    raise SystemExit('REGIONAL_PRIORITY_ANCHOR_NOT_FOUND')
regional.write_text(regional_text.replace(anchor, replacement, 1), encoding='utf-8')

sync = PIPELINE / 'scripts' / 'sync_regional_ccgp.py'
replace_once(
    sync,
    """from medical_channel_pipeline.regional_candidate import (  # noqa: E402\n    regional_candidate_priority,\n    regional_candidate_skip_reason,\n)\n""",
    """from medical_channel_pipeline.regional_candidate import (  # noqa: E402\n    regional_candidate_priority,\n    regional_candidate_selection_key,\n    regional_candidate_skip_reason,\n)\n""",
)
replace_once(
    sync,
    """    existing_records = load_json_arrays(args.existing_records_input, label='existing regional records')\n    session = CcgpSearchSession()\n""",
    """    existing_records = load_json_arrays(args.existing_records_input, label='existing regional records')\n    existing_source_urls = {\n        str((record.get('source') or {}).get('url') or '')\n        for record in existing_records\n        if isinstance(record, dict) and str((record.get('source') or {}).get('url') or '')\n    }\n    session = CcgpSearchSession()\n""",
)
replace_once(
    sync,
    """        discovered = sorted(\n            discovered_by_url.values(),\n            key=lambda item: (\n                regional_candidate_priority(item[1]),\n                getattr(item[1], 'published_at', None) or '',\n                getattr(item[1], 'detail_url', ''),\n            ),\n            reverse=True,\n        )\n        selected = discovered[: plan['max_candidates_per_market']]\n        market_new_count = 0\n""",
    """        discovered = sorted(\n            discovered_by_url.values(),\n            key=lambda item: regional_candidate_selection_key(item[1], existing_source_urls),\n            reverse=True,\n        )\n        selected = discovered[: plan['max_candidates_per_market']]\n        selected_candidates = [\n            {\n                'title': getattr(candidate, 'title', None),\n                'url': getattr(candidate, 'detail_url', None),\n                'published_at': getattr(candidate, 'published_at', None),\n                'priority': regional_candidate_priority(candidate),\n                'was_existing_verified_url': str(getattr(candidate, 'detail_url', '') or '') in existing_source_urls,\n            }\n            for _, candidate in selected\n        ]\n        market_new_count = 0\n""",
)
replace_once(
    sync,
    """            'unique_candidate_count': len(discovered),\n            'selected_candidate_count': len(selected),\n            'new_verified_record_count': market_new_count,\n""",
    """            'unique_candidate_count': len(discovered),\n            'selected_candidate_count': len(selected),\n            'selected_unseen_candidate_count': sum(\n                1 for item in selected_candidates if not item['was_existing_verified_url']\n            ),\n            'selected_existing_candidate_count': sum(\n                1 for item in selected_candidates if item['was_existing_verified_url']\n            ),\n            'selected_candidates': selected_candidates,\n            'new_verified_record_count': market_new_count,\n""",
)
replace_once(
    sync,
    """            'candidate_detail_budget_uses_recall_preserving_priority': True,\n            'cross_market_project_number_dedupe_is_forbidden': True,\n""",
    """            'candidate_detail_budget_uses_recall_preserving_priority': True,\n            'candidate_detail_budget_prioritizes_unseen_urls_before_rechecks': True,\n            'cross_market_project_number_dedupe_is_forbidden': True,\n""",
)

test = PIPELINE / 'tests' / 'test_regional_candidate_classification.py'
replace_once(
    test,
    """    regional_candidate_priority,\n    regional_candidate_skip_reason,\n)\n""",
    """    regional_candidate_priority,\n    regional_candidate_selection_key,\n    regional_candidate_skip_reason,\n)\n""",
)
insert_before = """    def test_regional_sync_classifies_and_prioritizes_before_detail_budget(self):\n"""
new_tests = """    def test_unseen_official_url_wins_budget_before_existing_recheck(self):\n        seen = candidate(\n            '某医院医疗设备采购项目公开招标公告',\n            buyer='某医院',\n            notice_type='公开招标公告',\n        )\n        unseen = candidate(\n            '中国医学科学院北京协和医院放射科乳腺机采购项目公开招标公告',\n            buyer='中国医学科学院北京协和医院',\n            notice_type='公开招标公告',\n        )\n        seen = DiscoveryCandidate(**{**seen.__dict__, 'detail_url': 'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/seen.htm'})\n        unseen = DiscoveryCandidate(**{**unseen.__dict__, 'detail_url': 'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/unseen.htm'})\n        existing = {seen.detail_url}\n        self.assertGreater(\n            regional_candidate_selection_key(unseen, existing),\n            regional_candidate_selection_key(seen, existing),\n        )\n\n    def test_unseen_selection_still_prefers_medical_relevance_then_recency(self):\n        medical = candidate(\n            '中日友好医院免散瞳眼底照相机系统采购项目公开招标公告',\n            buyer='中日友好医院',\n            notice_type='公开招标公告',\n        )\n        generic = candidate(\n            '某研究院一般设备采购项目公开招标公告',\n            buyer='某研究院',\n            notice_type='公开招标公告',\n        )\n        self.assertGreater(\n            regional_candidate_selection_key(medical, set()),\n            regional_candidate_selection_key(generic, set()),\n        )\n\n"""
test_text = test.read_text(encoding='utf-8')
if test_text.count(insert_before) != 1:
    raise SystemExit('TEST_INSERT_ANCHOR_MISMATCH')
test_text = test_text.replace(insert_before, new_tests + insert_before, 1)
test_text = test_text.replace(
    """        priority_at = source.index('regional_candidate_priority(item[1])')\n""",
    """        priority_at = source.index('regional_candidate_selection_key(item[1], existing_source_urls)')\n""",
    1,
)
test_text = test_text.replace(
    """        self.assertIn(\"'candidate_detail_budget_uses_recall_preserving_priority': True\", source)\n""",
    """        self.assertIn(\"'candidate_detail_budget_uses_recall_preserving_priority': True\", source)\n        self.assertIn(\"'candidate_detail_budget_prioritizes_unseen_urls_before_rechecks': True\", source)\n        self.assertIn(\"'selected_candidates': selected_candidates\", source)\n""",
    1,
)
test.write_text(test_text, encoding='utf-8')

print('unseen-first regional candidate budget patch applied')
