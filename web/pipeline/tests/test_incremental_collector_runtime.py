from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class IncrementalCollectorRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = (WEB_ROOT / "collector_incremental_runtime.py").read_text(encoding="utf-8")
        self.queue = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        self.trigger = (WEB_ROOT / "api" / "collector-run.py").read_text(encoding="utf-8")
        self.status = (WEB_ROOT / "api" / "collector-status.py").read_text(encoding="utf-8")
        self.scheduler = (WEB_ROOT / "collector_incremental_scheduler.py").read_text(encoding="utf-8")
        self.namespace = (WEB_ROOT / "collector_namespace.py").read_text(encoding="utf-8")
        self.vercel = json.loads((WEB_ROOT / "vercel.json").read_text(encoding="utf-8"))

    def test_incremental_trigger_reuses_existing_authenticated_function_and_queue(self) -> None:
        self.assertIn('mode == "incremental"', self.trigger)
        self.assertIn('Authorization: Bearer $CRON_SECRET', self.trigger)
        self.assertIn('QUEUE_TOPIC_NAME', self.trigger)
        self.assertIn('"mode": "incremental"', self.trigger)
        self.assertIn('scan_bucket_id(source_id, now=now)', self.trigger)
        self.assertIn('idempotency_key=f"{QUEUE_TOPIC_NAME}:{bucket_id}"', self.trigger)
        self.assertNotIn('user_id', self.trigger)
        self.assertNotIn('organization_id', self.trigger)

    def test_trigger_only_activates_explicitly_implemented_incremental_sources(self) -> None:
        self.assertIn('INCREMENTAL_SOURCE_IDS = SCHEDULED_INCREMENTAL_SOURCES', self.trigger)
        block = re.search(
            r"SUPPORTED_INCREMENTAL_SOURCES\s*=\s*\((.*?)\)\n\n",
            self.runtime,
            re.DOTALL,
        )
        scheduled = re.search(
            r"SCHEDULED_INCREMENTAL_SOURCES\s*=\s*\((.*?)\)\n\n",
            self.scheduler,
            re.DOTALL,
        )
        self.assertIsNotNone(block)
        self.assertIsNotNone(scheduled)
        self.assertNotIn('"ccgp"', block.group(1))
        self.assertNotIn('"ccgp"', scheduled.group(1))
        for source in (
            'tjmugh',
            'tjnothop',
            'teda',
            'tjfch',
            'tjfch_test',
            'tjzyefy',
            'tjzxfc',
        ):
            self.assertIn(f'"{source}"', block.group(1))
            self.assertIn(f'"{source}"', scheduled.group(1))

    def test_incremental_ledgers_and_staging_are_public_source_scoped_not_account_scoped(self) -> None:
        self.assertIn('collector-incremental-ledger:{source_id}:v2', self.runtime)
        self.assertIn('collector-incremental-bucket:{source_id}:v2', self.runtime)
        self.assertIn('collector-incremental-pending:{source_id}:v2', self.runtime)
        self.assertNotIn('user_id', self.runtime)
        self.assertNotIn('organization_id', self.runtime)
        self.assertNotIn('local_scope', self.runtime)

    def test_deep_and_incremental_mutations_are_serialized_with_runtime_leases(self) -> None:
        self.assertIn('INCREMENTAL_ACTIVE_KEY', self.namespace)
        self.assertIn('INCREMENTAL_ACTIVE_TTL_SECONDS = 15 * 60', self.namespace)
        self.assertIn('_acquire_incremental_lease(', self.queue)
        self.assertIn('_release_incremental_lease(cache, scan_id)', self.queue)
        self.assertIn('active_cycle_id(cache.get(ACTIVE_CYCLE_KEY))', self.queue)
        self.assertIn('cache.delete(INCREMENTAL_ACTIVE_KEY)', self.queue)
        self.assertIn('_release_active_cycle_if_owned(cycle_id)', self.queue)

    def test_deep_cycle_gets_priority_when_incremental_scan_is_already_active(self) -> None:
        self.assertIn('DEEP_START_DELAY_WHEN_INCREMENTAL_SECONDS = 300', self.trigger)
        self.assertIn('active_incremental_id(cache.get(INCREMENTAL_ACTIVE_KEY))', self.trigger)
        self.assertIn('delay=delay_seconds', self.trigger)
        self.assertIn('active_cycle_id(cache.get(ACTIVE_CYCLE_KEY))', self.trigger)
        self.assertIn('INCREMENTAL_BLOCKED_BY_DEEP_CYCLE', self.trigger)

    def test_terminal_deep_paths_release_active_cycle_lease(self) -> None:
        publish_release = self.queue.index('_release_active_cycle_if_owned(cycle_id)')
        retry_limit = self.queue.index('COLLECTOR_STAGE_RETRY_LIMIT')
        second_release = self.queue.index('_release_active_cycle_if_owned(cycle_id)', publish_release + 1)
        self.assertLess(publish_release, retry_limit)
        self.assertGreater(second_release, retry_limit)
        self.assertIn('cache.delete(ACTIVE_CYCLE_KEY)', self.queue)

    def test_incremental_failures_leave_bucket_open_for_idempotent_retry(self) -> None:
        self.assertIn('INCREMENTAL_DETAIL_VERIFICATION_INCOMPLETE', self.runtime)
        failure_index = self.runtime.index('if failures:')
        mark_index = self.runtime.rindex('_mark_bucket_completed(')
        self.assertLess(failure_index, mark_index)
        self.assertIn('record_verification_success(', self.runtime)
        self.assertIn('record_verification_failure(', self.runtime)

    def test_incremental_detail_failure_cannot_publish_partial_public_snapshot(self) -> None:
        failure_index = self.runtime.index('if failures:')
        canonical_write = self.runtime.index('runtime._cache_set(\n            cache,\n            cache_key,', failure_index)
        publish_index = self.runtime.index('_publish_snapshot_if_ready(cache, observed)', failure_index)
        failure_block = self.runtime[failure_index:canonical_write]
        self.assertLess(failure_index, canonical_write)
        self.assertLess(canonical_write, publish_index)
        self.assertIn('_save_pending_records(cache, source, staged_records)', failure_block)
        self.assertIn('"snapshot_refreshed": False', failure_block)
        self.assertIn('"snapshot_as_of": None', failure_block)
        self.assertIn('INCREMENTAL_DETAIL_VERIFICATION_INCOMPLETE', failure_block)
        self.assertNotIn('cache_key', failure_block)
        self.assertNotIn('_publish_snapshot_if_ready(', failure_block)

    def test_staged_partial_records_commit_only_after_source_scan_is_clean(self) -> None:
        failure_index = self.runtime.index('if failures:')
        commit_index = self.runtime.index('if staged_records:', failure_index)
        clear_index = self.runtime.index('_save_pending_records(cache, source, [])', commit_index)
        publish_index = self.runtime.index('_publish_snapshot_if_ready(cache, observed)', clear_index)
        self.assertLess(failure_index, commit_index)
        self.assertLess(commit_index, clear_index)
        self.assertLess(clear_index, publish_index)
        self.assertIn('runtime.merge_canonical_records(existing_records, staged_records)', self.runtime)
        self.assertIn('pending_record_count', self.runtime)

    def test_only_explicit_carryover_can_bypass_current_discovery_lookup(self) -> None:
        start = self.runtime.index('def _candidate_from_decision(')
        end = self.runtime.index('\n\ndef _publish_snapshot_if_ready', start)
        block = self.runtime[start:end]
        self.assertIn('if candidate is not None:', block)
        self.assertIn('if decision.reason == "PENDING_CARRYOVER":', block)
        self.assertIn('return decision.candidate', block)
        self.assertIn('raise RuntimeError("INCREMENTAL_SELECTED_CANDIDATE_MISSING")', block)

    def test_authoritative_deep_publish_discards_all_older_incremental_staging(self) -> None:
        self.assertIn('def clear_incremental_pending(cache: RuntimeCache)', self.runtime)
        start = self.queue.index('else:\n            # The completed deep cycle is authoritative')
        end = self.queue.index('        return', start)
        terminal = self.queue[start:end]
        health = terminal.index('update_automation_health(')
        clear = terminal.index('incremental_runtime.clear_incremental_pending(terminal_cache)')
        schedule = terminal.index('await _start_intraday_chain_after_deep()')
        release = terminal.index('_release_active_cycle_if_owned(cycle_id)')
        self.assertLess(health, clear)
        self.assertLess(clear, schedule)
        self.assertLess(schedule, release)

    def test_incremental_status_is_aggregate_only(self) -> None:
        for field in (
            'candidate_count',
            'verified_count',
            'failed_count',
            'unverified_count',
            'selected_detail_count',
            'skipped_unchanged_count',
            'active_scan_id',
        ):
            self.assertIn(f'"{field}"', self.status)
        self.assertNotIn('detail_url', self.status)
        self.assertNotIn('project_name', self.status)
        self.assertNotIn('title', self.status)
        self.assertNotIn('user_id', self.status)
        self.assertNotIn('organization_id', self.status)
        self.assertNotIn('local_scope', self.status)

    def test_high_frequency_crons_are_not_enabled_yet(self) -> None:
        crons = self.vercel.get('crons') or []
        self.assertEqual(
            crons,
            [{"path": "/api/collector-run", "schedule": "20 0 * * *"}],
        )
        functions = self.vercel.get('functions') or {}
        self.assertIn('api/collector-queue.py', functions)
        self.assertNotIn('api/collector-incremental.py', functions)


if __name__ == "__main__":
    unittest.main()
