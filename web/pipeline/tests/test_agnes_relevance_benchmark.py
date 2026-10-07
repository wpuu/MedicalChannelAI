from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / "scripts" / "run_agnes_relevance_benchmark.py"
DATASET_PATH = PIPELINE_ROOT / "data" / "action_radar_relevance_gold.json"

spec = importlib.util.spec_from_file_location("run_agnes_relevance_benchmark", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("AGNES_RELEVANCE_BENCHMARK_IMPORT_FAILED")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class AgnesRelevanceBenchmarkTests(unittest.TestCase):
    def test_dataset_has_exactly_45_profile_case_pairs(self) -> None:
        profiles, opportunities = bench.validate_dataset(
            json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        )
        self.assertEqual(len(profiles), 3)
        self.assertEqual(len(opportunities), 15)
        self.assertEqual(len(profiles) * len(opportunities), 45)

    def test_prompt_never_sends_expected_labels_or_source_notes(self) -> None:
        payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        profile = payload["profiles"][0]
        opportunity = payload["opportunities"][0]
        messages = bench.build_messages(profile, opportunity)
        rendered = json.dumps(messages, ensure_ascii=False)
        self.assertNotIn('"expected"', rendered)
        self.assertNotIn("source_note", rendered)
        self.assertNotIn("ACTION_RADAR_GOLDSET", rendered)

    def test_parser_accepts_only_grounded_enum_and_ids(self) -> None:
        parsed = bench.parse_content(
            '{"classification":"DIRECT_MATCH","matched_profile_item_ids":["A2"]}',
            {"A1", "A2"},
        )
        self.assertEqual(parsed["classification"], "DIRECT_MATCH")
        self.assertEqual(parsed["matched_profile_item_ids"], ["A2"])

    def test_parser_rejects_model_invented_profile_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "ID_NOT_GROUNDED"):
            bench.parse_content(
                '{"classification":"DIRECT_MATCH","matched_profile_item_ids":["X9"]}',
                {"A1", "A2"},
            )

    def test_parser_rejects_extra_natural_language_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_FIELD"):
            bench.parse_content(
                '{"classification":"NOT_MATCH","matched_profile_item_ids":[],"reason":"医院很大"}',
                {"A1"},
            )

    def test_not_match_must_have_empty_matched_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "NOT_MATCH_MUST_BE_EMPTY"):
            bench.parse_content(
                '{"classification":"NOT_MATCH","matched_profile_item_ids":["A1"]}',
                {"A1"},
            )

    def test_positive_match_requires_grounded_profile_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "MATCH_REQUIRES_ID"):
            bench.parse_content(
                '{"classification":"POSSIBLE_MATCH_NEEDS_CONFIRMATION","matched_profile_item_ids":[]}',
                {"B4"},
            )

    def test_api_keys_are_never_required_for_offline_contract_tests(self) -> None:
        prior = os.environ.pop("AGNES_API_KEYS", None)
        try:
            self.assertEqual(
                bench.parse_content(
                    '{"classification":"NOT_MATCH","matched_profile_item_ids":[]}',
                    {"C1"},
                )["classification"],
                "NOT_MATCH",
            )
        finally:
            if prior is not None:
                os.environ["AGNES_API_KEYS"] = prior


if __name__ == "__main__":
    unittest.main()
