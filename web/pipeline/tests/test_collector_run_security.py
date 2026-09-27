from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_RUN = WEB_ROOT / "api" / "collector-run.py"


class CollectorRunSecurityTests(unittest.TestCase):
    def test_temporary_acceptance_probe_is_removed(self) -> None:
        source = COLLECTOR_RUN.read_text(encoding="utf-8")
        self.assertNotIn("ACCEPTANCE_PROBE", source)
        self.assertNotIn('cycle_id = f"accept:', source)
        self.assertNotIn('mode == "acceptance"', source)
        # Query parsing is now a production feature for authenticated incremental
        # source scans; it must never become an alternate authentication path.
        self.assertIn("parse_qs", source)
        self.assertIn("urlsplit", source)
        self.assertIn('mode == "incremental"', source)

    def test_trigger_requires_cron_secret_before_reading_incremental_query(self) -> None:
        source = COLLECTOR_RUN.read_text(encoding="utf-8")
        auth_call = source.index("allowed, trigger_source = _authorized(self)")
        auth_reject = source.index('COLLECTOR_TRIGGER_FORBIDDEN', auth_call)
        query_read = source.index("query = _request_query(self)", auth_call)
        self.assertLess(auth_call, auth_reject)
        self.assertLess(auth_reject, query_read)
        self.assertIn('INCREMENTAL_SOURCE_UNSUPPORTED', source)
        self.assertIn('COLLECTOR_MODE_INVALID', source)

    def test_same_day_recovery_cycles_are_counted_bounded_and_persisted_before_send(self) -> None:
        source = COLLECTOR_RUN.read_text(encoding="utf-8")
        self.assertIn("def _plan_cycle(state: object, *, local_date: str)", source)
        self.assertIn('return f"prod:{local_date}:recovery-{attempt}", True', source)
        self.assertIn("if attempt > MAX_RECOVERY_CYCLES_PER_DAY:", source)
        self.assertIn('raise CollectorStartConflict("COLLECTOR_RECOVERY_LIMIT")', source)
        self.assertIn('raise CollectorStartConflict("COLLECTOR_CYCLE_ALREADY_COMPLETED_TODAY")', source)
        # Counter + attempt reset are persisted before the queue send so a failed
        # send can never reuse a cycle id (Vercel Queues rejects reused keys for 24h).
        self.assertLess(source.index("write_collector_state(cache, state, now=now)"), source.index("message_id = await send("))
        self.assertNotIn("recovery-v3", source)
        self.assertNotIn("recovery-v6", source)
        self.assertNotIn("recovery-v7", source)
        self.assertNotIn("_recovery_cycle_id", source)
        self.assertNotIn("uuid", source.lower())

    def test_new_cycle_is_blocked_only_by_a_live_stage_lease_and_releases_on_send_failure(self) -> None:
        source = COLLECTOR_RUN.read_text(encoding="utf-8")
        self.assertNotIn("MIGRATION_STALE_RUNNING_AFTER", source)
        self.assertNotIn("_migration_recovery_running_stages_are_stale", source)
        self.assertIn("if cycle_has_live_running_stage(current_state, now=now):", source)
        self.assertIn('raise CollectorStartConflict("COLLECTOR_CYCLE_ALREADY_RUNNING")', source)
        self.assertIn("except DuplicateIdempotencyKeyError as exc:", source)
        self.assertIn('raise CollectorStartConflict("COLLECTOR_CYCLE_ALREADY_QUEUED") from exc', source)
        enqueue = source[source.index("async def _enqueue_start"):source.index("async def _enqueue_incremental")]
        self.assertIn("except Exception:", enqueue)
        self.assertIn("_release_cycle_if_owned(cache, cycle_id)", enqueue)
        self.assertIn("raise", enqueue)

    def test_trigger_requires_cron_secret_and_bearer_auth_fail_closed(self) -> None:
        source = COLLECTOR_RUN.read_text(encoding="utf-8")
        self.assertIn('os.environ.get("CRON_SECRET")', source)
        self.assertIn("if not cron_secret:", source)
        self.assertIn('request.headers.get("authorization")', source)
        self.assertIn('hmac.compare_digest(authorization, f"Bearer {cron_secret}")', source)
        self.assertIn('return True, "VERCEL_CRON"', source)
        self.assertNotIn('x-vercel-cron-schedule', source)
        self.assertLess(source.index("if not cron_secret:"), source.index('return True, "VERCEL_CRON"'))
        self.assertLess(source.index("hmac.compare_digest"), source.index('return True, "VERCEL_CRON"'))
        self.assertIn("cycle_id, is_recovery = _plan_cycle(state, local_date=local_date)", source)


if __name__ == "__main__":
    unittest.main()
