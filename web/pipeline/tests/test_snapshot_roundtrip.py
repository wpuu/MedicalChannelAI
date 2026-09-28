from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / "scripts" / "verify_snapshot_roundtrip.py"

spec = importlib.util.spec_from_file_location("verify_snapshot_roundtrip", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("SNAPSHOT_ROUNDTRIP_IMPORT_FAILED")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def snapshot(*, as_of: str = "2026-08-31T20:00:00+08:00", ids: tuple[str, ...] = ("opp-1", "opp-2")) -> dict:
    cards = [{"opportunity_id": opportunity_id} for opportunity_id in ids]
    return {
        "schema_version": "0.1",
        "mode": "TODAY_ACTIONS",
        "snapshot_as_of": as_of,
        "cards": cards[:2],
        "card_count": min(2, len(cards)),
        "opportunity_pool": cards,
        "opportunity_pool_count": len(cards),
        "matched_count": len(cards),
    }


class SnapshotRoundTripTests(unittest.TestCase):
    def test_fresh_read_url_bypasses_cdn_cache_with_unique_token(self) -> None:
        first = verifier.fresh_read_url("https://example.com/api/public-snapshot?region=tj&fresh=old")
        second = verifier.fresh_read_url("https://example.com/api/public-snapshot?region=tj&fresh=old")
        self.assertTrue(first.startswith("https://example.com/api/public-snapshot?region=tj&fresh="))
        self.assertEqual(first.count("fresh="), 1)
        self.assertNotIn("fresh=old", first)
        self.assertNotEqual(first, second)

    def test_read_url_requires_https(self) -> None:
        with self.assertRaisesRegex(
            verifier.SnapshotRoundTripError,
            "SNAPSHOT_READ_URL_MUST_BE_HTTPS",
        ):
            verifier.validate_read_url("http://example.com/snapshot.json")

    def test_read_url_rejects_embedded_userinfo(self) -> None:
        with self.assertRaisesRegex(
            verifier.SnapshotRoundTripError,
            "SNAPSHOT_READ_URL_USERINFO_REJECTED",
        ):
            verifier.validate_read_url("https://user:pass@example.com/snapshot.json")

    def test_remote_json_must_match_public_snapshot_contract(self) -> None:
        with self.assertRaisesRegex(
            verifier.SnapshotRoundTripError,
            "SNAPSHOT_REMOTE_SCHEMA_INVALID",
        ):
            verifier._load_json_bytes(json.dumps({"schema_version": "0.1"}).encode(), source="REMOTE")

    def test_snapshot_as_of_mismatch_fails_closed(self) -> None:
        local = snapshot(as_of="2026-08-31T20:00:00+08:00")
        remote = snapshot(as_of="2026-08-31T20:01:00+08:00")
        with self.assertRaisesRegex(
            verifier.SnapshotRoundTripError,
            r"SNAPSHOT_ROUNDTRIP_MISMATCH:snapshot_as_of",
        ):
            verifier.compare_snapshots(local, remote)

    def test_top5_or_pool_id_mismatch_fails_closed(self) -> None:
        local = snapshot(ids=("opp-1", "opp-2", "opp-3"))
        remote = snapshot(ids=("opp-1", "opp-2", "opp-x"))
        with self.assertRaisesRegex(
            verifier.SnapshotRoundTripError,
            r"SNAPSHOT_ROUNDTRIP_MISMATCH:pool_ids",
        ):
            verifier.compare_snapshots(local, remote)

    def test_duplicate_opportunity_ids_are_rejected(self) -> None:
        bad = snapshot(ids=("opp-1", "opp-1"))
        with self.assertRaisesRegex(
            verifier.SnapshotRoundTripError,
            "SNAPSHOT_LOCAL_TOP5_DUPLICATE_ID",
        ):
            verifier.compare_snapshots(bad, bad)

    def test_verify_roundtrip_reports_byte_identical_for_same_payload(self) -> None:
        payload = json.dumps(snapshot(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_bytes(payload)
            remote = json.loads(payload.decode("utf-8"))
            with patch.object(
                verifier,
                "fetch_remote_snapshot",
                return_value=(payload, remote),
            ):
                result = verifier.verify_roundtrip(
                    local_path=path,
                    read_url="https://storage.example/snapshot.json",
                    timeout_seconds=5,
                )
        self.assertTrue(result["byte_identical"])
        self.assertEqual(result["local_sha256"], result["remote_sha256"])
        self.assertEqual(result["snapshot_as_of"], "2026-08-31T20:00:00+08:00")
        self.assertEqual(result["today_card_count"], 2)
        self.assertEqual(result["opportunity_pool_count"], 2)


if __name__ == "__main__":
    unittest.main()
