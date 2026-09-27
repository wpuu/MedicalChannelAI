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

    def test_stale_running_regional_stage_can_replay_only_for_known_migration_failure(self) -> None:
        self.assertIn("regional_stale_migration_replay = False", self.source)
        self.assertIn('previous.get("status") == "RUNNING"', self.source)
        self.assertIn('publish_state.get("status") == "FAILED"', self.source)
        self.assertIn('startswith("COLLECTOR_CANONICAL_STATE_INCOMPLETE")', self.source)
        self.assertIn("timedelta(minutes=15)", self.source)
        self.assertIn('int(previous.get("attempt_count", 0)) == MAX_STAGE_ATTEMPTS_PER_DAY', self.source)
        prepare = self.source[self.source.index("def _prepare_stage"):self.source.index("def _mark_completed")]
        stale_block = prepare[prepare.index("regional_stale_migration_replay = bool("):prepare.index("if index > 0:")]
        self.assertNotIn("not isinstance(cache.get(_regional_records_key(market_code)), list)", stale_block)
        self.assertIn("and not regional_stale_migration_replay", self.source)

    def test_beijing_fallback_is_a_separate_bounded_queue_stage(self) -> None:
        stage_order = self.source[self.source.index("STAGE_ORDER = ("):self.source.index("EXPECTED_SCHEDULES")]
        self.assertLess(stage_order.index('"regional_bj"'), stage_order.index('"regional_bj_fallback"'))
        self.assertLess(stage_order.index('"regional_bj_fallback"'), stage_order.index('"regional_he"'))
        runtime = self.source[self.source.index("def _run_regional_market"):self.source.index("def _persist_verified_snapshot_durably")]
        self.assertIn('fallback_only = stage == "regional_bj_fallback"', runtime)
        self.assertIn('"fallback_required": True', runtime)
        self.assertIn('national_fallback_used = fallback_only or (stage != "regional_bj" and not scoped_found_candidates)', runtime)
        self.assertIn('elif stage in REGIONAL_STAGE_MARKET_CODES or stage == "regional_bj_fallback"', self.source)

    def test_beijing_fallback_does_not_duplicate_publish_market_map(self) -> None:
        mapping = self.source[self.source.index("REGIONAL_STAGE_MARKET_CODES = {"):self.source.index("STAGE_ORDER = (")]
        self.assertIn('"regional_bj": "BJ"', mapping)
        self.assertNotIn('"regional_bj_fallback"', mapping)
        publish = self.source[self.source.index("def _run_publish"):]
        self.assertIn("for market_code in REGIONAL_STAGE_MARKET_CODES.values()", publish)

    def test_timeout_split_recovery_is_one_extra_attempt_only(self) -> None:
        prepare = self.source[self.source.index("def _prepare_stage"):self.source.index("def _mark_completed")]
        self.assertIn("bj_timeout_split_replay", prepare)
        self.assertIn('stage == "regional_bj"', prepare)
        self.assertIn("attempts == MAX_STAGE_ATTEMPTS_PER_DAY + 1", prepare)
        self.assertIn('"regional_bj_fallback" not in stages', prepare)
        self.assertIn("and not bj_timeout_split_replay", prepare)

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
