from __future__ import annotations

import ast
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = WEB_ROOT / "collector_runtime.py"
NAMESPACE_PATH = WEB_ROOT / "collector_namespace.py"


def _function_source(source: str, name: str) -> str:
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"function not found: {name}")


def _tuple_assignment(source: str, name: str) -> tuple[str, ...]:
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            value = ast.literal_eval(node.value)
            if not isinstance(value, tuple):
                raise AssertionError(f"{name} must be a tuple")
            return value
    raise AssertionError(f"assignment not found: {name}")


class VercelAwardRuntimeTests(unittest.TestCase):
    """The 中标/成交 award stage is best-effort and must never block the chain."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = RUNTIME_PATH.read_text(encoding="utf-8")
        cls.namespace = NAMESPACE_PATH.read_text(encoding="utf-8")

    def test_award_stage_runs_after_event_watch_and_before_institution_stages(self) -> None:
        order = _tuple_assignment(self.runtime, "STAGE_ORDER")
        self.assertIn("award", order)
        self.assertEqual(order.index("award"), order.index("event6") + 1)
        self.assertLess(order.index("award"), order.index("tjmugh"))
        self.assertLess(order.index("award"), order.index("publish"))
        dispatch = _function_source(self.runtime, "run_stage")
        self.assertIn('elif stage == "award":', dispatch)
        self.assertIn("result = _run_award(cache, state)", dispatch)

    def test_award_stage_catches_every_failure_and_carries_the_store_forward(self) -> None:
        body = _function_source(self.runtime, "_run_award")
        self.assertIn("except Exception as exc:", body)
        self.assertGreaterEqual(body.count("except Exception as exc:"), 2)
        self.assertIn('"status": "DEGRADED"', body)
        self.assertIn('"award_store_carried_forward": True', body)
        self.assertNotIn("raise ", body)
        # The store only advances when the sync's own publish gate allows it.
        self.assertIn('if report["publish_allowed"]:', body)
        self.assertIn("_cache_set(cache, CCGP_AWARDS_KEY, merged_awards", body)
        self.assertIn('load_award_plan(DATA_ROOT / "tianjin_award_query_plan.json")', body)
        self.assertIn("run_award_sync(", body)

    def test_award_stage_reuses_the_verified_sync_and_bootstraps_from_bundled_store(self) -> None:
        self.assertIn("from sync_ccgp_awards import (", self.runtime)
        self.assertIn("load_plan as load_award_plan,", self.runtime)
        self.assertIn("run_award_sync,", self.runtime)
        self.assertRegex(self.runtime, r"from medical_channel_pipeline\.ccgp_award import [^\n]*merge_award_records")
        bootstrap = _function_source(self.runtime, "_bootstrap_ccgp_awards")
        self.assertIn('DATA_ROOT / "tianjin_award_records.json"', bootstrap)
        self.assertIn("if not path.exists():", bootstrap)
        self.assertIn("return []", bootstrap)
        self.assertIn("merge_award_records([], _load_array(path))", bootstrap)

    def test_publish_treats_awards_as_optional_input(self) -> None:
        publish = _function_source(self.runtime, "_run_publish")
        self.assertIn("award_records, _ = _cached_list(cache, CCGP_AWARDS_KEY, _bootstrap_ccgp_awards)", publish)
        self.assertIn("except Exception:", publish)
        self.assertIn("award_records = []", publish)
        self.assertIn("build_public_snapshot(records, as_of, list(events), award_records)", publish)
        self.assertIn('"award_record_count": len(award_records)', publish)
        self.assertIn('"awarded_project_count"', publish)
        self.assertIn('"award_ledger_count"', publish)
        # Awards are not part of the canonical completeness precondition.
        precondition = publish[: publish.index("missing_canonical")]
        self.assertNotIn("CCGP_AWARDS_KEY", precondition)

    def test_event_watch_skips_projects_that_already_have_a_published_result(self) -> None:
        # Both the Vercel ccgp stage and the GitHub-runner script drop awarded
        # projects from the 更正/终止 watch list (two CCGP searches per project
        # per day) and report what they skipped.
        ccgp = _function_source(self.runtime, "_run_ccgp")
        self.assertIn("exclude_awarded_projects(", ccgp)
        self.assertIn("_cached_list(cache, CCGP_AWARDS_KEY, _bootstrap_ccgp_awards)", ccgp)
        self.assertIn('"event_watch_skipped_awarded": awarded_watch_skipped', ccgp)
        self.assertLess(ccgp.index("exclude_awarded_projects("), ccgp.index("ACTIVE_EVENT_WATCH_CAP_EXCEEDED"))
        script = (WEB_ROOT / "pipeline" / "scripts" / "sync_tianjin_plan.py").read_text(encoding="utf-8")
        main = _function_source(script, "main")
        self.assertIn("'--existing-awards-input'", main)
        self.assertIn("exclude_awarded_projects(", main)
        self.assertIn("'event_watch_skipped_awarded': awarded_watch_skipped", main)

    def test_award_store_lives_in_the_isolated_v2_namespace(self) -> None:
        self.assertIn('CCGP_AWARDS_KEY = "medicalchannelai:collector-ccgp-awards:v1"', self.runtime)
        self.assertIn('CCGP_AWARDS_KEY = "medicalchannelai:collector-ccgp-awards:v2"', self.namespace)
        self.assertIn('"CCGP_AWARDS_KEY": CCGP_AWARDS_KEY,', self.namespace)


if __name__ == "__main__":
    unittest.main()
