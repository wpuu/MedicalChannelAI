from __future__ import annotations

import importlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))
PRODUCTION_URL = "https://medicalchannelai.vercel.app/api/public-snapshot"
PREVIEW_HOST = "medicalchannelai-p0-abc123-team.vercel.app"


class CollectorPublishEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        functions = types.ModuleType("vercel.functions")
        functions.RuntimeCache = object
        modules = patch.dict(sys.modules, {"vercel": types.ModuleType("vercel"), "vercel.functions": functions})
        modules.start()
        self.addCleanup(modules.stop)
        sys.modules.pop("collector_runtime", None)
        self.runtime = importlib.import_module("collector_runtime")
        self.snapshot = {"snapshot_as_of": "2026-11-05T00:00:00Z", "cards": [], "opportunity_pool": []}
        self.environment = {
            "VERCEL_ENV": "preview", "VERCEL_URL": PREVIEW_HOST,
            "VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "preview-test-publisher-token-0001",
        }

    def publish_request(self, environment):
        snapshot = self.snapshot

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return json.dumps({"ok": True, "snapshot_as_of": snapshot["snapshot_as_of"], "opportunity_pool_count": 0}).encode()

        with patch.dict(os.environ, environment, clear=True), patch.object(self.runtime, "urlopen", return_value=Response()) as send:
            result = self.runtime._persist_verified_snapshot_durably(snapshot)
        self.assertEqual(result["opportunity_pool_count"], 0)
        send.assert_called_once()
        return send.call_args.args[0]

    def test_preview_put_uses_only_exact_current_deployment_even_with_production_override(self) -> None:
        request = self.publish_request({
            **self.environment,
            "VERIFIED_SNAPSHOT_PUBLISH_URL": PRODUCTION_URL,
            "DURABLE_PUBLISH_URL": "https://external.example/api/public-snapshot",
            "VERCEL_PROJECT_PRODUCTION_URL": "medicalchannelai.vercel.app",
        })
        self.assertEqual(request.full_url, f"https://{PREVIEW_HOST}/api/public-snapshot")
        self.assertEqual(request.method, "PUT")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.environment['VERIFIED_SNAPSHOT_PUBLISH_TOKEN']}")

    def test_runtime_oidc_is_sent_only_to_validated_preview_self_host(self) -> None:
        request = self.publish_request({
            **self.environment, "VERCEL_OIDC_TOKEN": "test-only-runtime-oidc",
            "VERIFIED_SNAPSHOT_PUBLISH_URL": PRODUCTION_URL,
            "DURABLE_PUBLISH_URL": "https://external.example/api/public-snapshot",
        })
        self.assertEqual(request.full_url, f"https://{PREVIEW_HOST}/api/public-snapshot")
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["x-vercel-trusted-oidc-idp-token"], "test-only-runtime-oidc")
        self.assertEqual(headers["authorization"], f"Bearer {self.environment['VERIFIED_SNAPSHOT_PUBLISH_TOKEN']}")

    def test_missing_runtime_oidc_does_not_fabricate_protection_authentication(self) -> None:
        request = self.publish_request(self.environment)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertNotIn("x-vercel-trusted-oidc-idp-token", headers)
        self.assertNotIn("x-vercel-protection-bypass", headers)
        with patch.dict(os.environ, self.environment, clear=True), patch.object(
            self.runtime, "urlopen", side_effect=HTTPError(request.full_url, 401, "protected", {}, None),
        ):
            with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "DURABLE_SNAPSHOT_PUBLISH_HTTP_401"):
                self.runtime._persist_verified_snapshot_durably(self.snapshot)

    def test_preview_missing_deployment_host_fails_before_any_request(self) -> None:
        environment = {**self.environment, "VERCEL_URL": "", "VERCEL_PROJECT_PRODUCTION_URL": "medicalchannelai.vercel.app"}
        with patch.dict(os.environ, environment, clear=True), patch.object(self.runtime, "urlopen") as send:
            with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "DURABLE_SNAPSHOT_PREVIEW_HOST_MISSING"):
                self.runtime._persist_verified_snapshot_durably(self.snapshot)
        send.assert_not_called()

    def test_preview_cannot_target_production_alias_even_with_publisher_token(self) -> None:
        with patch.dict(os.environ, {**self.environment, "VERCEL_URL": "medicalchannelai.vercel.app"}, clear=True), patch.object(self.runtime, "urlopen") as send:
            with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "DURABLE_SNAPSHOT_PREVIEW_PRODUCTION_HOST_REJECTED"):
                self.runtime._persist_verified_snapshot_durably(self.snapshot)
        send.assert_not_called()

    def test_preview_rejects_external_host_scheme_port_userinfo_and_path_injection(self) -> None:
        invalid_hosts = (
            "medicalai.qd.je", "external.example", "evil.vercel.app.external.example",
            "https://safe.vercel.app", "http://safe.vercel.app", "safe.vercel.app:443",
            "safe.vercel.app@medicalchannelai.vercel.app", "user:password@safe.vercel.app",
            "safe.vercel.app/api/public-snapshot", "safe.vercel.app/../production",
            "safe.vercel.app?upstream=production", "safe.vercel.app#production",
            "safe.vercel.app\\@medicalchannelai.vercel.app", "safe.vercel.app%2fproduction",
            "-unsafe.vercel.app", "unsafe-.vercel.app", "sub.safe.vercel.app",
        )
        for host in invalid_hosts:
            with self.subTest(host=host), patch.dict(os.environ, {**self.environment, "VERCEL_URL": host, "VERCEL_OIDC_TOKEN": "test-only-runtime-oidc"}, clear=True), patch.object(self.runtime, "urlopen") as send:
                with self.assertRaisesRegex(self.runtime.CollectorStageBlocked, "DURABLE_SNAPSHOT_PREVIEW_HOST_INVALID"):
                    self.runtime._persist_verified_snapshot_durably(self.snapshot)
                send.assert_not_called()

    def test_production_keeps_existing_canonical_url(self) -> None:
        request = self.publish_request({
            **self.environment, "VERCEL_ENV": "production", "VERCEL_OIDC_TOKEN": "test-only-runtime-oidc",
            "VERIFIED_SNAPSHOT_PUBLISH_URL": "https://external.example",
        })
        self.assertEqual(request.full_url, PRODUCTION_URL)
        self.assertNotIn("x-vercel-trusted-oidc-idp-token", {key.lower() for key, _ in request.header_items()})

    def test_legacy_local_environment_keeps_existing_default(self) -> None:
        request = self.publish_request({"VERIFIED_SNAPSHOT_PUBLISH_TOKEN": self.environment["VERIFIED_SNAPSHOT_PUBLISH_TOKEN"]})
        self.assertEqual(request.full_url, PRODUCTION_URL)


if __name__ == "__main__":
    unittest.main()
