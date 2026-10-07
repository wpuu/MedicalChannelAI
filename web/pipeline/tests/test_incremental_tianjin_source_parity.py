from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class IncrementalTianjinSourceParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = (WEB_ROOT / "collector_runtime.py").read_text(encoding="utf-8")
        self.incremental = (WEB_ROOT / "collector_incremental_runtime.py").read_text(encoding="utf-8")
        self.policy = (WEB_ROOT / "collector_incremental.py").read_text(encoding="utf-8")
        self.scheduler = (WEB_ROOT / "collector_incremental_scheduler.py").read_text(encoding="utf-8")

    def test_time_sensitive_research_sources_have_explicit_intraday_policies(self) -> None:
        for source in ("tjzyefy", "tjzxfc"):
            self.assertIn(f'"{source}": {{', self.policy)
            self.assertIn(f'"{source}"', self.scheduler)
            self.assertIn(f'"{source}"', self.incremental)

    def test_procurement_intent_stays_daily_deep_only(self) -> None:
        self.assertNotIn('"tjzyefy_intent": {', self.policy)
        self.assertNotIn('"tjzyefy_intent"', self.scheduler)
        self.assertNotIn('"tjzyefy_intent"', self.incremental)
        self.assertIn('"tjzyefy_intent"', self.runtime)

    def test_incremental_runtime_reuses_existing_verified_adapters(self) -> None:
        required = (
            "runtime.parse_tjzyefy_index_html",
            "runtime.parse_tjzyefy_market_research",
            "runtime.parse_tjzxfc_index_html",
            "runtime.parse_tjzxfc_market_research",
        )
        for marker in required:
            self.assertIn(marker, self.incremental)

        # The incremental layer must orchestrate existing parsers, not fork a
        # second source-of-truth parser implementation.
        self.assertNotIn("def parse_tjzyefy_", self.incremental)
        self.assertNotIn("def parse_tjzxfc_", self.incremental)

    def test_nonmedical_source_rows_remain_nonfacts(self) -> None:
        self.assertIn('"TJZYEFY_NON_MEDICAL_RESEARCH"', self.incremental)
        self.assertIn('"TJZYEFY_PROCUREMENT_INTENT_NOT_SUPPORTED"', self.incremental)
        self.assertIn('"TJZXFC_NON_MEDICAL_EARLY_SIGNAL"', self.incremental)

    def test_deep_runtime_has_independent_canonical_state_for_all_three_sources(self) -> None:
        for marker in (
            'TJZYEFY_RECORDS_KEY = "medicalchannelai:collector-tjzyefy-records:v1"',
            'TJZYEFY_INTENT_RECORDS_KEY = "medicalchannelai:collector-tjzyefy-intent-records:v1"',
            'TJZXFC_RECORDS_KEY = "medicalchannelai:collector-tjzxfc-records:v1"',
            "def _bootstrap_tjzyefy_records()",
            "def _bootstrap_tjzyefy_intent_records()",
            "def _bootstrap_tjzxfc_records()",
            "def _run_tjzyefy(",
            "def _run_tjzyefy_intent(",
            "def _run_tjzxfc(",
        ):
            self.assertIn(marker, self.runtime)

    def test_publish_completeness_and_merge_include_all_three_sources(self) -> None:
        for marker in (
            '"tjzyefy": tjzyefy_records',
            '"tjzyefy_intent": tjzyefy_intent_records',
            '"tjzxfc": tjzxfc_records',
            "+ list(tjzyefy_records)",
            "+ list(tjzyefy_intent_records)",
            "+ list(tjzxfc_records)",
        ):
            self.assertIn(marker, self.runtime)
        self.assertIn("COLLECTOR_CANONICAL_STATE_INCOMPLETE", self.runtime)

    def test_deep_stage_order_runs_sources_before_publish(self) -> None:
        stage_start = self.runtime.index("STAGE_ORDER =")
        stage_end = self.runtime.index("EXPECTED_SCHEDULES =", stage_start)
        stage_block = self.runtime[stage_start:stage_end]
        publish_index = stage_block.index('"publish"')
        for source in ('"tjzyefy"', '"tjzyefy_intent"', '"tjzxfc"'):
            self.assertLess(stage_block.index(source), publish_index)


if __name__ == "__main__":
    unittest.main()
