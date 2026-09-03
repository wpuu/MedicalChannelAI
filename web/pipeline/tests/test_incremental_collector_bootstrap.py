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

    def test_changed_index_fingerprint_can_never_be_erased_by_older_canonical_state(self) -> None:
        fingerprint_guard = self.bootstrap.index('if previous_fingerprint != observation.fingerprint:')
        strict_match = self.bootstrap.index('strict_metadata_match = _canonical_matches_discovery', fingerprint_guard)
        seed = self.bootstrap.index('ledger = record_verification_success(', strict_match)
        block = self.bootstrap[fingerprint_guard:strict_match]
        self.assertIn('metadata_changed_pending += 1', block)
        self.assertIn('continue', block)
        self.assertLess(fingerprint_guard, strict_match)
        self.assertLess(strict_match, seed)

    def test_newer_failed_or_unverified_incremental_state_blocks_stale_canonical_repair(self) -> None:
        self.assertIn('existing_updated_at = _parsed_at(normalized_existing.get("updated_at"))', self.bootstrap)
        self.assertIn('previous_needs_verification = not previous_is_current_verified', self.bootstrap)
        self.assertIn('existing_updated_at >= verified_at', self.bootstrap)
        self.assertIn('newer_incremental_state += 1', self.bootstrap)
        self.assertIn('already_newer_verified += 1', self.bootstrap)
        self.assertIn('newer_incremental_state_count', self.bootstrap)

    def test_tjfch_tracked_fingerprint_bridge_requires_canonical_after_prior_index_observation(self) -> None:
        start = self.bootstrap.index('if tracked_fingerprint_matches and not strict_metadata_match:')
        end = self.bootstrap.index('ledger = record_verification_success(', start)
        block = self.bootstrap[start:end]
        self.assertIn('previous_seen_at = _parsed_at(previous.get("last_seen_at"))', block)
        self.assertIn('verified_at < previous_seen_at', block)
        self.assertIn('bridge_too_old += 1', block)
        self.assertIn('tracked_fingerprint_bridge += 1', block)

    def test_reconcile_keeps_source_level_ledger_clock_monotonic(self) -> None:
        seed = self.bootstrap.index('ledger = record_verification_success(')
        clock = self.bootstrap.index('ledger["updated_at"] = current.isoformat()', seed)
        save = self.bootstrap.index('incremental_runtime._save_ledger(cache, source, ledger)', clock)
        self.assertLess(seed, clock)
        self.assertLess(clock, save)

    def test_existing_failed_or_unverified_ledger_can_still_be_repaired_by_newer_canonical_fact(self) -> None:
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
