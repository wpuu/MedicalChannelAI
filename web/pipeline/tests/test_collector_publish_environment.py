from __future__ import annotations

import importlib
import io
import json
import os
import socket
import urllib.request
from urllib.error import URLError
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
        for owner, name in ((socket.socket, "connect"), (socket, "getaddrinfo"), (urllib.request, "build_opener")):
            blocker = patch.object(owner, name, side_effect=AssertionError("NETWORK_FORBIDDEN"))
            blocker.start()
            self.addCleanup(blocker.stop)
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
                return json.dumps({"ok": True, "durable_committed": True, "cache_status": "UPDATED", "snapshot_as_of": snapshot["snapshot_as_of"], "opportunity_pool_count": 0}).encode()

        with patch.dict(os.environ, environment, clear=True), patch.object(self.runtime, "urlopen", return_value=Response()) as send:
            result = self.runtime._persist_verified_snapshot_durably(snapshot)
        self.assertEqual(result["opportunity_pool_count"], 0)
        send.assert_called_once()
        return send.call_args.args[0]

    def budget_put_case(self, mode="success", *, elapsed=0, parent_work=210, changes=None):
        tick, calls = [float(elapsed)], []
        budget = self.runtime.CliBudget(lambda: tick[0], lambda d: None, total_seconds=270, work_seconds=parent_work, started_at=0)
        receipt = self.runtime._new_publish_receipt()
        ack = {"ok": True, "durable_committed": True, "cache_status": "UPDATED",
               "snapshot_as_of": self.snapshot["snapshot_as_of"], "opportunity_pool_count": 0}
        ack.update(changes or {})
        if mode == "missing_commit": ack.pop("durable_committed")
        body = json.dumps(ack).encode() if mode != "bad_json" else b"not-json"
        class Response(io.BytesIO):
            status = 500 if mode == "http_error" else 200
            def read(self):
                if mode == "late_work": tick[0] = 210
                if mode == "late_total": tick[0] = 270
                return super().read()
        def send(request, **kwargs):
            calls.append((request, kwargs))
            if mode == "transport_error": raise URLError("SYNTHETIC_DISCONNECT")
            return Response(body)
        original_json = self.runtime.json.dumps
        def dump(*args, **kwargs):
            value = original_json(*args, **kwargs)
            if mode == "serialize_late": tick[0] = 210
            return value
        result, error = None, None
        with patch.dict(os.environ, self.environment, clear=True), patch.object(self.runtime, "preview_oidc_token", return_value=None), patch.object(
            self.runtime, "urlopen", side_effect=send), patch.object(self.runtime.json, "dumps", side_effect=dump):
            try:
                result = self.runtime._persist_verified_snapshot_durably(self.snapshot, budget=budget, receipt=receipt)
            except Exception as exc:
                error = type(exc).__name__
                receipt = exc.diagnostics["publish_receipt"]
        return {"result": result, "error": error, "receipt": receipt, "calls": calls, "budget": budget}

    def test_publish_budget_expired_or_serialization_late_never_sends_put(self):
        for mode, elapsed in (("success", 210), ("success", 209), ("serialize_late", 0)):
            with self.subTest(mode=mode, elapsed=elapsed):
                c = self.budget_put_case(mode, elapsed=elapsed)
                self.assertFalse(c["calls"])
                self.assertEqual(c["receipt"]["publication_outcome"], "NOT_ATTEMPTED")

    def test_publish_budget_ack_requires_strict_existing_fields(self):
        for changes in ({"durable_committed": False}, {"durable_committed": 1}, {"durable_committed": "true"},
                        {"ok": 1}, {"snapshot_as_of": "wrong"}, {"snapshot_as_of": None},
                        {"opportunity_pool_count": False}, {"opportunity_pool_count": "0"}):
            with self.subTest(changes=changes):
                c = self.budget_put_case(changes=changes)
                self.assertIsNotNone(c["error"])
                self.assertEqual(len(c["calls"]), 1)
                self.assertEqual(c["receipt"]["publication_outcome"], "UNKNOWN")
        c = self.budget_put_case("missing_commit")
        self.assertEqual(c["receipt"]["publication_outcome"], "UNKNOWN")

    def test_publish_budget_late_valid_ack_stays_confirmed(self):
        for mode in ("late_work", "late_total"):
            with self.subTest(mode=mode):
                c = self.budget_put_case(mode)
                self.assertIsNone(c["error"])
                self.assertEqual(c["receipt"]["publication_outcome"], "CONFIRMED")
                self.assertTrue(c["receipt"]["ack_after_work_deadline"])
                self.assertTrue(c["budget"].work_complete)

    def test_publish_budget_parent180_uses210_and_does_not_reset_clock(self):
        c = self.budget_put_case(elapsed=195, parent_work=180)
        self.assertIsNone(c["error"])
        self.assertEqual(c["calls"][0][1]["timeout"], 14)
        self.assertEqual(c["budget"].started, 0)
        self.assertEqual(c["budget"].work_seconds, 180)
        self.assertFalse(c["budget"].work_complete)
        c = self.budget_put_case()
        self.assertEqual(c["calls"][0][1]["timeout"], 30)

    def test_publish_budget_transport_http_and_json_failures_remain_unknown(self):
        for mode in ("transport_error", "http_error", "bad_json"):
            with self.subTest(mode=mode):
                c = self.budget_put_case(mode)
                self.assertEqual(len(c["calls"]), 1)
                self.assertEqual(c["receipt"]["publication_outcome"], "UNKNOWN")

    def test_publish_budget_malformed_copy_status_does_not_erase_durable_ack(self):
        for status in ({"invalid": True}, None, False):
            with self.subTest(status=status):
                c = self.budget_put_case(changes={"cache_status": status})
                self.assertIsNone(c["error"])
                self.assertEqual(c["receipt"]["publication_outcome"], "CONFIRMED")
                self.assertEqual(c["receipt"]["node_cache_status"], "UNKNOWN")

    def test_publish_receipt_is_never_added_to_http_snapshot(self):
        c = self.budget_put_case()
        self.assertEqual(json.loads(c["calls"][0][0].data), self.snapshot)
        self.assertNotIn("publish_receipt", self.snapshot)
        self.assertNotIn("budget", self.snapshot)

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

    def test_sdk_context_oidc_is_forwarded_even_without_environment_token(self) -> None:
        sdk = types.ModuleType("vercel.oidc")
        sdk.get_vercel_oidc_token_sync = lambda: "sdk-context-only-test-token"
        with patch.dict(sys.modules, {"vercel.oidc": sdk}):
            request = self.publish_request(self.environment)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["x-vercel-trusted-oidc-idp-token"], "sdk-context-only-test-token")
        self.assertEqual(request.full_url, f"https://{PREVIEW_HOST}/api/public-snapshot")

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

    def test_preview_protection_error_never_exposes_response_body_credentials(self) -> None:
        with patch.dict(os.environ, self.environment, clear=True), patch.object(
            self.runtime, "urlopen", side_effect=HTTPError(
                f"https://{PREVIEW_HOST}/api/public-snapshot", 403, "protected", {},
                io.BytesIO(b"credential-sensitive-test-value"),
            ),
        ):
            with self.assertRaises(self.runtime.CollectorStageBlocked) as caught:
                self.runtime._persist_verified_snapshot_durably(self.snapshot)
        self.assertIn("HTTP_403", str(caught.exception))
        self.assertNotIn("credential-sensitive-test-value", str(caught.exception))

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
