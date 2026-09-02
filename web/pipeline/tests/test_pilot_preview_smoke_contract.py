import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class PilotPreviewSmokeContractTests(unittest.TestCase):
    def test_smoke_covers_continuation_rewrite_without_live_ai(self):
        source = (WEB_ROOT / 'scripts' / 'pilot-preview-smoke.mjs').read_text(encoding='utf-8')
        self.assertIn("request('/api/ai/discover-continuation', { expected: [405] })", source)
        self.assertIn("CONTINUATION_REWRITE_INVALID", source)
        self.assertIn("METHOD_NOT_ALLOWED", source)

    def test_smoke_persists_target_hospital_across_session_and_export(self):
        source = (WEB_ROOT / 'scripts' / 'pilot-preview-smoke.mjs').read_text(encoding='utf-8')
        self.assertIn("target_hospitals: [{ hospital: targetHospital, department: null }]", source)
        self.assertIn("TARGET_HOSPITAL_SAVE_FAILED", source)
        self.assertIn("CROSS_SESSION_TARGET_HOSPITAL_PERSISTENCE_FAILED", source)
        self.assertIn("ACCOUNT_EXPORT_TARGET_HOSPITAL_MISSING", source)

    def test_smoke_persists_reminder_across_idempotency_session_and_export(self):
        source = (WEB_ROOT / 'scripts' / 'pilot-preview-smoke.mjs').read_text(encoding='utf-8')
        self.assertIn("remind_at: remindAt", source)
        self.assertIn("FOLLOWUP_REMINDER_SAVE_FAILED", source)
        self.assertIn("FOLLOWUP_REMINDER_IDEMPOTENCY_FAILED", source)
        self.assertIn("FOLLOWED_REMINDER_MISSING", source)
        self.assertIn("CROSS_SESSION_REMINDER_PERSISTENCE_FAILED", source)
        self.assertIn("ACCOUNT_EXPORT_REMINDER_MISSING", source)

    def test_smoke_remains_destructive_safe_for_production(self):
        source = (WEB_ROOT / 'scripts' / 'pilot-preview-smoke.mjs').read_text(encoding='utf-8')
        self.assertIn("PILOT_SMOKE_PRODUCTION_FORBIDDEN", source)
        self.assertIn("PILOT_SMOKE_PREVIEW_HOST_REQUIRED", source)
        self.assertIn("await cleanup()", source)


if __name__ == '__main__':
    unittest.main()
