from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class DurablePublicIntelligenceTests(unittest.TestCase):
    def test_public_opportunities_are_versioned_by_public_fact_hash(self) -> None:
        source = (WEB_ROOT / 'api' / '_publicIntelligenceDb.js').read_text(encoding='utf-8')
        self.assertIn('CREATE TABLE IF NOT EXISTS public_opportunities', source)
        self.assertIn('CREATE TABLE IF NOT EXISTS public_opportunity_versions', source)
        self.assertIn('CREATE TABLE IF NOT EXISTS public_snapshot_materializations', source)
        self.assertIn('current_fact_hash TEXT NOT NULL CHECK (length(current_fact_hash) = 64)', source)
        self.assertIn('fact_hash TEXT NOT NULL CHECK (length(fact_hash) = 64)', source)
        self.assertIn('changed_fields JSONB', source)
        self.assertIn("${tx.json(['INITIAL'])}", source)
        self.assertIn('const fields = changedFields(existing.current_payload, observation.payload)', source)
        self.assertIn('observedAt.getTime() < previousSeen', source)
        self.assertIn('return { created: false, changed: false, stale: true', source)

    def test_same_snapshot_and_concurrent_materialization_are_idempotent(self) -> None:
        source = (WEB_ROOT / 'api' / '_publicIntelligenceDb.js').read_text(encoding='utf-8')
        pilot = (WEB_ROOT / 'api' / '_pilotOpportunity.js').read_text(encoding='utf-8')
        self.assertIn('export async function materializeVerifiedSnapshot(snapshot)', source)
        self.assertIn('public_snapshot_materializations', source)
        self.assertIn('SELECT pg_advisory_xact_lock', source)
        self.assertIn('if (existing.length) return { skipped: true', source)
        self.assertIn('existing.current_fact_hash === observation.fact_hash', source)
        self.assertIn('last_seen_at = GREATEST(last_seen_at', source)
        self.assertIn("import { materializeVerifiedSnapshot } from './_publicIntelligenceDb.js'", pilot)
        self.assertIn('await materializePublicSnapshotBestEffort(snapshot)', pilot)
        self.assertLess(
            pilot.index('await materializePublicSnapshotBestEffort(snapshot)'),
            pilot.index('const profile = await loadPrivateProfileForUser(user)'),
        )
        self.assertIn("console.warn('public intelligence materialization deferred'", pilot)

    def test_public_snapshot_payload_excludes_customer_context(self) -> None:
        source = (WEB_ROOT / 'api' / '_publicIntelligenceDb.js').read_text(encoding='utf-8')
        start = source.index('function publicPayloadFromCard')
        end = source.index('function publicObservation', start)
        payload = source[start:end]
        self.assertIn('opportunity_id:', payload)
        self.assertIn('facts,', payload)
        self.assertIn('evidence_source_urls:', payload)
        self.assertNotIn('customer_context', payload)
        self.assertNotIn('priority', payload)

    def test_page_brief_cache_key_binds_region_facts_day_and_prompt_version(self) -> None:
        db = (WEB_ROOT / 'api' / '_publicIntelligenceDb.js').read_text(encoding='utf-8')
        core = (WEB_ROOT / 'api' / 'ai' / '_analyzeCore.js').read_text(encoding='utf-8')
        brief = (WEB_ROOT / 'api' / 'ai' / '_pageBrief.js').read_text(encoding='utf-8')
        self.assertIn('PRIMARY KEY (opportunity_id, fact_hash, window_state, brief_type, prompt_version)', db)
        self.assertIn('export function publicAiFactHash', db)
        self.assertIn('export async function getOrCreateSharedPublicAiBrief', db)
        self.assertIn("PAGE_BRIEF_PROMPT_VERSION = 'page-brief-v1'", brief)
        self.assertIn("PAGE_BRIEF_TYPE = 'PAGE_BRIEF'", brief)
        self.assertIn("opportunityId: `page-brief:${markets.join('+')}`", core)
        self.assertIn('fact_hash: publicAiFactHash(item.facts, item.evidenceUrls)', core)
        self.assertIn('windowState: `day:${shanghaiDateString(nowMs)}`', core)
        self.assertIn('briefType: PAGE_BRIEF_TYPE', core)
        self.assertIn('promptVersion: PAGE_BRIEF_PROMPT_VERSION', core)

    def test_per_card_next_step_is_deterministic_rules_without_model(self) -> None:
        core = (WEB_ROOT / 'api' / 'ai' / '_analyzeCore.js').read_text(encoding='utf-8')
        contract = (WEB_ROOT / 'api' / 'ai' / '_decisionContract.js').read_text(encoding='utf-8')
        start = core.index('function ruleDecisionItem(')
        block = core[start:core.index('\n}\n', start)]
        self.assertIn('buildRuleDecision(grounded.facts, grounded.evidenceUrls, customerContext, windowStatus)', block)
        self.assertNotIn('callProvider', block)
        self.assertNotIn('RateLimit', block)
        self.assertIn("decision_source: 'PUBLIC_FACT_RULES'", block)
        self.assertIn("PUBLIC_RULE_VERSION = 'public-fact-rules-v1'", contract)
        self.assertIn('export function selectRuleActionCodes(', contract)
        self.assertNotIn('parseDecisionContent', core)
        self.assertNotIn('buildDecisionMessages', core)

    def test_page_brief_model_call_is_memoized_rate_limited_and_falls_back_to_rules(self) -> None:
        core = (WEB_ROOT / 'api' / 'ai' / '_analyzeCore.js').read_text(encoding='utf-8')
        start = core.index('export async function analyzePageBrief(')
        block = core[start:core.index('\n}\n', start)]
        self.assertIn('const pending = inFlight.get(inFlightKey)', block)
        self.assertIn('if (!request?.__mcaiInternalPrewarm && await warmRateLimitExceeded(request)) throw rateLimitError()', block)
        self.assertIn('if (cacheOnly) return pageBriefResponse(buildRuleBrief(items)', block)
        self.assertIn("aiError: 'AI_NOT_CONFIGURED'", block)
        self.assertIn('aiError: aiErrorCode(error)', block)
        self.assertIn('max_tokens: maxTokens', core)
        self.assertIn('const PAGE_BRIEF_MAX_TOKENS = 700', core)

    def test_durable_cache_never_holds_transaction_during_generation(self) -> None:
        db = (WEB_ROOT / 'api' / '_publicIntelligenceDb.js').read_text(encoding='utf-8')
        today = (WEB_ROOT / 'src' / 'pages' / 'TodayPage.tsx').read_text(encoding='utf-8')
        detail = (WEB_ROOT / 'src' / 'pages' / 'OpportunityDetailPage.tsx').read_text(encoding='utf-8')
        brief_start = db.index('export async function getOrCreateSharedPublicAiBrief')
        self.assertLess(db.index('if (cached) return cached', brief_start), db.index('createdResult = await createResult()', brief_start))
        brief_block = db[brief_start:db.index('\n}\n', brief_start)]
        self.assertNotIn('sql.begin', brief_block)
        self.assertNotIn('pg_advisory', brief_block)
        self.assertIn('DO NOTHING', brief_block)
        self.assertNotIn('ai: { configured: true }', today)
        self.assertNotIn('ai: { configured: true }', detail)

    def test_shared_public_ai_table_contains_no_account_scope(self) -> None:
        source = (WEB_ROOT / 'api' / '_publicIntelligenceDb.js').read_text(encoding='utf-8')
        start = source.index('CREATE TABLE IF NOT EXISTS public_ai_briefs')
        end = source.index('CREATE INDEX IF NOT EXISTS public_ai_briefs_lookup_idx', start)
        table = source[start:end]
        for forbidden in ['user_id', 'organization_id', 'customer_context', 'hospital_relationship', 'private_']:
            self.assertNotIn(forbidden, table)
        self.assertIn('result JSONB NOT NULL', table)

    def test_private_pilot_context_is_overlay_not_upstream_model_input(self) -> None:
        wrapper = (WEB_ROOT / 'api' / 'ai' / 'analyze.js').read_text(encoding='utf-8')
        core = (WEB_ROOT / 'api' / 'ai' / '_analyzeCore.js').read_text(encoding='utf-8')
        self.assertIn('__medicalChannelPrivateDecisionOverlay', wrapper)
        self.assertIn("body: { opportunity_id: opportunityId }", wrapper)
        self.assertNotIn('customer_context: privateContext.context', wrapper)
        self.assertIn('const privateOverlayContext = sanitizeCustomerContext(request.__medicalChannelPrivateDecisionOverlay)', core)
        self.assertIn('const ruleCustomerContext = privateOverlayContext ? null : clientCustomerContext', core)
        self.assertIn('applyPrivateDecisionOverlay(item.decision, privateOverlayContext)', core)
        self.assertIn('这只表示经营目标，不代表已有院内关系', core)
        self.assertIn("'PUBLIC_FACT_RULES_PLUS_PRIVATE_RULE_OVERLAY'", core)

    def test_unconfirmed_capability_overlay_never_claims_authorization(self) -> None:
        core = (WEB_ROOT / 'api' / 'ai' / '_analyzeCore.js').read_text(encoding='utf-8')
        self.assertIn("value === 'DIRECT_AUTHORIZED'", core)
        self.assertIn('已确认直接授权/供货能力', core)
        self.assertIn("value === 'DIRECT' || value === 'DIRECT_UNCONFIRMED'", core)
        self.assertIn('直接供货条件仍需确认', core)
        self.assertIn('厂家、授权或最终供货条件仍需在投入投标或正式承诺前确认', core)


if __name__ == '__main__':
    unittest.main()
