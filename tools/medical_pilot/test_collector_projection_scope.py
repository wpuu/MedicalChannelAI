from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from .collector_store import SQLitePublicEventLedger, persist_collector_result
from .test_collector_store import built, notice
from .today_repo import SQLiteTodayActionsRepository


class CollectorProjectionScopeTests(unittest.TestCase):
    def test_old_product_taxonomy_does_not_survive_new_current_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.sqlite"
            repository = SQLiteTodayActionsRepository(path)
            ledger = SQLitePublicEventLedger(path)

            old_notice = notice(
                url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260820_scope.htm",
                notice_type="TENDER",
                published_at="2026-08-20T09:00:00+08:00",
                title="流式细胞仪购置项目",
            )
            new_notice = notice(
                url="https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202608/t20260830_scope.htm",
                notice_type="AWARD",
                published_at="2026-08-30T09:00:00+08:00",
                title="办公家具购置项目",
            )
            old_event, old_facts = built(old_notice, "2026-08-20T01:00:00Z")
            new_event, new_facts = built(new_notice, "2026-08-30T01:00:00Z")

            persist_collector_result(
                repository=repository,
                event_ledger=ledger,
                event=old_event,
                facts=old_facts,
            )
            current = persist_collector_result(
                repository=repository,
                event_ledger=ledger,
                event=new_event,
                facts=new_facts,
            )

            self.assertEqual(current["lifecycle_state"], "AWARDED")
            self.assertEqual(current["project_name"], "办公家具购置项目")
            self.assertNotIn("LAB_FLOW_CYTOMETER", current["product_labels"])
            self.assertEqual(current["product_label_validation_status"], "UNVERIFIED")
            self.assertIs(current["is_rental_project"], False)


if __name__ == "__main__":
    unittest.main()
