from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.medical_pilot.agnes_dispatch_queue import (
    MemoryAgnesDispatchQueue,
    SQLiteAgnesDispatchQueue,
    queue_today_actions_dispatch,
)
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions import build_today_actions
from tools.medical_pilot.today_actions_dispatch import build_today_actions_agnes_dispatch


NOW = datetime(2026, 8, 30, 8, 10, tzinfo=ZoneInfo("Asia/Shanghai"))


def build_dispatch() -> dict:
    profile = complete_profile()
    item = opportunity()
    fact = {
        "schema_version": "0.1",
        "fact_id": "fact_queue_demo",
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": item["project_name"],
        "source_url": "https://www.ccgp.gov.cn/example/queue",
    }
    today = build_today_actions(
        profile=profile,
        opportunities=[item],
        evidence_facts_by_opportunity={item["opportunity_id"]: [fact]},
    )
    return build_today_actions_agnes_dispatch(
        profile_id=profile["profile_id"],
        today_actions=today,
        now=NOW,
    )


class AgnesDispatchQueueTests(unittest.TestCase):
    def test_same_dispatch_is_enqueued_once(self) -> None:
        queue = MemoryAgnesDispatchQueue()
        dispatch = build_dispatch()
        first = queue_today_actions_dispatch(queue, dispatch, enqueued_at=NOW)
        second = queue_today_actions_dispatch(queue, dispatch, enqueued_at=NOW)
        self.assertEqual(first, {"inserted": 1, "duplicate": 0, "total": 1})
        self.assertEqual(second, {"inserted": 0, "duplicate": 1, "total": 1})
        self.assertEqual(len(queue.list_pending(limit=10)), 1)

    def test_queue_item_keeps_server_side_model_input_and_global_lease_requirement(self) -> None:
        queue = MemoryAgnesDispatchQueue()
        dispatch = build_dispatch()
        queue_today_actions_dispatch(queue, dispatch, enqueued_at=NOW)
        row = queue.list_pending(limit=10)[0]
        self.assertEqual(row["source"], "TODAY_ACTIONS")
        self.assertTrue(row["dispatch_item"]["requires_global_lease"])
        self.assertEqual(row["model_input_sha256"], dispatch["task_payloads"][0]["model_input_sha256"])
        self.assertEqual(row["model_input"]["opportunity_id"], row["opportunity_id"])

    def test_sqlite_two_instances_share_task_uniqueness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dispatch.sqlite3"
            queue_a = SQLiteAgnesDispatchQueue(path)
            queue_b = SQLiteAgnesDispatchQueue(path)
            dispatch = build_dispatch()
            self.assertEqual(queue_today_actions_dispatch(queue_a, dispatch, enqueued_at=NOW)["inserted"], 1)
            self.assertEqual(queue_today_actions_dispatch(queue_b, dispatch, enqueued_at=NOW)["duplicate"], 1)
            self.assertEqual(len(queue_b.list_pending(limit=10)), 1)

    def test_delete_removes_terminal_or_reconciled_work(self) -> None:
        queue = MemoryAgnesDispatchQueue()
        dispatch = build_dispatch()
        queue_today_actions_dispatch(queue, dispatch, enqueued_at=NOW)
        task_id = dispatch["task_payloads"][0]["task_id"]
        self.assertTrue(queue.delete(task_id))
        self.assertFalse(queue.delete(task_id))
        self.assertIsNone(queue.get(task_id))

    def test_tampered_hash_or_task_identity_is_rejected(self) -> None:
        dispatch = build_dispatch()
        dispatch["task_payloads"][0]["model_input_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            queue_today_actions_dispatch(MemoryAgnesDispatchQueue(), dispatch, enqueued_at=NOW)


if __name__ == "__main__":
    unittest.main()
