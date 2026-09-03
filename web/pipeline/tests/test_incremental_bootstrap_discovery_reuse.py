from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class IncrementalBootstrapDiscoveryReuseTests(unittest.TestCase):
    def test_bootstrap_never_owns_an_official_discovery_request(self) -> None:
        bootstrap = (WEB_ROOT / "collector_incremental_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("discovered: Iterable[Any] | None = None", bootstrap)
        self.assertIn('return {"action": "DISCOVERY_REQUIRED", "source_id": source}', bootstrap)
        self.assertNotIn("incremental_runtime._DISCOVERY[source](current)", bootstrap)

    def test_runtime_discovers_once_then_reuses_rows_for_bootstrap_and_planning(self) -> None:
        runtime = (WEB_ROOT / "collector_incremental_runtime.py").read_text(encoding="utf-8")
        start = runtime.index("def run_incremental_source(")
        block = runtime[start:]

        discovery = block.index("discovered = _DISCOVERY[source](observed)")
        bootstrap = block.index("bootstrap_incremental_ledger_from_canonical(")
        ledger = block.index("ledger = _load_ledger(cache, source)", bootstrap)
        plan = block.index("plan = plan_detail_verification(", ledger)

        self.assertLess(discovery, bootstrap)
        self.assertLess(bootstrap, ledger)
        self.assertLess(ledger, plan)
        self.assertIn("discovered=discovered", block[bootstrap:ledger])
        self.assertEqual(block.count("_DISCOVERY[source](observed)"), 1)

    def test_queue_preflight_bootstrap_cannot_duplicate_network_discovery(self) -> None:
        queue = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        bootstrap = (WEB_ROOT / "collector_incremental_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("bootstrap_incremental_ledger_from_canonical(", queue)
        self.assertIn("if discovered is None:", bootstrap)
        self.assertNotIn("_DISCOVERY[", bootstrap)


if __name__ == "__main__":
    unittest.main()
