from __future__ import annotations

import re
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
STATUS_API = WEB_ROOT / 'src' / 'services' / 'runtimeStatusApi.ts'
TODAY_PAGE = WEB_ROOT / 'src' / 'pages' / 'TodayPage.tsx'
DETAIL_PAGE = WEB_ROOT / 'src' / 'pages' / 'OpportunityDetailPage.tsx'
POOL_PAGE = WEB_ROOT / 'src' / 'pages' / 'OpportunityPoolPage.tsx'
SERVER_STATUS = WEB_ROOT / 'api' / 'status.js'


class RuntimeStatusUiContractTests(unittest.TestCase):
    def test_frontend_accepts_all_server_snapshot_source_modes(self) -> None:
        client = STATUS_API.read_text(encoding='utf-8')
        server = SERVER_STATUS.read_text(encoding='utf-8')
        snapshot_loader = (WEB_ROOT / 'api' / '_verifiedSnapshot.js').read_text(encoding='utf-8')
        # Derive the server-side mode list from source instead of hard-coding it:
        # a mode the browser validator does not know (e.g. DATABASE after the
        # durable store landed) makes isRuntimeStatus() fail and pauses AI
        # automation for every user even while the snapshot is fresh.
        server_modes = set(re.findall(r"lastSourceMode = '([A-Z_]+)'", snapshot_loader))
        failure_line = re.search(r"const failureMode = (.*)", server).group(1)
        server_modes.update(re.findall(r"'([A-Z_]+)'", failure_line))
        self.assertIn('DATABASE', server_modes)
        self.assertGreaterEqual(server_modes, {'BUNDLED', 'DATABASE', 'RUNTIME_CACHE', 'REMOTE', 'BUNDLED_FALLBACK', 'UNAVAILABLE'})
        set_start = client.index('SNAPSHOT_SOURCE_MODES = new Set')
        client_set = client[set_start:client.index('])', set_start)]
        union_start = client.index('export type RuntimeSnapshotSourceMode')
        client_union = client[union_start:client.index('export interface RuntimeStatus', union_start)]
        for mode in sorted(server_modes):
            self.assertIn(f"'{mode}'", client_set, f'browser SNAPSHOT_SOURCE_MODES must accept {mode}')
            self.assertIn(f"'{mode}'", client_union, f'RuntimeSnapshotSourceMode must include {mode}')
        self.assertIn("lastSourceMode = 'RUNTIME_CACHE'", snapshot_loader)
        self.assertIn("lastSourceMode = 'BUNDLED_FALLBACK'", snapshot_loader)
        self.assertIn("lastRuntimeOrigin = runtimeResult.origin", snapshot_loader)
        self.assertIn("runtime_origin: sourceMode === 'RUNTIME_CACHE' ? runtimeOrigin : null", server)
        self.assertIn("runtime_origin?: 'PUBLISHED' | 'BUNDLED' | null", client)
        self.assertIn('SNAPSHOT_STALE_AFTER_MINUTES = 30 * 60', server)

    def test_shared_runtime_helpers_surface_stale_fallback_and_unavailable_snapshot(self) -> None:
        helper = STATUS_API.read_text(encoding='utf-8')
        today = TODAY_PAGE.read_text(encoding='utf-8')
        detail = DETAIL_PAGE.read_text(encoding='utf-8')
        pool = POOL_PAGE.read_text(encoding='utf-8')

        # Keep source-mode/freshness policy in one shared helper instead of
        # duplicating fragile comparisons inside individual pages.
        self.assertIn("status.snapshot.source_mode === 'BUNDLED_FALLBACK'", helper)
        for freshness in ['STALE', 'INVALID', 'UNAVAILABLE']:
            self.assertIn(f"status.snapshot.freshness === '{freshness}'", helper)
        self.assertIn('runtimeSnapshotWarning', helper)
        self.assertIn('runtimeAutomationUnavailableReason', helper)
        self.assertIn('暂停自动分析与沟通草稿', helper)
        self.assertIn('官方依据', helper)
        self.assertIn("if (!checked) return '正在确认公开商机快照状态，自动分析与沟通草稿暂不可用。'", helper)

        # Today, full pool, and direct detail navigation must all consume the
        # same runtime boundary so stale data cannot be bypassed by another UI.
        for source in [today, detail, pool]:
            self.assertIn('getRuntimeStatus()', source)
            self.assertIn('runtimeSnapshotWarning', source)
            self.assertIn('runtimeAutomationUnavailableReason', source)

        self.assertIn('automationUnavailableReason={automationUnavailableReason}', today)
        self.assertIn('if (!automationUnavailableReason) setOutreachId', today)
        self.assertIn('analysisDisabled={Boolean(automationUnavailableReason)}', detail)
        self.assertIn('Boolean(automationUnavailableReason)', detail)
        self.assertIn('runtimeStatusChecked', pool)
        self.assertIn('aiUnavailableReason ? undefined : () => void analyze', pool)
        self.assertIn('analysisUnavailableReason={aiUnavailableReason}', pool)

    def test_stale_snapshot_blocks_only_automation_not_manual_crm_actions(self) -> None:
        today = TODAY_PAGE.read_text(encoding='utf-8')
        detail = DETAIL_PAGE.read_text(encoding='utf-8')
        pool = POOL_PAGE.read_text(encoding='utf-8')

        # Manual CRM actions must remain available for already-known facts even
        # when fresh automated recommendations are paused.
        for marker in ["onContacted", "onFollow", "onNotFit", "onRemind"]:
            self.assertIn(marker, today)
        self.assertIn('<FollowupCard', detail)
        self.assertIn('onChangeStatus=', detail)
        self.assertIn('onAddNote=', detail)
        self.assertIn('onRemind=', detail)
        self.assertIn('onFollow={() => void addToFollowups', pool)
        self.assertIn('官方依据', pool)


if __name__ == '__main__':
    unittest.main()
