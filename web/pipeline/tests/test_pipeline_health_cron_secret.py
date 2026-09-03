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
        self.assertIn('cron_ready = cron_secret_configured or not cron_secret_required', source)
        self.assertIn('ready = bool(_IMPORT_OK and _DATA_OK and cache_ok and cron_ready)', source)

    def test_health_never_exposes_cron_secret_value(self) -> None:
        source = HEALTH_PATH.read_text(encoding='utf-8')
        self.assertNotIn("'cron_secret':", source)
        self.assertNotIn('"cron_secret":', source)


if __name__ == '__main__':
    unittest.main()
