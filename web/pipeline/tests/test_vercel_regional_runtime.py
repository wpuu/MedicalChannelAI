from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
RUNTIME = WEB_ROOT / "collector_runtime.py"


class VercelRegionalRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RUNTIME.read_text(encoding="utf-8")

    def test_five_regional_stages_run_before_publish(self) -> None:
        stages = [
            '"regional_bj"',
            '"regional_he"',
            '"regional_ln"',
            '"regional_jl"',
            '"regional_hl"',
        ]
        positions = [self.source.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[-1], self.source.index('"publish"', positions[-1]))

    def test_regional_runtime_is_bounded_per_market(self) -> None:
        self.assertIn("REGIONAL_STAGE_MARKET_CODES", self.source)
        self.assertIn("plan[\"max_candidates_per_market\"]", self.source)
        self.assertIn("REGIONAL_FALLBACK_MAX_PAGES", self.source)
        self.assertIn("REGIONAL_ALL_DISCOVERY_QUERIES_FAILED", self.source)
        self.assertIn("REGIONAL_ALL_SELECTED_DETAILS_FAILED_VERIFICATION", self.source)
        self.assertIn("candidate_market_code", self.source)

    def test_publish_includes_market_sharded_regional_canonical_records(self) -> None:
        self.assertIn(
            'REGIONAL_RECORDS_KEY_PREFIX = "medicalchannelai:collector-regional-records:v3"',
            self.source,
        )
        self.assertIn('return f"{REGIONAL_RECORDS_KEY_PREFIX}:{normalized}"', self.source)
        publish = self.source[self.source.index("def _run_publish"):]
        self.assertIn("regional_records_by_market", publish)
        self.assertIn("for market_code in REGIONAL_STAGE_MARKET_CODES.values()", publish)
        self.assertIn("regional_records = [", publish)
        self.assertNotIn("cache.get(REGIONAL_RECORDS_KEY)", publish)

    def test_completed_regional_stage_replays_when_v3_cache_shard_is_missing(self) -> None:
        prepare = self.source[self.source.index("def _prepare_stage"):self.source.index("def _mark_completed")]
        self.assertIn("regional_cache_replay = False", prepare)
        self.assertIn("cache.get(_regional_records_key(market_code))", prepare)
        self.assertIn("if not regional_cache_replay:", prepare)
        self.assertIn("and not regional_cache_replay", prepare)

    def test_publish_gets_one_narrow_cache_migration_retry_and_names_missing_state(self) -> None:
        prepare = self.source[self.source.index("def _prepare_stage"):self.source.index("def _mark_completed")]
        self.assertIn("publish_cache_migration_retry", prepare)
        self.assertIn('stage == "publish"', prepare)
        self.assertIn('startswith("COLLECTOR_CANONICAL_STATE_INCOMPLETE")', prepare)
        publish = self.source[self.source.index("def _run_publish"):]
        self.assertIn("canonical_by_name", publish)
        self.assertIn("missing_canonical", publish)
        self.assertIn('"COLLECTOR_CANONICAL_STATE_INCOMPLETE:" +', publish)

    def test_regional_cache_bootstraps_only_the_current_market(self) -> None:
        self.assertIn(
            'DATA_ROOT / "regional_live_ccgp_records.json"',
            self.source,
        )
        self.assertIn("def _bootstrap_regional_records(market_code: str)", self.source)
        self.assertIn('get("market_code")', self.source)
        self.assertIn("regional_records_key = _regional_records_key(market_code)", self.source)
        self.assertIn("lambda: _bootstrap_regional_records(market_code)", self.source)
        self.assertIn("merge_canonical_records(existing_records, new_records)", self.source)


if __name__ == "__main__":
    unittest.main()
