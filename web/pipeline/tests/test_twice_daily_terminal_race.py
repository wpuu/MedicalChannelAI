from __future__ import annotations

import asyncio
import threading
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from test_twice_daily_search import (
    ACTIVE_CYCLE_KEY, META_KEY, MORNING, NOON, MemoryCache,
    SCHEDULE_VERSION, queue, scheduled_cycle, start,
)
from collector_namespace import active_cycle_id


class TwiceDailyTerminalRaceTests(unittest.TestCase):
    def _terminal_and_noon_start(self):
        """Run the real Queue terminal and Cron entry with controlled overlap."""
        morning_id, morning_anchor = scheduled_cycle(MORNING, 'morning')
        noon_id, _ = scheduled_cycle(NOON, 'noon')
        release_read_or_done = threading.Event()
        noon_started = threading.Event()
        errors = []

        class InterleavedCache(MemoryCache):
            terminal_ready = False

            def get(self, key):
                value = super().get(key)
                if (key == ACTIVE_CYCLE_KEY and self.terminal_ready
                        and threading.current_thread().name == 'morning-terminal'):
                    # Snapshot the old lease before allowing the noon entry.
                    # The legacy compare-delete resumes with this stale read.
                    release_read_or_done.set()
                    if not noon_started.wait(5):
                        raise AssertionError('noon entry did not finish')
                return value

        cache = InterleavedCache()
        cache.set(ACTIVE_CYCLE_KEY, {
            'cycle_id': morning_id, 'cycle_as_of': morning_anchor.isoformat(),
        })
        cache.set(META_KEY, {
            'local_date': '2026-10-03', 'cycle_id': morning_id,
            'cycle_as_of': morning_anchor.isoformat(),
            'stages': {'publish': {'status': 'RUNNING'}},
        })

        def finish_publish(*_args, **_kwargs):
            cache.get(META_KEY)['stages']['publish'] = {
                'status': 'COMPLETED', 'terminal': True,
            }
            return 200, {'action': 'COMPLETED'}

        def clear_staging(_cache):
            cache.terminal_ready = True

        payload = {
            'schema_version': '0.1', 'schedule_version': SCHEDULE_VERSION,
            'stage': 'publish', 'cycle_id': morning_id,
            'cycle_as_of': morning_anchor.isoformat(),
        }

        def finish_morning():
            try:
                asyncio.run(queue.process_collector_payload(payload))
            except BaseException as exc:
                errors.append(exc)
            finally:
                # A safe no-delete terminal finishes without reading ACTIVE.
                release_read_or_done.set()

        send = AsyncMock(return_value='offline-noon-message')
        with patch.object(queue, 'RuntimeCache', return_value=cache), \
             patch.object(start, 'RuntimeCache', return_value=cache), \
             patch.object(queue.runtime, 'run_stage', side_effect=finish_publish), \
             patch.object(queue.incremental_runtime, 'clear_incremental_pending', side_effect=clear_staging), \
             patch.object(start, 'send', send), \
             patch.object(start, 'datetime') as entry_clock, \
             patch.object(queue, 'datetime') as queue_clock:
            entry_clock.now.return_value = NOON
            entry_clock.fromisoformat.side_effect = datetime.fromisoformat
            queue_clock.now.return_value = NOON
            queue_clock.fromisoformat.side_effect = datetime.fromisoformat
            worker = threading.Thread(target=finish_morning, name='morning-terminal')
            worker.start()
            try:
                self.assertTrue(release_read_or_done.wait(5), 'terminal stalled')
                result = asyncio.run(start._enqueue_start('OFFLINE', 'noon'))
                self.assertEqual(result[2], noon_id)
                self.assertEqual(active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)), noon_id)
            finally:
                noon_started.set()
                worker.join(5)
            self.assertFalse(worker.is_alive(), 'terminal worker did not stop')
            self.assertEqual(errors, [])
            send.assert_awaited_once()
            self.assertEqual(send.await_args.args[1]['cycle_id'], noon_id)
        return active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)), noon_id

    def test_old_terminal_cannot_remove_new_noon_lease(self):
        actual, expected = self._terminal_and_noon_start()
        self.assertEqual(actual, expected)

    def test_harness_reproduces_legacy_compare_delete_loss(self):
        def legacy_release(cycle_id):
            cache = queue.RuntimeCache()
            if active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)) == cycle_id:
                cache.delete(ACTIVE_CYCLE_KEY)

        with patch.object(queue, '_release_active_cycle_if_owned', side_effect=legacy_release):
            actual, _ = self._terminal_and_noon_start()
        self.assertIsNone(actual)
