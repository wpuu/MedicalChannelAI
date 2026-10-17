from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
HEALTH_PATH = WEB_ROOT / 'api' / 'pipeline-health.py'


class PipelineHealthCronSecretTests(unittest.TestCase):
    def test_production_requires_cron_secret_but_preview_does_not(self) -> None:
        source = HEALTH_PATH.read_text(encoding='utf-8')
        self.assertIn("os.environ.get('CRON_SECRET')", source)
        self.assertIn("os.environ.get('VERCEL_ENV')", source)
        self.assertIn("== 'production'", source)
        self.assertIn('cron_secret_configured', source)
        self.assertIn('cron_secret_required', source)
        self.assertIn('cron_ready = cron_secret_configured or not production_mode', source)

    def test_production_health_requires_recent_verified_snapshot(self) -> None:
        source = HEALTH_PATH.read_text(encoding='utf-8')
        self.assertIn('MAX_VERIFIED_SNAPSHOT_AGE_SECONDS = 30 * 60 * 60', source)
        self.assertIn('MAX_FUTURE_SNAPSHOT_SKEW_SECONDS = 15 * 60', source)
        self.assertIn('LATEST_RUNTIME_SNAPSHOT_KEY', source)
        self.assertIn("BUNDLED_SNAPSHOT_PATH = PROJECT_ROOT / 'public' / 'data' / 'today-actions.public.json'", source)
        self.assertIn("def _durable_status_snapshot(now: datetime)", source)
        self.assertIn("if database_configured:", source)
        self.assertIn("DATABASE_STATUS_DEGRADED", source)
        self.assertIn("COLLECTION_STATE_UNKNOWN", source)
        self.assertIn("def _snapshot_freshness(value: Any, now: datetime)", source)
        self.assertIn("snapshot.get('source_mode') != 'DATABASE'", source)
        self.assertIn("snapshot.get('freshness') != 'FRESH'", source)
        self.assertIn("os.environ.get('DATABASE_URL')", source)
        self.assertIn("os.environ.get('POSTGRES_URL')", source)
        self.assertIn("urlopen(request, timeout=5)", source)
        self.assertIn('snapshot_ready = snapshot_fresh or not production_mode', source)
        self.assertIn(
            'ready = bool(_IMPORT_OK and _DATA_OK and cache_ok and cron_ready and snapshot_ready)',
            source,
        )
        self.assertIn('verified_snapshot_fresh', source)
        self.assertIn('verified_snapshot_age_seconds', source)
        self.assertIn('verified_snapshot_max_age_seconds', source)
        self.assertIn('sys.path.insert(0, str(PROJECT_ROOT))', source)

    def test_health_never_exposes_cron_secret_value(self) -> None:
        source = HEALTH_PATH.read_text(encoding='utf-8')
        self.assertNotIn("'cron_secret':", source)
        self.assertNotIn('"cron_secret":', source)


if __name__ == '__main__':
    unittest.main()
