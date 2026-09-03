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

    def test_smoke_proves_target_hospital_does_not_inflate_relationship_score(self):
        source = (WEB_ROOT / 'scripts' / 'pilot-preview-smoke.mjs').read_text(encoding='utf-8')
        self.assertIn("hospital_relationships: []", source)
        self.assertIn("TARGET_ONLY_PROFILE_RELATIONSHIP_NOT_EMPTY", source)
        self.assertIn("TARGET_HOSPITAL_INFLATED_RELATIONSHIP_POINTS", source)
        self.assertIn("Number(findComponent(targetOnlyPersonalized, 'RELATIONSHIP')?.points || 0) === 0", source)
        self.assertLess(
            source.index("TARGET_HOSPITAL_INFLATED_RELATIONSHIP_POINTS"),
            source.index("HOSPITAL_RELATIONSHIP_SAVE_FAILED"),
        )
        self.assertIn("PERSONALIZED_RELATIONSHIP_POINTS_MISSING", source)

    def test_smoke_persists_reminder_across_idempotency_session_and_export(self):
        source = (WEB_ROOT / 'scripts' / 'pilot-preview-smoke.mjs').read_text(encoding='utf-8')
        self.assertIn("remind_at: remindAt", source)
        self.assertIn("FOLLOWUP_REMINDER_SAVE_FAILED", source)
        self.assertIn("FOLLOWUP_REMINDER_IDEMPOTENCY_FAILED", source)
        self.assertIn("FOLLOWED_REMINDER_MISSING", source)
        self.assertIn("CROSS_SESSION_REMINDER_PERSISTENCE_FAILED", source)
        self.assertIn("ACCOUNT_EXPORT_REMINDER_MISSING", source)

    def test_smoke_proves_deleted_account_credentials_stop_working(self):
        source = (WEB_ROOT / 'scripts' / 'pilot-preview-smoke.mjs').read_text(encoding='utf-8')
        self.assertIn("const deletedLogin = await request('/api/auth/login'", source)
        self.assertIn("expected: [401]", source)
        self.assertIn("INVALID_CREDENTIALS", source)
        self.assertIn("DELETED_ACCOUNT_LOGIN_SUCCEEDED", source)
        self.assertLess(
            source.index("ACCOUNT_DELETE_FAILED"),
            source.index("DELETED_ACCOUNT_LOGIN_SUCCEEDED"),
        )

    def test_smoke_remains_destructive_safe_for_production(self):
        source = (WEB_ROOT / 'scripts' / 'pilot-preview-smoke.mjs').read_text(encoding='utf-8')
        self.assertIn("PILOT_SMOKE_PRODUCTION_FORBIDDEN", source)
        self.assertIn("PILOT_SMOKE_PREVIEW_HOST_REQUIRED", source)
        self.assertIn("await cleanup()", source)


if __name__ == '__main__':
    unittest.main()
