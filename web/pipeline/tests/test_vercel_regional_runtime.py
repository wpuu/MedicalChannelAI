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

    def test_publish_includes_regional_canonical_records(self) -> None:
        self.assertIn(
            'REGIONAL_RECORDS_KEY = "medicalchannelai:collector-regional-records:v2"',
            self.source,
        )
        publish = self.source[self.source.index("def _run_publish"):]
        self.assertIn("regional_records = cache.get(REGIONAL_RECORDS_KEY)", publish)
        self.assertIn("+ list(regional_records)", publish)

    def test_regional_cache_bootstraps_from_verified_git_data(self) -> None:
        self.assertIn(
            'DATA_ROOT / "regional_live_ccgp_records.json"',
            self.source,
        )
        self.assertIn("_bootstrap_regional_records", self.source)
        self.assertIn("merge_canonical_records(existing_records, new_records)", self.source)


if __name__ == "__main__":
    unittest.main()
