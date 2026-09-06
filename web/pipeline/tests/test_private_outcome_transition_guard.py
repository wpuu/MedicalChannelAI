from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class PrivateOutcomeTransitionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_api = (WEB_ROOT / "api" / "_privateCore.js").read_text(encoding="utf-8")

    def test_server_has_exact_controlled_win_and_loss_review_labels(self) -> None:
        self.assertIn("const WON_REVIEW_NOTE_PREFIX = '成交复盘（当前用户判断）：'", self.private_api)
        self.assertIn("const LOST_REVIEW_NOTE_PREFIX = '未成交原因（当前用户判断）：'", self.private_api)
        self.assertIn("'方案与客户需求匹配'", self.private_api)
        self.assertIn("'客户需求或项目变化'", self.private_api)
        self.assertIn('return labels.has(label)', self.private_api)

    def test_transition_guard_uses_locked_current_status(self) -> None:
        self.assertIn('SELECT id, status, remind_at FROM private_followups', self.private_api)
        self.assertIn("(mutation.status === 'WON' || mutation.status === 'LOST')", self.private_api)
        self.assertIn('followup.status !== mutation.status', self.private_api)
        self.assertIn('!hasControlledOutcomeReview(mutation.status, mutation.note)', self.private_api)
        self.assertIn("throw new Error('FOLLOWUP_OUTCOME_REVIEW_REQUIRED')", self.private_api)
        self.assertIn("sendJson(response, 400, { error: 'FOLLOWUP_OUTCOME_REVIEW_REQUIRED' })", self.private_api)

    def test_same_terminal_status_can_still_accept_later_freeform_notes(self) -> None:
        guard = self.private_api.index("(mutation.status === 'WON' || mutation.status === 'LOST')")
        status_check = self.private_api.index('followup.status !== mutation.status', guard)
        review_check = self.private_api.index('!hasControlledOutcomeReview(mutation.status, mutation.note)', status_check)
        self.assertLess(guard, status_check)
        self.assertLess(status_check, review_check)

    def test_idempotency_short_circuits_before_transition_guard(self) -> None:
        existing = self.private_api.index('const existingMutation = await tx`')
        short_circuit = self.private_api.index('if (existingMutation.length) return', existing)
        guard = self.private_api.index("(mutation.status === 'WON' || mutation.status === 'LOST')")
        self.assertLess(existing, short_circuit)
        self.assertLess(short_circuit, guard)

    def test_guard_executes_before_event_insert_and_status_update(self) -> None:
        guard = self.private_api.index("throw new Error('FOLLOWUP_OUTCOME_REVIEW_REQUIRED')")
        event_insert = self.private_api.index('INSERT INTO private_followup_events', guard)
        status_update = self.private_api.index('UPDATE private_followups', event_insert)
        self.assertLess(guard, event_insert)
        self.assertLess(event_insert, status_update)


if __name__ == '__main__':
    unittest.main()
