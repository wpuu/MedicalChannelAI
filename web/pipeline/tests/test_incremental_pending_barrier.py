from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class IncrementalPendingBarrierTests(unittest.TestCase):
    def test_partial_failure_creates_records_and_unresolved_url_barrier(self) -> None:
        runtime = (WEB_ROOT / "collector_incremental_runtime.py").read_text(encoding="utf-8")
        self.assertIn("collector-incremental-pending-barrier:{source_id}:v2", runtime)
        failure = runtime.index("if failures:")
        deferred = runtime.index("if pending_barrier:", failure)
        block = runtime[failure:deferred]
        self.assertIn("_save_pending_records(cache, source, staged_records)", block)
        self.assertIn("_save_pending_barrier(cache, source, pending_barrier)", block)
        self.assertIn("INCREMENTAL_DETAIL_VERIFICATION_INCOMPLETE", block)

    def test_successful_retry_resolves_barrier_only_for_verified_url(self) -> None:
        runtime = (WEB_ROOT / "collector_incremental_runtime.py").read_text(encoding="utf-8")
        success = runtime.index("successful_urls.add(decision.candidate.detail_url)")
        load_barrier = runtime.index("pending_barrier = _load_pending_barrier(cache, source)", success)
        resolve = runtime.index("pending_barrier.difference_update(successful_urls)", load_barrier)
        add_failures = runtime.index('pending_barrier.update(item["url"] for item in failures)', resolve)
        self.assertLess(success, load_barrier)
        self.assertLess(load_barrier, resolve)
        self.assertLess(resolve, add_failures)

    def test_missing_failed_candidate_cannot_release_staged_siblings(self) -> None:
        runtime = (WEB_ROOT / "collector_incremental_runtime.py").read_text(encoding="utf-8")
        barrier = runtime.index("if pending_barrier:")
        canonical = runtime.index("if staged_records:", barrier)
        block = runtime[barrier:canonical]
        self.assertIn('"deferred_reason": "PENDING_VERIFICATION_BARRIER"', block)
        self.assertIn('"snapshot_refreshed": False', block)
        self.assertIn("_mark_bucket_completed(", block)
        self.assertNotIn("cache_key", block)
        self.assertNotIn("_publish_snapshot_if_ready", block)

    def test_clean_barrier_is_cleared_before_public_publish(self) -> None:
        runtime = (WEB_ROOT / "collector_incremental_runtime.py").read_text(encoding="utf-8")
        canonical = runtime.index("if staged_records:", runtime.index("if pending_barrier:"))
        clear = runtime.index("_save_pending_barrier(cache, source, set())", canonical)
        publish = runtime.index("_publish_snapshot_if_ready(cache, observed)", clear)
        self.assertLess(canonical, clear)
        self.assertLess(clear, publish)

    def test_authoritative_deep_clear_removes_records_and_barriers(self) -> None:
        runtime = (WEB_ROOT / "collector_incremental_runtime.py").read_text(encoding="utf-8")
        start = runtime.index("def clear_incremental_pending")
        end = runtime.index("def _last_completed_bucket", start)
        block = runtime[start:end]
        self.assertIn("cache.delete(_pending_cache_key(source_id))", block)
        self.assertIn("cache.delete(_pending_barrier_cache_key(source_id))", block)


if __name__ == "__main__":
    unittest.main()
