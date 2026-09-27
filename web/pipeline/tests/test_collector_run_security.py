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

    def test_cache_migration_recovery_cycle_is_narrow_and_deterministic(self) -> None:
        source = COLLECTOR_RUN.read_text(encoding="utf-8")
        self.assertIn("def _recovery_cycle_id(cache: RuntimeCache, local_date: str)", source)
        self.assertIn('publish.get("status") != "FAILED"', source)
        self.assertIn('startswith("COLLECTOR_CANONICAL_STATE_INCOMPLETE")', source)
        self.assertIn('return f"prod:{local_date}:recovery-v3"', source)
        self.assertNotIn("uuid", source.lower())

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
        self.assertIn('cycle_id = _recovery_cycle_id(cache, local_date) or f"prod:{local_date}"', source)


if __name__ == "__main__":
    unittest.main()
