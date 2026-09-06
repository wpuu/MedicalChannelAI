from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))

from collector_incremental_ticks import (  # noqa: E402
    MAX_TICKS_PER_DAY,
    TICK_INTERVAL_MINUTES,
    first_tick_after_deep,
    next_tick_after,
    parse_tick_schedule,
    same_china_business_date,
    tick_delay_seconds,
    tick_from_payload,
)


class IncrementalTickChainTests(unittest.TestCase):
    def test_first_tick_waits_until_china_business_window(self) -> None:
        deep_done = datetime(2026, 9, 4, 3, 5, tzinfo=timezone.utc)  # 11:05 CST
        tick = first_tick_after_deep(deep_done)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.business_date, "2026-09-04")
        self.assertEqual(tick.scheduled_for, "2026-09-04T03:30:00+00:00")  # 11:30 CST
        self.assertEqual(tick.sequence, 1)

    def test_deep_publish_after_business_window_does_not_start_chain(self) -> None:
        deep_done = datetime(2026, 9, 4, 11, 30, tzinfo=timezone.utc)  # 19:30 CST
        self.assertIsNone(first_tick_after_deep(deep_done))

    def test_chain_runs_every_fifteen_minutes_and_stops_same_day(self) -> None:
        self.assertEqual(TICK_INTERVAL_MINUTES, 15)
        first = first_tick_after_deep(datetime(2026, 9, 4, 3, 5, tzinfo=timezone.utc))
        self.assertIsNotNone(first)
        current = first
        ticks = [current]
        while True:
            scheduled = parse_tick_schedule(current)
            self.assertIsNotNone(scheduled)
            nxt = next_tick_after(current, delivered_at=scheduled)
            if nxt is None:
                break
            ticks.append(nxt)
            current = nxt
        self.assertEqual(MAX_TICKS_PER_DAY, 31)
        self.assertEqual(len(ticks), MAX_TICKS_PER_DAY)
        self.assertEqual(ticks[-1].scheduled_for, "2026-09-04T11:00:00+00:00")  # 19:00 CST
        self.assertTrue(all(item.business_date == "2026-09-04" for item in ticks))

    def test_small_delivery_delay_does_not_double_tick_interval(self) -> None:
        first = first_tick_after_deep(datetime(2026, 9, 4, 3, 5, tzinfo=timezone.utc))
        self.assertIsNotNone(first)
        delivered = datetime(2026, 9, 4, 3, 30, 5, tzinfo=timezone.utc)  # 11:30:05 CST
        nxt = next_tick_after(first, delivered_at=delivered)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.scheduled_for, "2026-09-04T03:45:00+00:00")  # 11:45 CST

    def test_late_delivery_skips_backlog_to_first_future_aligned_tick(self) -> None:
        first = first_tick_after_deep(datetime(2026, 9, 4, 3, 5, tzinfo=timezone.utc))
        self.assertIsNotNone(first)
        delayed = datetime(2026, 9, 4, 4, 7, tzinfo=timezone.utc)  # 12:07 CST
        nxt = next_tick_after(first, delivered_at=delayed)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.scheduled_for, "2026-09-04T04:15:00+00:00")  # 12:15 CST

    def test_business_date_guard_uses_china_date_not_utc_date(self) -> None:
        queued = datetime(2026, 9, 4, 11, 0, tzinfo=timezone.utc)  # 19:00 China Sep 4
        same_day = datetime(2026, 9, 4, 15, 50, tzinfo=timezone.utc)  # 23:50 China Sep 4
        next_day = datetime(2026, 9, 4, 16, 5, tzinfo=timezone.utc)  # 00:05 China Sep 5
        self.assertTrue(same_china_business_date(queued, same_day))
        self.assertFalse(same_china_business_date(queued, next_day))

    def test_incremental_source_redelivery_checks_business_date_before_lease(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        start = source.index("def _process_incremental_payload")
        end = source.index("async def _process_incremental_tick_payload", start)
        block = source[start:end]
        date_guard = block.index("same_china_business_date(observed_at, delivered_at)")
        lease = block.index("_acquire_incremental_lease(")
        self.assertLess(date_guard, lease)

    def test_tick_payload_is_self_authenticating_by_schedule_contract(self) -> None:
        tick = first_tick_after_deep(datetime(2026, 9, 4, 3, 5, tzinfo=timezone.utc))
        self.assertIsNotNone(tick)
        payload = {
            "business_date": tick.business_date,
            "scheduled_for": tick.scheduled_for,
            "tick_id": tick.tick_id,
            "sequence": tick.sequence,
        }
        self.assertEqual(tick_from_payload(payload), tick)
        payload["sequence"] = 99
        self.assertIsNone(tick_from_payload(payload))

    def test_tick_delay_never_becomes_negative(self) -> None:
        tick = first_tick_after_deep(datetime(2026, 9, 4, 3, 5, tzinfo=timezone.utc))
        self.assertIsNotNone(tick)
        self.assertEqual(
            tick_delay_seconds(tick, now=datetime(2026, 9, 4, 3, 20, tzinfo=timezone.utc)),
            600,
        )
        self.assertEqual(
            tick_delay_seconds(tick, now=datetime(2026, 9, 4, 3, 40, tzinfo=timezone.utc)),
            0,
        )

    def test_queue_chain_is_accepted_before_terminal_deep_lease_is_released(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        terminal = source.index('await _start_intraday_chain_after_deep()')
        release = source.index('_release_active_cycle_if_owned(cycle_id)', terminal)
        retry_limit = source.index('COLLECTOR_STAGE_RETRY_LIMIT', release)
        self.assertLess(terminal, release)
        self.assertLess(release, retry_limit)
        failure_branch = source[retry_limit:]
        self.assertNotIn('_start_intraday_chain_after_deep()', failure_branch)

    def test_chain_start_send_failure_is_retriable_instead_of_silently_stopping_day(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        start = source.index('async def _start_intraday_chain_after_deep')
        end = source.index('async def process_collector_payload', start)
        block = source[start:end]
        self.assertIn('state="SCHEDULE_RETRY_PENDING"', block)
        self.assertIn('await _enqueue_incremental_tick(first_tick, now=now)', block)
        self.assertIn('raise', block)
        self.assertNotIn('state="SCHEDULE_FAILED"', block)

    def test_tick_schedules_next_before_selecting_or_running_source(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        start = source.index('async def _process_incremental_tick_payload')
        end = source.index('async def _start_intraday_chain_after_deep', start)
        block = source[start:end]
        next_enqueue = block.index('await _enqueue_incremental_tick(next_tick, now=now)')
        selection = block.index('choose_due_incremental_source(cache, now=now)')
        source_enqueue = block.index('await _enqueue_incremental_source(decision.source_id, observed_at=now)')
        self.assertLess(next_enqueue, selection)
        self.assertLess(selection, source_enqueue)

    def test_intraday_attempt_is_marked_only_after_source_queue_accepts(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        start = source.index('async def _process_incremental_tick_payload')
        end = source.index('async def _start_intraday_chain_after_deep', start)
        block = source[start:end]
        source_enqueue = block.index('await _enqueue_incremental_source(decision.source_id, observed_at=now)')
        attempt_mark = block.index('mark_incremental_source_attempt(cache, decision.source_id, now=now)')
        self.assertLess(source_enqueue, attempt_mark)

    def test_tick_payload_never_contains_customer_private_context(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        tick_start = source.index('async def _enqueue_incremental_tick')
        tick_end = source.index('async def _enqueue_incremental_source', tick_start)
        block = source[tick_start:tick_end]
        for forbidden in ('user_id', 'organization_id', 'local_scope', 'hospital_relationships', 'product_capabilities'):
            self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
