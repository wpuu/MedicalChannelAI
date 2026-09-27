from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
RUNTIME = WEB_ROOT / "collector_runtime.py"


class VercelRegionalRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RUNTIME.read_text(encoding="utf-8")

    def test_each_regional_primary_and_fallback_runs_before_publish(self) -> None:
        stages = [
            '"regional_bj"',
            '"regional_bj_fallback"',
            '"regional_he"',
            '"regional_he_fallback"',
            '"regional_ln"',
            '"regional_ln_fallback"',
            '"regional_jl"',
            '"regional_jl_fallback"',
            '"regional_hl"',
            '"regional_hl_fallback"',
        ]
        stage_order = self.source[self.source.index("STAGE_ORDER = ("):self.source.index("class CollectorError")]
        positions = [stage_order.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[-1], stage_order.index('"publish"'))

    def test_stage_completion_merges_latest_runtime_state(self) -> None:
        self.assertIn("def _latest_stage_state_for_update(", self.source)
        self.assertIn("latest = load_status(cache)", self.source)
        self.assertIn("_write_status(cache, latest)", self.source)
        mark_completed = self.source[
            self.source.index("def _mark_completed"):
            self.source.index("def _mark_failed")
        ]
        self.assertNotIn("_write_status(cache, state)", mark_completed)

    def test_regional_runtime_is_bounded_per_market(self) -> None:
        self.assertIn("REGIONAL_STAGE_MARKET_CODES", self.source)
        self.assertIn("plan[\"max_candidates_per_market\"]", self.source)
        self.assertIn("REGIONAL_FALLBACK_MAX_PAGES", self.source)
        self.assertIn("REGIONAL_ALL_DISCOVERY_QUERIES_FAILED", self.source)
        self.assertIn("REGIONAL_ALL_SELECTED_DETAILS_FAILED_VERIFICATION", self.source)
        self.assertIn("candidate_market_code", self.source)

    def test_running_stage_is_claimed_by_wall_clock_lease_not_by_special_case_flags(self) -> None:
        prepare = self.source[self.source.index("def _prepare_stage"):self.source.index("def _mark_completed")]
        for removed_flag in (
            "regional_stale_migration_replay",
            "regional_timeout_split_replay",
            "publish_cache_migration_retry",
            "tjfch_policy_recovery_retry",
            "regional_cache_replay",
        ):
            self.assertNotIn(removed_flag, self.source)
        self.assertIn("if stage_lease_is_live(previous, now=wall_now):", prepare)
        self.assertIn('f"COLLECTOR_STAGE_LEASE_HELD:{stage}:', prepare)
        self.assertIn('previous["error_code"] = "COLLECTOR_STAGE_TIMEOUT"', prepare)
        self.assertIn('"started_at": wall_now.isoformat()', prepare)
        self.assertIn('"lease_expires_at": (wall_now + timedelta(seconds=STAGE_LEASE_SECONDS)).isoformat()', prepare)
        self.assertNotIn('"started_at": now.isoformat()', prepare)

    def test_every_regional_fallback_is_a_separate_bounded_queue_stage(self) -> None:
        mapping = self.source[self.source.index("REGIONAL_FALLBACK_STAGE_MARKET_CODES = {"):self.source.index("STAGE_ORDER = (")]
        for stage, code in (
            ("regional_bj_fallback", "BJ"),
            ("regional_he_fallback", "HE"),
            ("regional_ln_fallback", "LN"),
            ("regional_jl_fallback", "JL"),
            ("regional_hl_fallback", "HL"),
        ):
            self.assertIn(f'"{stage}": "{code}"', mapping)
        runtime = self.source[self.source.index("def _run_regional_market"):self.source.index("def _persist_verified_snapshot_durably")]
        self.assertIn("fallback_only = stage in REGIONAL_FALLBACK_STAGE_MARKET_CODES", runtime)
        self.assertIn('primary_stage = stage.removesuffix("_fallback")', runtime)
        self.assertIn('national_fallback_used = fallback_only', runtime)
        self.assertIn("REGIONAL_FALLBACK_STAGE_MARKET_CODES", self.source)

    def test_fallback_stage_map_does_not_duplicate_publish_market_map(self) -> None:
        primary_mapping = self.source[self.source.index("REGIONAL_STAGE_MARKET_CODES = {"):self.source.index("REGIONAL_FALLBACK_STAGE_MARKET_CODES = {")]
        self.assertNotIn("_fallback", primary_mapping)
        publish = self.source[self.source.index("def _run_publish"):]
        self.assertIn("for market_code in REGIONAL_STAGE_MARKET_CODES.values()", publish)

    def test_regional_discovery_and_detail_loops_respect_the_stage_budget(self) -> None:
        runtime = self.source[self.source.index("def _run_regional_market"):self.source.index("def _publish_min_pool_ratio")]
        self.assertIn('_require_budget(f"{stage}:scoped_discovery")', runtime)
        self.assertIn('_require_budget(f"{stage}:national_fallback_discovery")', runtime)
        self.assertIn("deferred_candidate_count = len(selected) - position", runtime)
        self.assertIn('raise CollectorStageBlocked(f"COLLECTOR_STAGE_BUDGET_EXHAUSTED:{stage}:detail")', runtime)
        self.assertIn("RegionalCcgpSearchSession(timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)", runtime)
        self.assertIn("fetch_ccgp_detail_html(candidate.detail_url, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)", runtime)
        self.assertNotIn("time.sleep(", runtime)

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

    def test_completed_stage_replays_when_its_canonical_output_is_missing(self) -> None:
        prepare = self.source[self.source.index("def _prepare_stage"):self.source.index("def _mark_completed")]
        outputs = self.source[self.source.index("def _stage_output_keys"):self.source.index("def _missing_stage_outputs")]
        self.assertIn("missing = _missing_stage_outputs(cache, stage)", prepare)
        self.assertIn('replay_reason = "COLLECTOR_STAGE_OUTPUT_MISSING:"', prepare)
        self.assertIn("attempts = 0", prepare)
        self.assertIn("return (_regional_records_key(REGIONAL_STAGE_MARKET_CODES[stage]),)", outputs)
        self.assertIn("return (CCGP_RECORDS_KEY, CCGP_EVENTS_KEY, CCGP_WATCH_KEY)", outputs)

    def test_publish_names_missing_canonical_state(self) -> None:
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
