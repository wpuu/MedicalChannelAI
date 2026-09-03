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

    def test_auth_responses_include_frontend_required_identity_fields(self):
        source = (WEB_ROOT / 'api' / 'auth.js').read_text(encoding='utf-8')
        register_source = source[source.index('async function register'):source.index('async function login')]
        login_source = source[source.index('async function login'):source.index('async function logout')]
        me_source = source[source.index('async function me'):source.index('async function requireUser')]
        frontend = (WEB_ROOT / 'src' / 'services' / 'apiConfig.ts').read_text(encoding='utf-8')

        self.assertIn('username: user.username', register_source)
        self.assertIn('display_name: user.display_name ?? null', register_source)
        self.assertIn('role: user.role', register_source)
        self.assertIn('local_scope: localScope(user.id)', register_source)
        self.assertIn(
            'SELECT id, username_display, display_name, password_salt, password_hash, role',
            login_source,
        )
        self.assertIn('username: user.username_display', login_source)
        self.assertIn('display_name: user.display_name', login_source)
        self.assertIn('local_scope: localScope(user.id)', login_source)
        self.assertIn('local_scope: localScope(user.id)', me_source)
        self.assertIn(
            "!(row.display_name === null || typeof row.display_name === 'string')",
            frontend,
        )
        self.assertIn("typeof row.local_scope !== 'string'", frontend)
        self.assertIn('!/^[0-9a-f]{32}$/.test(row.local_scope)', frontend)

    def test_local_scope_is_opaque_stable_account_identity_not_username(self):
        source = (WEB_ROOT / 'api' / 'auth.js').read_text(encoding='utf-8')
        self.assertIn('function localScope(userId)', source)
        self.assertIn('sha256(`pilot-local-scope:v1:${userId}`).slice(0, 32)', source)
        self.assertEqual(source.count('local_scope: localScope(user.id)'), 3)
        export_source = source[source.index('async function exportAccount'):source.index('async function deleteAccount')]
        self.assertNotIn('local_scope', export_source)

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
