from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DB = WEB_ROOT / 'api' / '_publicIntelligenceDb.js'
TODAY_PREF = WEB_ROOT / 'api' / '_todayDisplayPreference.js'
PRIVATE_API = WEB_ROOT / 'api' / 'private.js'
AUTH_API = WEB_ROOT / 'api' / 'auth.js'
AI_CORE = WEB_ROOT / 'api' / 'ai' / '_analyzeCore.js'
PRIVATE_CONTEXT = WEB_ROOT / 'api' / '_privateProfileContext.js'
API_SERVICE = WEB_ROOT / 'src' / 'services' / 'ApiTodayActionsService.ts'
METRICS = WEB_ROOT / 'src' / 'components' / 'today' / 'MetricCards.tsx'


class SharedPublicIntelligenceArchitectureTests(unittest.TestCase):
    def test_public_history_schema_is_region_and_version_scoped(self) -> None:
        source = PUBLIC_DB.read_text(encoding='utf-8')
        for table in (
            'public_collector_runs',
            'public_opportunities',
            'public_opportunity_versions',
            'public_ai_briefs',
        ):
            self.assertIn(table, source)
        self.assertIn('region_code TEXT NOT NULL', source)
        self.assertIn('current_fact_hash', source)
        self.assertIn('current_version', source)
        self.assertIn('UNIQUE (opportunity_id, fact_hash)', source)
        self.assertIn(
            'PRIMARY KEY (opportunity_id, fact_hash, window_state, brief_type, prompt_version)',
            source,
        )

    def test_today_limit_is_separate_display_preference(self) -> None:
        source = TODAY_PREF.read_text(encoding='utf-8')
        self.assertIn('private_user_ui_preferences', source)
        self.assertIn('Object.freeze([3, 5, 8, 10, 15])', source)
        private_context = PRIVATE_CONTEXT.read_text(encoding='utf-8')
        self.assertNotIn('private_user_ui_preferences', private_context)
        self.assertNotIn('today_limit', private_context)

        private_api = PRIVATE_API.read_text(encoding='utf-8')
        self.assertIn("['GET', 'PUT']", private_api)
        self.assertIn('todayPrivateState', private_api)
        self.assertIn('setTodayLimitForUser', private_api)
        self.assertIn('today_limit_options', private_api)

        auth_api = AUTH_API.read_text(encoding='utf-8')
        self.assertIn('ui_preferences', auth_api)
        self.assertIn('private_user_ui_preferences', auth_api)

    def test_today_response_batches_followup_and_feedback_summary(self) -> None:
        private_api = PRIVATE_API.read_text(encoding='utf-8')
        self.assertIn('decorateCardWithFollowup', private_api)
        self.assertIn('recommendation_feedback_summary', private_api)
        self.assertIn('followup_status', private_api)
        self.assertIn('async function todayPrivateState', private_api)

        api_service = API_SERVICE.read_text(encoding='utf-8')
        self.assertNotIn("'/followed?view=status-index'", api_service)
        self.assertIn('recommendation_feedback_summary', api_service)

        metrics = METRICS.read_text(encoding='utf-8')
        self.assertNotIn('loadRecommendationFeedback', metrics)
        self.assertNotIn('subscribeRemoteRecommendationFeedback', metrics)
        self.assertIn('updateTodayLimit', metrics)
        self.assertIn('今日重点显示数量', metrics)

    def test_existing_ai_cache_is_not_mistaken_for_durable_shared_public_cache(self) -> None:
        source = AI_CORE.read_text(encoding='utf-8')
        self.assertIn('new Map()', source)
        self.assertIn('RESULT_CACHE_TTL_MS', source)
        # Durable regional public AI is a separate persistence layer. The current
        # process-local decision cache remains private/personalized behavior.
        self.assertNotIn('public_ai_briefs', source)


class ProductNeutralLanguageTests(unittest.TestCase):
    def test_runtime_product_does_not_embed_first_customer_nickname(self) -> None:
        nickname = '\u8001\u6768'
        roots = [WEB_ROOT / 'src', WEB_ROOT / 'api', WEB_ROOT / 'pipeline']
        violations: list[str] = []
        for root in roots:
            for path in root.rglob('*'):
                if not path.is_file() or path.suffix.lower() not in {
                    '.js', '.mjs', '.ts', '.tsx', '.py', '.json'
                }:
                    continue
                try:
                    text = path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    continue
                if nickname in text:
                    violations.append(str(path.relative_to(WEB_ROOT)))
        self.assertEqual(violations, [])


if __name__ == '__main__':
    unittest.main()
