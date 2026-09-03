from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class IncrementalCollectorBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bootstrap = (WEB_ROOT / "collector_incremental_bootstrap.py").read_text(encoding="utf-8")
        self.queue = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")

    def test_bootstrap_is_one_time_optimization_not_a_second_fact_source(self) -> None:
        self.assertIn('if normalize_ledger(existing_ledger)["entries"]:', self.bootstrap)
        self.assertIn('return {"action": "LEDGER_ALREADY_INITIALIZED"', self.bootstrap)
        self.assertIn('RECENT_DEEP_VERIFICATION_MAX_AGE = timedelta(hours=6)', self.bootstrap)
        self.assertIn('_record_source_url(record)', self.bootstrap)
        self.assertIn('_record_observed_at(record)', self.bootstrap)
        self.assertIn('record_verification_success(', self.bootstrap)
        self.assertIn('verified_at=verified_at', self.bootstrap)

    def test_url_match_alone_can_never_claim_current_discovery_metadata_verified(self) -> None:
        self.assertIn('candidate_title != canonical_title', self.bootstrap)
        self.assertIn('candidate_published != canonical_published', self.bootstrap)
        self.assertIn('if source_id == "tjfch":', self.bootstrap)
        self.assertIn('return False', self.bootstrap)
        self.assertIn('if verified_at is None or verified_at > current:', self.bootstrap)
        self.assertIn('current - verified_at > RECENT_DEEP_VERIFICATION_MAX_AGE', self.bootstrap)

    def test_bootstrap_never_uses_private_customer_context(self) -> None:
        for forbidden in ('user_id', 'organization_id', 'local_scope', 'hospital_relationships', 'product_capabilities'):
            self.assertNotIn(forbidden, self.bootstrap)

    def test_queue_bootstraps_before_incremental_detail_planning(self) -> None:
        seed = self.queue.index('bootstrap_incremental_ledger_from_canonical(')
        run = self.queue.index('incremental_runtime.run_incremental_source(')
        self.assertLess(seed, run)
        self.assertIn('_release_incremental_lease(cache, scan_id)', self.queue)


if __name__ == "__main__":
    unittest.main()
