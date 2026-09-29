from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT / "scripts"))

import sync_tianjin_plan  # noqa: E402


def candidate(url: str, published_at: str) -> SimpleNamespace:
    return SimpleNamespace(detail_url=url, published_at=published_at, title=f"项目 {url}")


def existing_record(url: str) -> dict:
    return {"schema_version": "0.1", "source": {"source_type": "CCGP_NOTICE", "url": url}}


class TianjinCandidateSelectionTests(unittest.TestCase):
    def test_unseen_urls_win_over_fresher_already_verified_urls(self) -> None:
        seen_new = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/seen_new.htm"
        seen_old = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/seen_old.htm"
        unseen_old = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/unseen_old.htm"
        unseen_older = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/unseen_older.htm"
        discovered = [
            ("公开招标", candidate(seen_new, "2026-09-29")),
            ("公开招标", candidate(seen_old, "2026-09-26")),
            ("竞争性磋商", candidate(unseen_old, "2026-09-25")),
            ("公开招标", candidate(unseen_older, "2026-09-23")),
        ]
        existing = [existing_record(seen_new), existing_record(seen_old)]

        selected = sync_tianjin_plan.select_tianjin_candidates(discovered, existing, max_candidates=2)
        self.assertEqual([item[1].detail_url for item in selected], [unseen_old, unseen_older])

        # Spare budget still re-verifies known URLs, newest first.
        selected = sync_tianjin_plan.select_tianjin_candidates(discovered, existing, max_candidates=3)
        self.assertEqual([item[1].detail_url for item in selected], [unseen_old, unseen_older, seen_new])

    def test_without_existing_records_order_is_pure_recency(self) -> None:
        a = candidate("https://www.ccgp.gov.cn/a.htm", "2026-09-27")
        b = candidate("https://www.ccgp.gov.cn/b.htm", "2026-09-29")
        selected = sync_tianjin_plan.select_tianjin_candidates([("公开招标", a), ("公开招标", b)], [], 5)
        self.assertEqual([item[1].detail_url for item in selected], [b.detail_url, a.detail_url])

    def test_existing_source_urls_ignore_malformed_rows(self) -> None:
        urls = sync_tianjin_plan.existing_source_urls_of(
            [None, {"source": None}, {"source": {"url": " "}}, existing_record("https://www.ccgp.gov.cn/x.htm")]
        )
        self.assertEqual(urls, {"https://www.ccgp.gov.cn/x.htm"})

    def test_default_plan_widens_window_within_loader_bounds(self) -> None:
        plan = sync_tianjin_plan.load_plan(sync_tianjin_plan.DEFAULT_PLAN)
        self.assertEqual(plan["lookback_days"], 7)
        self.assertEqual(plan["max_candidates"], 16)
        self.assertGreaterEqual(plan["delay_seconds"], 4.0)
        # Notice types that have no VERIFIED adapter must stay out of the plan
        # (the loader is fail-closed); award/correction/termination coverage
        # needs a parser first, not a config flip.
        self.assertEqual(plan["notice_types"], ["公开招标", "竞争性磋商"])
        raw = json.loads(sync_tianjin_plan.DEFAULT_PLAN.read_text(encoding="utf-8"))
        self.assertTrue(raw["policy"]["unseen_candidates_verified_first"])
        self.assertTrue(raw["policy"]["award_correction_termination_types_require_verified_adapter"])

    def test_vercel_deep_stage_uses_the_shared_unseen_first_selection(self) -> None:
        # collector_runtime imports the Vercel runtime, which is unavailable in
        # unit tests; the repo therefore pins runtime wiring at source level.
        runtime = (PIPELINE_ROOT.parent / "collector_runtime.py").read_text(encoding="utf-8")
        self.assertIn("select_tianjin_candidates,", runtime)
        self.assertIn(
            'selected = select_tianjin_candidates(discovered, existing_records, plan["max_candidates"])',
            runtime,
        )
        self.assertNotIn('selected = discovered[: plan["max_candidates"]]', runtime)

    def test_loader_rejects_notice_types_without_verified_adapter(self) -> None:
        raw = json.loads(sync_tianjin_plan.DEFAULT_PLAN.read_text(encoding="utf-8"))
        raw["notice_types"] = ["公开招标", "中标公告"]
        tmp = PIPELINE_ROOT / "data" / "_tmp_plan_award_types.json"
        tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "NOTICE_TYPE_UNSUPPORTED"):
                sync_tianjin_plan.load_plan(tmp)
        finally:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
