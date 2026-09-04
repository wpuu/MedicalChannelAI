from __future__ import annotations

import json
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class PublicOpportunityHistoryTests(unittest.TestCase):
    def test_history_reuses_existing_profile_serverless_function(self) -> None:
        config = json.loads((WEB_ROOT / 'vercel.json').read_text(encoding='utf-8'))
        rewrites = {item['source']: item['destination'] for item in config['rewrites']}
        self.assertEqual(
            rewrites['/api/public-history/:id'],
            '/api/profile?route=public-history&id=:id',
        )
        self.assertNotIn('api/public-history.js', config.get('functions', {}))

    def test_history_route_requires_authenticated_account(self) -> None:
        source = (WEB_ROOT / 'api' / 'profile.js').read_text(encoding='utf-8')
        start = source.index('async function publicHistoryRoute')
        end = source.index('export default async function handler', start)
        route = source[start:end]
        self.assertIn("request.method !== 'GET'", route)
        self.assertIn('const user = await requireUser(request, response)', route)
        self.assertIn('if (!user) return', route)
        self.assertIn('historyOpportunityId(request)', route)
        self.assertIn('await publicOpportunityHistory(id)', route)

    def test_version_history_reads_public_table_only_and_never_private_profile(self) -> None:
        source = (WEB_ROOT / 'api' / '_publicIntelligenceHistory.js').read_text(encoding='utf-8')
        self.assertIn('FROM public_opportunity_versions', source)
        self.assertIn('ALLOWED_CHANGE_FIELDS', source)
        self.assertIn("change_type: isInitial ? 'INITIAL' : 'UPDATED'", source)
        for forbidden in [
            'private_product_capabilities',
            'private_hospital_relationships',
            'private_target_hospitals',
            'customer_context',
            'organization_id',
            'user_id',
        ]:
            self.assertNotIn(forbidden, source)

    def test_history_api_returns_before_and_after_only_for_safe_public_fields(self) -> None:
        source = (WEB_ROOT / 'api' / '_publicIntelligenceHistory.js').read_text(encoding='utf-8')
        self.assertIn('before: previous ? pathValue(previous.payload, field) : null', source)
        self.assertIn('after: pathValue(row.payload, field)', source)
        self.assertIn("'facts.registration_deadline'", source)
        self.assertIn("'facts.bid_deadline'", source)
        self.assertIn("'facts.budget'", source)
        self.assertIn("'facts.product_items'", source)
        self.assertIn("'facts.public_contact'", source)
        self.assertIn("'evidence_source_urls'", source)

    def test_detail_history_is_on_demand_and_separate_from_private_followup(self) -> None:
        page = (WEB_ROOT / 'src' / 'pages' / 'OpportunityDetailPage.tsx').read_text(encoding='utf-8')
        card = (WEB_ROOT / 'src' / 'components' / 'opportunity' / 'PublicHistoryCard.tsx').read_text(encoding='utf-8')
        service = (WEB_ROOT / 'src' / 'services' / 'publicOpportunityHistoryApi.ts').read_text(encoding='utf-8')
        load_start = page.index('const load = useCallback')
        load_end = page.index('useEffect(() =>', load_start)
        initial_load = page[load_start:load_end]
        self.assertNotIn('loadPublicHistory(id)', initial_load)
        self.assertIn('<PublicHistoryCard', page)
        self.assertIn('onLoad={() => loadPublicHistory(card.opportunity_id)}', page)
        self.assertIn('void getPublicOpportunityHistory(opportunityId)', page)
        self.assertIn('setPublicHistoryError(true)', page)
        self.assertIn('查看更新记录', card)
        self.assertIn('重试读取', card)
        self.assertIn('当前商机事实和官方依据不受影响', card)
        self.assertIn('不包含你的医院关系或产品资源', card)
        self.assertIn('/public-history/${encodeURIComponent(opportunityId)}', service)


if __name__ == '__main__':
    unittest.main()
