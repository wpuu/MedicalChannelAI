from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class TodayRequestPressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = (WEB_ROOT / "src" / "pages" / "TodayPage.tsx").read_text(encoding="utf-8")

    def test_reminders_do_not_block_primary_today_loading(self) -> None:
        self.assertIn("const loadReminders = useCallback(async () =>", self.page)
        start = self.page.index("const load = useCallback(async")
        end = self.page.index("useEffect(() =>", start)
        block = self.page[start:end]
        self.assertIn("void loadReminders()", block)
        self.assertIn("const res = await todayActionsService.getTodayActions()", block)
        self.assertNotIn("await getDueReminders()", block)
        self.assertIn("setLoading(false)", block)

    def test_runtime_health_starts_with_today_but_is_not_awaited(self) -> None:
        self.assertIn("const loadRuntimeStatus = useCallback(() =>", self.page)
        start = self.page.index("const load = useCallback(async")
        end = self.page.index("useEffect(() =>", start)
        block = self.page[start:end]
        self.assertIn("loadRuntimeStatus()", block)
        self.assertNotIn("await getRuntimeStatus()", block)

    def test_auxiliary_auth_failure_still_redirects(self) -> None:
        start = self.page.index("const loadReminders = useCallback(async () =>")
        end = self.page.index("const loadRuntimeStatus", start)
        block = self.page[start:end]
        self.assertIn("isAuthRequiredError(cause)", block)
        self.assertIn("navigate('/login', { replace: true })", block)


if __name__ == "__main__":
    unittest.main()
