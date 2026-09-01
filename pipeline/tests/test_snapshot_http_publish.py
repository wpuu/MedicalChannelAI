from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / "scripts" / "publish_snapshot_http.py"

spec = importlib.util.spec_from_file_location("publish_snapshot_http", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("SNAPSHOT_PUBLISH_IMPORT_FAILED")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class SnapshotHttpPublishTests(unittest.TestCase):
    def test_publish_url_requires_https(self) -> None:
        with self.assertRaisesRegex(
            publisher.SnapshotPublishError,
            "SNAPSHOT_PUBLISH_URL_MUST_BE_HTTPS",
        ):
            publisher.validate_publish_url("http://example.com/snapshot.json")

    def test_publish_url_rejects_embedded_userinfo(self) -> None:
        with self.assertRaisesRegex(
            publisher.SnapshotPublishError,
            "SNAPSHOT_PUBLISH_URL_USERINFO_REJECTED",
        ):
            publisher.validate_publish_url("https://user:pass@example.com/snapshot.json")

    def test_payload_requires_public_snapshot_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps({"schema_version": "0.1"}), encoding="utf-8")
            with self.assertRaisesRegex(
                publisher.SnapshotPublishError,
                "SNAPSHOT_PUBLISH_SCHEMA_INVALID",
            ):
                publisher.load_snapshot_payload(path)

    def test_valid_payload_and_request_include_digest_without_leaking_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "mode": "TODAY_ACTIONS",
                        "snapshot_as_of": "2026-08-31T20:00:00+08:00",
                        "cards": [],
                    }
                ),
                encoding="utf-8",
            )
            payload = publisher.load_snapshot_payload(path)
            request = publisher.build_request(
                url="https://storage.example/snapshot.json",
                payload=payload,
                method="PUT",
                bearer_token="secret-token-value",
            )
            self.assertEqual(request.get_method(), "PUT")
            self.assertEqual(request.get_header("Content-type"), "application/json; charset=utf-8")
            self.assertEqual(request.get_header("Authorization"), "Bearer secret-token-value")
            self.assertRegex(request.get_header("X-content-sha256"), r"^[0-9a-f]{64}$")
            self.assertNotIn("secret-token-value", request.full_url)

    def test_method_is_restricted_to_put_or_post(self) -> None:
        with self.assertRaisesRegex(
            publisher.SnapshotPublishError,
            "SNAPSHOT_PUBLISH_METHOD_REJECTED",
        ):
            publisher.build_request(
                url="https://storage.example/snapshot.json",
                payload=b"{}",
                method="DELETE",
                bearer_token=None,
            )


if __name__ == "__main__":
    unittest.main()
