from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class FollowupOutcomeLearningUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.types = (WEB_ROOT / "src" / "types" / "index.ts").read_text(encoding="utf-8")
        cls.labels = (WEB_ROOT / "src" / "utils" / "labels.ts").read_text(encoding="utf-8")
        cls.card = (WEB_ROOT / "src" / "components" / "opportunity" / "FollowupCard.tsx").read_text(encoding="utf-8")
        cls.lost_modal = (WEB_ROOT / "src" / "components" / "followup" / "LostModal.tsx").read_text(encoding="utf-8")
        cls.not_fit_modal = (WEB_ROOT / "src" / "components" / "followup" / "NotFitModal.tsx").read_text(encoding="utf-8")
        cls.detail = (WEB_ROOT / "src" / "pages" / "OpportunityDetailPage.tsx").read_text(encoding="utf-8")

    def test_lost_reason_has_bounded_business_categories(self) -> None:
        self.assertIn('export type LostReason =', self.types)
        self.assertIn('价格/报价竞争失败', self.labels)
        self.assertIn('产品或参数不匹配', self.labels)
        self.assertIn('厂家/授权资源不足', self.labels)
        self.assertIn('投标/响应执行失败', self.labels)
        self.assertIn('客户需求或项目变化', self.labels)

    def test_lost_status_requires_explicit_reason_flow_in_ui(self) -> None:
        self.assertIn("if (status === 'LOST')", self.card)
        self.assertIn('onLost()', self.card)
        self.assertIn('onLost={() => setLostOpen(true)}', self.detail)
        self.assertIn('<LostModal', self.detail)

    def test_lost_reason_is_clearly_private_user_judgment(self) -> None:
        self.assertIn('当前账号私有复盘数据', self.lost_modal)
        self.assertIn('不是医院或采购方公开确认的事实', self.lost_modal)
        self.assertIn('未成交原因（当前用户判断）：${reason}', self.detail)
        self.assertNotIn('facts.', self.lost_modal)
        self.assertNotIn('public_snapshot', self.lost_modal)

    def test_not_fit_persistence_copy_matches_runtime_mode(self) -> None:
        self.assertIn('isApiMode', self.not_fit_modal)
        self.assertIn('会保存到服务器，不会写入公开商机事实', self.not_fit_modal)
        self.assertIn('演示模式下只保存在当前浏览器', self.not_fit_modal)

    def test_terminal_results_require_explicit_two_step_reopen(self) -> None:
        self.assertIn('const terminal = REMINDER_TERMINAL_STATUSES.has(card.followup_status)', self.card)
        self.assertIn('更正结果 / 重新打开', self.card)
        self.assertIn('确认重新打开', self.card)
        self.assertIn("setStatus('REVIEWING')", self.card)
        self.assertIn("onChangeStatus('REVIEWING')", self.card)
        self.assertIn('保留原有结果和复盘历史', self.card)
        self.assertIn('当前结果将不再计入终态统计', self.card)
        terminal_start = self.card.index('{terminal ? (')
        normal_select = self.card.index('<select', terminal_start)
        reopen_copy = self.card.index('更正结果 / 重新打开', terminal_start)
        self.assertLess(reopen_copy, normal_select)


if __name__ == '__main__':
    unittest.main()
