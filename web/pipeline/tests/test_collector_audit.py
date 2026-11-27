from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))
from collector_audit import emit_collector_audit  # noqa: E402


class CollectorAuditTests(unittest.TestCase):
    def test_preview_never_sends_audit(self):
        with patch.dict(os.environ, {
            "VERCEL_ENV": "preview",
            "VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "synthetic-test-token-" * 2,
        }), patch("collector_audit.urlopen") as opener:
            self.assertFalse(emit_collector_audit(
                cycle_id="prod:2026-11-27", cycle_as_of="2026-11-27T00:27:29Z",
                stage="trigger", status="COMPLETED", outcome="QUEUED"))
            opener.assert_not_called()

    def test_production_uses_authenticated_patch_not_query(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = b'{}'
        token = "synthetic-secret-for-test-only-" * 2
        with patch.dict(os.environ, {
            "VERCEL_ENV": "production",
            "VERIFIED_SNAPSHOT_PUBLISH_TOKEN": token,
        }), patch("collector_audit.urlopen", return_value=response) as opener:
            self.assertTrue(emit_collector_audit(
                cycle_id="prod:2026-11-27",
                cycle_as_of="2026-11-27T00:27:29Z",
                stage="ccgp", status="COMPLETED",
                outcome="SKIPPED", error_code="SOURCE_UNAVAILABLE",
                new_verified_record_count=0))
            request = opener.call_args.args[0]
            self.assertEqual(request.get_method(), "PATCH")
            self.assertTrue(request.full_url.endswith("/api/public-snapshot"))
            self.assertNotIn(token, request.full_url)
            self.assertEqual(request.get_header("Authorization"), "Bearer " + token)
            self.assertNotIn(token.encode(), request.data)

    def test_error_does_not_block_or_log_secret(self):
        token = "synthetic-secret-for-test-only-" * 2
        with patch.dict(os.environ, {
            "VERCEL_ENV": "production",
            "VERIFIED_SNAPSHOT_PUBLISH_TOKEN": token,
        }), patch("collector_audit.urlopen", side_effect=RuntimeError(token)), \
             patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertFalse(emit_collector_audit(
                cycle_id="prod:2026-11-27",
                cycle_as_of="2026-11-27T00:27:29Z",
                stage="publish", status="FAILED", outcome="WORKER_EXCEPTION"))
            self.assertNotIn(token, stdout.getvalue())
            self.assertIn("COLLECTOR_AUDIT_WRITE_FAILED", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
