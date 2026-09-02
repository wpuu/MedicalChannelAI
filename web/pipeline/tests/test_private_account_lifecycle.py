import json
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class PrivateAccountLifecycleTests(unittest.TestCase):
    def test_account_routes_share_existing_auth_function(self):
        config = json.loads((WEB_ROOT / 'vercel.json').read_text(encoding='utf-8'))
        rewrites = {item['source']: item['destination'] for item in config['rewrites']}
        self.assertEqual(rewrites['/api/account/export'], '/api/auth?route=export')
        self.assertEqual(rewrites['/api/account/delete'], '/api/auth?route=delete')

    def test_export_does_not_select_password_or_session_secret(self):
        source = (WEB_ROOT / 'api' / 'auth.js').read_text(encoding='utf-8')
        export_start = source.index('async function exportAccount')
        delete_start = source.index('async function deleteAccount')
        export_source = source[export_start:delete_start]
        self.assertNotIn('password_hash', export_source)
        self.assertNotIn('password_salt', export_source)
        self.assertNotIn('token_hash', export_source)
        self.assertNotIn('private_sessions', export_source)
        self.assertIn('private_product_capabilities', export_source)
        self.assertIn('private_hospital_relationships', export_source)
        self.assertIn('private_followups', export_source)
        self.assertIn('private_recommendation_feedback', export_source)

    def test_account_deletion_requires_current_password(self):
        source = (WEB_ROOT / 'api' / 'auth.js').read_text(encoding='utf-8')
        delete_source = source[source.index('async function deleteAccount'):]
        self.assertIn('validatePassword(body?.password)', delete_source)
        self.assertIn('verifyPassword(password, account.password_salt, account.password_hash)', delete_source)
        self.assertIn("PASSWORD_CONFIRMATION_FAILED", delete_source)
        self.assertIn('DELETE FROM private_users WHERE id = ${user.id}', delete_source)
        self.assertIn('clearSessionCookie(request, response)', delete_source)

    def test_consumed_invite_cannot_be_reused_after_user_is_deleted(self):
        source = (WEB_ROOT / 'api' / '_auth.js').read_text(encoding='utf-8')
        self.assertIn('SELECT code_hash, organization_id, expires_at, used_by, used_at', source)
        self.assertIn('invitation.used_at || invitation.used_by || inviteExpired(invitation)', source)
        self.assertIn('AND used_at IS NULL', source)


if __name__ == '__main__':
    unittest.main()
