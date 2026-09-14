from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class AgnesAsyncCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        cls.continuation = (WEB_ROOT / 'api' / 'ai' / '_discoverContinuation.js').read_text(encoding='utf-8')
        cls.client = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarApi.ts').read_text(encoding='utf-8')
        cls.store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        cls.page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        cls.continuation_client = (WEB_ROOT / 'src' / 'services' / 'discoveryContinuationApi.ts').read_text(encoding='utf-8')

    def test_root_uses_wait_until_runtime_cache_and_longer_background_budget(self) -> None:
        self.assertIn("import { getCache, waitUntil } from '@vercel/functions'", self.root)
        self.assertIn('export const config = { maxDuration: 45 }', self.root)
        self.assertIn('BACKGROUND_PROVIDER_TIMEOUT_MS = 25_000', self.root)
        self.assertIn("AI_CACHE_PREFIX = 'medicalchannelai:agnes-discovery:v1'", self.root)
        self.assertIn('waitUntil(task)', self.root)
        self.assertIn("state: 'PENDING'", self.root)
        self.assertIn("state: 'READY'", self.root)
        self.assertIn("state: 'FAILED'", self.root)

    def test_root_cache_key_is_hashed_and_bound_to_analysis_and_content(self) -> None:
        start = self.root.index('function aiCacheKey(')
        end = self.root.index('function cachedCandidateRows', start)
        block = self.root[start:end]
        self.assertIn("createHash('sha256')", block)
        self.assertIn('ANALYSIS_VERSION', block)
        self.assertIn('fingerprint', block)
        self.assertIn('aiCacheSourceSignature(source)', block)
        self.assertNotIn('source.name}:', block)

    def test_agnes3_thinking_is_disabled_on_root_and_continuation(self) -> None:
        expected = 'chat_template_kwargs: { enable_thinking: false }'
        self.assertIn(expected, self.root)
        self.assertIn(expected, self.continuation)
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.root)
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.continuation)

    def test_pending_is_explicit_and_never_reused_as_completed_scan(self) -> None:
        self.assertIn("'AI_REFRESH_PENDING'", self.client)
        self.assertIn("'STALE_WHILE_AI_REFRESH'", self.client)
        self.assertIn("'SERVER_AI_CACHE'", self.client)
        self.assertIn('ai_refresh_pending: boolean', self.client)
        self.assertIn('if (!result || result.ai_refresh_pending) return undefined', self.client)
        self.assertIn('previous.ai_refresh_pending === true', self.root)
        self.assertIn('AI后台分析中', self.page)
        self.assertIn('AI_REFRESH_RETRY_DELAYS_MS', self.page)

    def test_pending_does_not_claim_zero_yield_or_merge_findings(self) -> None:
        self.assertIn('const pending = result.ai_refresh_pending === true', self.store)
        self.assertIn('pending ? 0 : result.candidate_count', self.store)
        self.assertIn('base.consecutive_zero_candidate_count', self.store)
        self.assertIn('result.ai_refresh_pending ? current.findings : mergeDiscoveryFindings', self.page)

    def test_force_ai_replaces_instead_of_merging_ready_cache(self) -> None:
        self.assertIn("const baseParsed = body?.force_ai === true", self.root)
        self.assertIn("? emptyParsed()", self.root)

    def test_continuation_ledger_accepts_v2_segments(self) -> None:
        ledger = (WEB_ROOT / 'src' / 'services' / 'discoveryContinuationLedger.ts').read_text(encoding='utf-8')
        self.assertIn("row.analysis_version !== 'agnes-discovery-continuation-v2'", ledger)
        self.assertNotIn("row.analysis_version !== 'agnes-discovery-continuation-v1'", ledger)

    def test_multi_scan_does_not_spawn_client_poll_storm(self) -> None:
        self.assertIn('{ preserveBusy: true, autoRetry: false }', self.page)

    def test_continuation_contract_is_single_enum_and_versioned_with_root(self) -> None:
        self.assertIn("ROOT_ANALYSIS_VERSION = 'agnes-discovery-live-v5-async-cache'", self.continuation)
        self.assertIn("CONTINUATION_ANALYSIS_VERSION = 'agnes-discovery-continuation-v2'", self.continuation)
        self.assertIn('allowed_signal_types: Array.from(SIGNAL_TYPES)', self.continuation)
        self.assertIn("signal_type: '单个字符串枚举值'", self.continuation)
        self.assertNotIn('signal_type: Array.from(SIGNAL_TYPES)', self.continuation)
        self.assertIn("analysis_version: 'agnes-discovery-continuation-v2'", self.continuation_client)


if __name__ == '__main__':
    unittest.main()
