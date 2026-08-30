from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.medical_pilot.agnes_task_result import (
    MemoryAgnesTaskResultStore,
    SQLiteAgnesTaskResultStore,
    build_terminal_result,
    validate_terminal_result,
)


NOW = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
TASK_ID = "today|profile|2026-08-30|opp_22222222-2222-2222-2222-222222222222|" + "a" * 24
OPPORTUNITY_ID = "opp_22222222-2222-2222-2222-222222222222"
INPUT_SHA = "a" * 64


def ready_result() -> dict:
    return build_terminal_result(
        task_id=TASK_ID,
        opportunity_id=OPPORTUNITY_ID,
        model_input_sha256=INPUT_SHA,
        status="READY",
        completed_at=NOW,
        validated_output={"schema_version": "0.1", "opportunity_id": OPPORTUNITY_ID},
        rendered_decision={"action": "准备投标评估"},
        error_code=None,
    )


def rejected_result() -> dict:
    return build_terminal_result(
        task_id=TASK_ID,
        opportunity_id=OPPORTUNITY_ID,
        model_input_sha256=INPUT_SHA,
        status="MODEL_OUTPUT_REJECTED",
        completed_at=NOW,
        validated_output=None,
        rendered_decision=None,
        error_code="UNGROUNDED_FACT_REFERENCE",
    )


class AgnesTaskResultTests(unittest.TestCase):
    def test_ready_put_get_and_duplicate_is_idempotent(self) -> None:
        store = MemoryAgnesTaskResultStore()
        result = ready_result()
        self.assertTrue(store.put_if_absent(TASK_ID, result))
        self.assertEqual(store.get(TASK_ID), result)
        self.assertFalse(store.put_if_absent(TASK_ID, result))
        self.assertEqual(store.get(TASK_ID), result)

    def test_model_output_rejected_is_valid_terminal(self) -> None:
        result = rejected_result()
        validate_terminal_result(TASK_ID, result)
        store = MemoryAgnesTaskResultStore()
        self.assertTrue(store.put_if_absent(TASK_ID, result))
        self.assertEqual(store.get(TASK_ID)["status"], "MODEL_OUTPUT_REJECTED")

    def test_provider_error_cannot_be_persisted_as_terminal(self) -> None:
        bad = ready_result()
        bad["status"] = "PROVIDER_ERROR"
        bad["validated_output"] = None
        bad["rendered_decision"] = None
        bad["error_code"] = "MODEL_CALL_FAILED"
        with self.assertRaises(ValueError):
            validate_terminal_result(TASK_ID, bad)
        with self.assertRaises(ValueError):
            MemoryAgnesTaskResultStore().put_if_absent(TASK_ID, bad)

    def test_sqlite_two_store_instances_share_task_uniqueness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agnes-results.sqlite3"
            store_a = SQLiteAgnesTaskResultStore(path)
            store_b = SQLiteAgnesTaskResultStore(path)
            result = ready_result()
            self.assertTrue(store_a.put_if_absent(TASK_ID, result))
            self.assertFalse(store_b.put_if_absent(TASK_ID, result))
            self.assertEqual(store_b.get(TASK_ID), result)

    def test_terminal_hash_and_task_identity_are_required(self) -> None:
        bad = ready_result()
        bad["model_input_sha256"] = "NOT_SHA"
        with self.assertRaises(ValueError):
            validate_terminal_result(TASK_ID, bad)
        mismatch = ready_result()
        mismatch["task_id"] = "other-task"
        with self.assertRaises(ValueError):
            validate_terminal_result(TASK_ID, mismatch)


if __name__ == "__main__":
    unittest.main()
