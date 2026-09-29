from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot as build_scoped_public_snapshot
from medical_channel_pipeline.ccgp_award import (
    awarded_project_keys,
    is_awarded_project,
    exclude_awarded_projects,
    MAX_LEDGER_ENTRIES,
    awarded_project_numbers,
    build_public_award_ledger,
    public_award_ledger_entry,
)
from medical_channel_pipeline.public_snapshot import build_public_snapshot
from scripts.publish_web_snapshot import combine_award_ledgers, combine_snapshots

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
AWARD_STORE = PIPELINE_ROOT / "data" / "tianjin_award_records.json"
POOL_STORE = PIPELINE_ROOT / "data" / "tianjin_live_ccgp_records.json"
AS_OF = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


def _awards() -> list[dict]:
    return json.loads(AWARD_STORE.read_text(encoding="utf-8"))


def _pool_record(project_number: str) -> dict:
    for record in json.loads(POOL_STORE.read_text(encoding="utf-8")):
        if record["facts"].get("project_number") == project_number:
            copied = copy.deepcopy(record)
            copied["facts"].setdefault("market_code", "TJ")
            return copied
    raise AssertionError(f"pool record not found: {project_number}")


class AwardSnapshotIntegrationTests(unittest.TestCase):
    def test_seeded_store_contains_real_tianjin_awards_matching_pool_projects(self) -> None:
        awards = _awards()
        self.assertGreaterEqual(len(awards), 3)
        numbers = {record["facts"]["project_number"] for record in awards}
        self.assertIn("XCSD-2026-A-589", numbers)
        self.assertIn("TJBHGP-2026-024", numbers)
        self.assertTrue(all(record["record_type"] == "AWARD_RESULT" for record in awards))
        self.assertTrue(all(record["facts"]["lifecycle_state"] == "AWARDED" for record in awards))
        self.assertTrue(all(record["source"]["url"].startswith("https://www.ccgp.gov.cn/") for record in awards))

    def test_published_award_retires_the_matching_pool_record(self) -> None:
        record = _pool_record("XCSD-2026-A-589")
        without = build_public_snapshot([record], AS_OF, [], [])
        with_awards = build_public_snapshot([record], AS_OF, [], _awards())
        self.assertEqual(without["awarded_project_count"], 0)
        self.assertEqual(without["award_ledger"], [])
        self.assertEqual(with_awards["awarded_project_count"], 1)
        self.assertEqual(with_awards["input_candidate_count"], 1)
        self.assertEqual(with_awards["opportunity_pool"], [])
        self.assertEqual(with_awards["cards"], [])
        self.assertEqual(
            [entry["project_number"] for entry in with_awards["award_ledger"]],
            [record["facts"]["project_number"] for record in sorted(_awards(), key=lambda item: (item["facts"]["published_at"], item["award_id"]), reverse=True)],
        )

    def test_full_width_or_spaced_pool_number_still_retires(self) -> None:
        # Tender notice typed with full-width dashes/spaces; result notice with ASCII.
        record = _pool_record("XCSD-2026-A-589")
        record["facts"]["project_number"] = "ＸＣＳＤ－2026－A－589 "
        snapshot = build_public_snapshot([record], AS_OF, [], _awards())
        self.assertEqual(snapshot["awarded_project_count"], 1)
        self.assertEqual(snapshot["opportunity_pool"], [])

    def test_event_watch_list_drops_awarded_projects_in_order(self) -> None:
        watch = ["XCSD-2026-A-641", "ＸＣＳＤ－2026－A－589", "TJBHGP-2026-024", "TJBD-2026-C-212"]
        kept, skipped = exclude_awarded_projects(watch, _awards(), AS_OF)
        self.assertEqual(kept, ["XCSD-2026-A-641", "TJBD-2026-C-212"])
        self.assertEqual(skipped, ["ＸＣＳＤ－2026－A－589", "TJBHGP-2026-024"])
        self.assertEqual(exclude_awarded_projects(watch, None, AS_OF), (watch, []))
        # Awards published after as_of are not yet effective, so nothing is skipped.
        early = datetime(2026, 9, 1, tzinfo=timezone.utc)
        self.assertEqual(exclude_awarded_projects(watch, _awards(), early), (watch, []))

    def test_award_only_retires_opportunities_of_its_own_market(self) -> None:
        # Same project number in another market must not be concluded by a Tianjin result.
        record = _pool_record("XCSD-2026-A-589")
        record["facts"]["market_code"] = "HE"
        record["facts"]["market_name"] = "河北"
        record["facts"]["market_admin_code"] = "130000"
        snapshot = build_public_snapshot([record], AS_OF, [], _awards())
        self.assertEqual(snapshot["awarded_project_count"], 0)
        self.assertEqual(snapshot["input_candidate_count"], 1)
        # The ledger itself is market-agnostic; the entry still carries its own market.
        self.assertEqual({entry["market_code"] for entry in snapshot["award_ledger"]}, {"TJ"})
        # Legacy awards without a market code keep the market-agnostic behaviour.
        legacy = copy.deepcopy(_awards())
        for item in legacy:
            item["facts"].pop("market_code", None)
        self.assertEqual(build_public_snapshot([record], AS_OF, [], legacy)["awarded_project_count"], 1)
        keys = awarded_project_keys(_awards(), AS_OF)
        self.assertIn(("TJ", "xcsd-2026-a-589"), keys)
        self.assertTrue(is_awarded_project(keys, "ＸＣＳＤ－2026－A－589", "tj"))
        self.assertFalse(is_awarded_project(keys, "XCSD-2026-A-589", "HE"))
        self.assertFalse(is_awarded_project(keys, "", "TJ"))

    def test_future_dated_award_is_not_effective_yet(self) -> None:
        awards = _awards()
        future = copy.deepcopy(awards[0])
        future["facts"]["published_at"] = "2026-10-05"
        self.assertNotIn(future["facts"]["project_number"].lower(), awarded_project_numbers([future], AS_OF))
        self.assertEqual(build_public_award_ledger([future], AS_OF), [])
        self.assertEqual(len(build_public_award_ledger([future], datetime(2026, 10, 5, tzinfo=timezone.utc))), 1)

    def test_ledger_entry_is_compact_and_public_only(self) -> None:
        awards = _awards()
        target = next(record for record in awards if record["facts"]["project_number"] == "XCSD-2026-A-589")
        entry = public_award_ledger_entry(target, AS_OF)
        self.assertEqual(entry["award_id"], target["award_id"])
        self.assertEqual(entry["market_code"], "TJ")
        self.assertEqual(entry["result_kind"], "AWARD")
        self.assertEqual(entry["total_amount_cny"], 13_950_000)
        self.assertEqual(entry["packages"][0]["supplier_name"], "天津市联大医用设备有限公司")
        self.assertEqual(entry["items"][0]["brand"], "联影")
        self.assertEqual(entry["items"][0]["model"], "uAngio960")
        self.assertEqual(entry["source_url"], target["source"]["url"])
        self.assertEqual(entry["legal_windows"][0]["code"], "RESULT_CHALLENGE")
        self.assertEqual(entry["legal_windows"][0]["anchor_date"], "2026-09-28")
        self.assertEqual(entry["legal_windows"][0]["deadline_date"], "2026-10-14")
        serialized = json.dumps(entry, ensure_ascii=False)
        for forbidden in ("supplier_address", "public_contact", "phone", "evidence", "统一社会信用代码"):
            self.assertNotIn(forbidden, serialized)
        self.assertLess(len(serialized.encode("utf-8")), 4096)

    def test_ledger_is_bounded_and_newest_first(self) -> None:
        awards = _awards()
        ledger = build_public_award_ledger(awards, AS_OF)
        dates = [entry["published_at"] for entry in ledger]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(len(build_public_award_ledger(awards, AS_OF, max_entries=1)), 1)
        self.assertLessEqual(MAX_LEDGER_ENTRIES, 60)

    def test_scope_wrapper_and_combiner_pass_the_ledger_through(self) -> None:
        record = _pool_record("XCSD-2026-A-589")
        tianjin = build_scoped_public_snapshot([record], AS_OF, [], _awards())
        regional = build_public_snapshot([], AS_OF, [], [])
        self.assertEqual(len(tianjin["award_ledger"]), len(_awards()))
        combined = combine_snapshots(tianjin, regional, [record], AS_OF)
        self.assertEqual(combined["awarded_project_count"], 1)
        self.assertEqual([entry["award_id"] for entry in combined["award_ledger"]], [entry["award_id"] for entry in tianjin["award_ledger"]])
        # Duplicated ledgers dedupe by award_id and stay bounded.
        merged = combine_award_ledgers(tianjin, tianjin)
        self.assertEqual(len(merged), len(tianjin["award_ledger"]))
        self.assertLessEqual(len(merged), MAX_LEDGER_ENTRIES)


if __name__ == "__main__":
    unittest.main()
