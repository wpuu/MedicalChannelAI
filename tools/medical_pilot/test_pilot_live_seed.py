from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.pilot_live_seed import load_manifest, run_seed


VALID_URL = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260827_27219685.htm"
SECOND_URL = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260824_27194440.htm"


@dataclass
class FakeParsed:
    project_code: str


@dataclass
class FakeCollected:
    parsed: FakeParsed


class PilotLiveSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "pilot.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _manifest(self, entries: list[dict]) -> Path:
        path = self.root / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "purpose": "test",
                    "snapshot_date": "2026-08-30",
                    "entries": entries,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_manifest_accepts_registered_official_ccgp_detail_url(self) -> None:
        entries = load_manifest(
            self._manifest([{"expected_project_code": "ZYGP20260851", "url": VALID_URL}])
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].expected_project_code, "ZYGP20260851")

    def test_manifest_rejects_unregistered_or_non_https_url(self) -> None:
        with self.assertRaises(ValueError):
            load_manifest(
                self._manifest(
                    [{"expected_project_code": "X", "url": "https://example.com/not-official"}]
                )
            )
        with self.assertRaises(ValueError):
            load_manifest(
                self._manifest(
                    [{"expected_project_code": "X", "url": VALID_URL.replace("https://", "http://")}]
                )
            )

    def test_manifest_rejects_duplicate_project_code_or_url(self) -> None:
        with self.assertRaises(ValueError):
            load_manifest(
                self._manifest(
                    [
                        {"expected_project_code": "DUP", "url": VALID_URL},
                        {"expected_project_code": "DUP", "url": SECOND_URL},
                    ]
                )
            )

    def test_seed_returns_safe_success_summary_without_customer_or_model_payloads(self) -> None:
        manifest = self._manifest(
            [{"expected_project_code": "ZYGP20260851", "url": VALID_URL}]
        )
        collected = FakeCollected(FakeParsed("ZYGP20260851"))
        persist_calls = []

        def collector(url):
            self.assertEqual(url, VALID_URL)
            return collected

        def persister(value, *, db_path):
            self.assertIs(value, collected)
            self.assertEqual(db_path, self.db_path)
            persist_calls.append(value)
            return {
                "opportunity_id": "opp_real_1",
                "project_name": "天津市泰达医院数字X光机（DR）采购项目",
                "verification_status": "VERIFIED",
                "lifecycle_state": "TENDERING",
                "product_labels": ["MEDICAL_IMAGING_DR"],
                "customer_context": {"should_not": "leak"},
                "decision": {"should_not": "seed"},
            }

        exit_code, summary = run_seed(
            db_path=self.db_path,
            manifest_path=manifest,
            collector=collector,
            persister=persister,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(persist_calls), 1)
        self.assertEqual(summary["success_count"], 1)
        row = summary["results"][0]
        self.assertEqual(row["product_labels"], ["MEDICAL_IMAGING_DR"])
        self.assertNotIn("customer_context", row)
        self.assertNotIn("decision", row)
        self.assertNotIn("url", row)

    def test_partial_failure_returns_exit_one_and_sanitized_error_type(self) -> None:
        manifest = self._manifest(
            [
                {"expected_project_code": "ZYGP20260851", "url": VALID_URL},
                {"expected_project_code": "TJBH-2026-A-0052", "url": SECOND_URL},
            ]
        )

        def collector(url):
            if url == SECOND_URL:
                raise RuntimeError("secret upstream response must not leak")
            return FakeCollected(FakeParsed("ZYGP20260851"))

        def persister(value, *, db_path):
            return {
                "opportunity_id": "opp_real_1",
                "project_name": "DR",
                "verification_status": "VERIFIED",
                "lifecycle_state": "TENDERING",
                "product_labels": ["MEDICAL_IMAGING_DR"],
            }

        exit_code, summary = run_seed(
            db_path=self.db_path,
            manifest_path=manifest,
            collector=collector,
            persister=persister,
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["success_count"], 1)
        self.assertEqual(summary["failure_count"], 1)
        failed = summary["results"][1]
        self.assertEqual(failed["error_type"], "RuntimeError")
        self.assertNotIn("secret", json.dumps(summary, ensure_ascii=False))

    def test_project_code_mismatch_never_reaches_persistence(self) -> None:
        manifest = self._manifest(
            [{"expected_project_code": "ZYGP20260851", "url": VALID_URL}]
        )
        persisted = False

        def collector(url):
            return FakeCollected(FakeParsed("DIFFERENT-CODE"))

        def persister(value, *, db_path):
            nonlocal persisted
            persisted = True
            raise AssertionError("mismatched project must never persist")

        exit_code, summary = run_seed(
            db_path=self.db_path,
            manifest_path=manifest,
            collector=collector,
            persister=persister,
        )
        self.assertFalse(persisted)
        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["success_count"], 0)
        self.assertEqual(summary["results"][0]["error_type"], "ValueError")


if __name__ == "__main__":
    unittest.main()
