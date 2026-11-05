from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))
from collector_oidc import preview_oidc_token


class CollectorOidcTests(unittest.TestCase):
    def sdk(self, token="request-context-test-token"):
        sdk = types.ModuleType("vercel.oidc")
        sdk.get_vercel_oidc_token_sync = Mock(return_value=token)
        sdk.get_vercel_oidc_token = Mock(side_effect=AssertionError("network-capable refresh entrypoint must not run"))
        return sdk

    def test_sdk_request_context_is_used_without_environment_token(self):
        sdk = self.sdk()
        with patch.dict(os.environ, {"VERCEL_ENV": "preview"}, clear=True), patch.dict(sys.modules, {"vercel.oidc": sdk}):
            self.assertEqual(preview_oidc_token(), "request-context-test-token")
        sdk.get_vercel_oidc_token_sync.assert_called_once_with()
        sdk.get_vercel_oidc_token.assert_not_called()

    def test_configured_token_file_is_resolved_by_sdk_not_read_by_application(self):
        sdk = self.sdk("sdk-file-test-token")
        with patch.dict(os.environ, {"VERCEL_ENV": "preview", "VERCEL_OIDC_TOKEN_FILE": "/runtime/credential-file"}, clear=True), \
                patch.dict(sys.modules, {"vercel.oidc": sdk}), patch.object(Path, "read_text") as read:
            self.assertEqual(preview_oidc_token(), "sdk-file-test-token")
        read.assert_not_called()
        sdk.get_vercel_oidc_token_sync.assert_called_once_with()

    def test_sdk_current_context_takes_precedence_over_stale_environment(self):
        sdk = self.sdk("fresh-context-test-token")
        with patch.dict(os.environ, {"VERCEL_ENV": "preview", "VERCEL_OIDC_TOKEN": "stale-env-test-token"}, clear=True), \
                patch.dict(sys.modules, {"vercel.oidc": sdk}):
            self.assertEqual(preview_oidc_token(), "fresh-context-test-token")

    def test_tokens_are_not_cached_across_requests_by_application(self):
        sdk = self.sdk()
        sdk.get_vercel_oidc_token_sync.side_effect = ["rotated-test-token-1", "rotated-test-token-2"]
        with patch.dict(os.environ, {"VERCEL_ENV": "preview"}, clear=True), patch.dict(sys.modules, {"vercel.oidc": sdk}):
            self.assertEqual(preview_oidc_token(), "rotated-test-token-1")
            self.assertEqual(preview_oidc_token(), "rotated-test-token-2")

    def test_production_never_reads_sdk_or_token_file(self):
        sdk = self.sdk()
        with patch.dict(os.environ, {"VERCEL_ENV": "production", "VERCEL_OIDC_TOKEN_FILE": "/runtime/credential-file"}, clear=True), \
                patch.dict(sys.modules, {"vercel.oidc": sdk}), patch.object(Path, "read_text") as read:
            self.assertIsNone(preview_oidc_token())
        sdk.get_vercel_oidc_token_sync.assert_not_called()
        read.assert_not_called()

    def test_sdk_failure_logs_only_safe_reason_and_never_exception_or_token(self):
        sdk = self.sdk()
        sdk.get_vercel_oidc_token_sync.side_effect = RuntimeError("credential-sensitive-test-value")
        with patch.dict(os.environ, {"VERCEL_ENV": "preview"}, clear=True), patch.dict(sys.modules, {"vercel.oidc": sdk}), \
                self.assertLogs("collector_oidc", level="WARNING") as logged:
            self.assertIsNone(preview_oidc_token())
        self.assertIn("SDK_TOKEN_UNAVAILABLE", " ".join(logged.output))
        self.assertNotIn("credential-sensitive-test-value", " ".join(logged.output))

    def test_standalone_environment_token_remains_supported_without_sdk(self):
        with patch.dict(os.environ, {"VERCEL_ENV": "preview", "VERCEL_OIDC_TOKEN": "local-env-test-token"}, clear=True), \
                patch.dict(sys.modules, {"vercel.oidc": None}):
            self.assertEqual(preview_oidc_token(), "local-env-test-token")


if __name__ == "__main__":
    unittest.main()
