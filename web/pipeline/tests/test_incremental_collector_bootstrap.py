from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class IncrementalCollectorBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bootstrap = (WEB_ROOT / "collector_incremental_bootstrap.py").read_text(encoding="utf-8")
        self.runtime = (WEB_ROOT / "collector_incremental_runtime.py").read_text(encoding="utf-8")
        self.queue = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")

    def test_reconcile_reuses_real_discovery_and_never_becomes_second_fact_source(self) -> None:
        self.assertIn('if discovered is None:', self.bootstrap)
        self.assertIn('"action": "DISCOVERY_REQUIRED"', self.bootstrap)
        self.assertNotIn('_DISCOVERY[source]', self.bootstrap)
        self.assertIn('"action": "RECONCILED" if existing_entries else "BOOTSTRAPPED"', self.bootstrap)
        self.assertIn('RECENT_DEEP_VERIFICATION_MAX_AGE = timedelta(hours=6)', self.bootstrap)
        self.assertIn('_record_source_url(record)', self.bootstrap)
        self.assertIn('_record_observed_at(record)', self.bootstrap)
        self.assertIn('record_verification_success(', self.bootstrap)
        self.assertIn('verified_at=verified_at', self.bootstrap)

    def test_url_match_alone_still_cannot_claim_current_discovery_metadata_verified(self) -> None:
        self.assertIn('candidate_title != canonical_title', self.bootstrap)
        self.assertIn('candidate_published != canonical_published', self.bootstrap)
        self.assertIn('if source_id == "tjfch":', self.bootstrap)
        self.assertIn('return False', self.bootstrap)
        self.assertIn('previous.get("fingerprint") == observation.fingerprint', self.bootstrap)
        self.assertIn('if not strict_metadata_match and not tracked_fingerprint_matches:', self.bootstrap)
        self.assertIn('if verified_at is None or verified_at > current:', self.bootstrap)
        self.assertIn('current - verified_at > RECENT_DEEP_VERIFICATION_MAX_AGE', self.bootstrap)

    def test_existing_failed_or_unverified_ledger_can_be_repaired_by_recent_canonical_fact(self) -> None:
        self.assertIn('existing_entries = normalized_existing["entries"]', self.bootstrap)
        self.assertIn('tracked_fingerprint_bridge_count', self.bootstrap)
        self.assertNotIn('LEDGER_ALREADY_INITIALIZED', self.bootstrap)
        self.assertIn('ledger = plan.next_ledger', self.bootstrap)
        self.assertIn('incremental_runtime._save_ledger(cache, source, ledger)', self.bootstrap)

    def test_bootstrap_never_uses_private_customer_context(self) -> None:
        for forbidden in ('user_id', 'organization_id', 'local_scope', 'hospital_relationships', 'product_capabilities'):
            self.assertNotIn(forbidden, self.bootstrap)

    def test_runtime_discovers_once_then_reconciles_before_detail_planning(self) -> None:
        discovery = self.runtime.index('discovered = _DISCOVERY[source](observed)')
        reconcile = self.runtime.index('bootstrap_incremental_ledger_from_canonical(', discovery)
        planning = self.runtime.index('plan = plan_detail_verification(', reconcile)
        self.assertLess(discovery, reconcile)
        self.assertLess(reconcile, planning)
        block = self.runtime[reconcile:planning]
        self.assertIn('discovered=discovered', block)
        self.assertNotIn('_DISCOVERY[source]', block)
        self.assertIn('_release_incremental_lease(cache, scan_id)', self.queue)


if __name__ == "__main__":
    unittest.main()
