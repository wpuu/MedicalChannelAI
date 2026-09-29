from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot
from medical_channel_pipeline.award_price_reference import (
    MAX_REFERENCE_ROWS,
    award_price_reference_rows,
    build_award_price_reference,
    combine_award_price_references,
)
from medical_channel_pipeline.device_families import (
    device_families_payload,
    device_family_for_name,
    load_device_families,
    load_device_family_parity_vectors,
    normalize_device_name,
)

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
AS_OF = datetime.fromisoformat("2026-09-29T18:00:00+08:00")


def _store(name: str) -> list[dict]:
    return json.loads((PIPELINE_ROOT / "data" / name).read_text(encoding="utf-8"))


def _all_awards() -> list[dict]:
    return [*_store("tianjin_award_records.json"), *_store("regional_award_records.json")]


class DeviceFamilyTests(unittest.TestCase):
    def test_taxonomy_is_ordered_unique_and_every_family_has_a_label(self) -> None:
        families = load_device_families()
        codes = [family["code"] for family in families]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(family["label"] for family in families))
        # Service / consumable buckets must win over device buckets (see JSON notes).
        self.assertLess(codes.index("MAINTENANCE"), codes.index("ULTRASOUND"))
        self.assertLess(codes.index("STERILIZATION"), codes.index("ENDOSCOPY"))
        self.assertLess(codes.index("DENTAL"), codes.index("CT"))
        self.assertLess(codes.index("NUCLEAR_RT"), codes.index("CT"))

    def test_parity_vectors_hold(self) -> None:
        vectors = load_device_family_parity_vectors()
        self.assertGreaterEqual(len(vectors), 30)
        for name, expected in vectors:
            with self.subTest(name=name):
                self.assertEqual(device_family_for_name(name), expected)

    def test_acronyms_match_whole_tokens_only_and_names_are_normalised(self) -> None:
        self.assertEqual(device_family_for_name("CBCT"), "DENTAL")
        self.assertEqual(device_family_for_name("PET-CT"), "NUCLEAR_RT")
        self.assertEqual(device_family_for_name("64排ct"), "CT")
        self.assertEqual(device_family_for_name("ｍｒｉ 系统"), "MRI")
        self.assertIsNone(device_family_for_name("DRY BOX"))  # ``DR`` inside ``DRY`` is not a token
        self.assertIsNone(device_family_for_name(None))
        self.assertEqual(normalize_device_name("　彩色　多普勒（Ｘ）"), "彩色 多普勒(X)")

    def test_payload_carries_exactly_what_the_client_needs(self) -> None:
        payload = device_families_payload()
        self.assertEqual({tuple(sorted(item)) for item in payload}, {("acronyms", "code", "keywords", "label")})
        self.assertEqual([item["code"] for item in payload], [family["code"] for family in load_device_families()])


class AwardPriceReferenceTests(unittest.TestCase):
    def test_rows_come_from_real_award_lines_with_single_brand_and_unit_price(self) -> None:
        rows = award_price_reference_rows(_all_awards(), AS_OF)
        self.assertGreaterEqual(len(rows), 40)
        for row in rows:
            with self.subTest(row=row["name"]):
                self.assertIsInstance(row["unit_price_cny"], int)
                self.assertGreater(row["unit_price_cny"], 0)
                self.assertTrue(row["brand"])
                self.assertNotRegex(row["brand"], r"[;；、]")
                self.assertNotIn("详见附件", row["name"])
                self.assertTrue(row["source_url"].startswith("https://www.ccgp.gov.cn/"))
                self.assertIn(row["market_code"], {"TJ", "BJ", "HE", "LN", "JL", "HL"})
        by_name = {(row["brand"], row["model"]): row for row in rows}
        # Real evidence lines observed 2026-09-28/29.
        self.assertEqual(by_name[("通用电气", "LOGIQ E20 Pro")]["unit_price_cny"], 2_418_000)
        self.assertEqual(by_name[("通用电气", "LOGIQ E20 Pro")]["family"], "ULTRASOUND")
        self.assertEqual(by_name[("通用电气", "LOGIQ E20 Pro")]["line_count"], 3)  # three 品目号 lines, one row
        self.assertEqual(by_name[("迈瑞", "TV80S")]["line_count"], 1)
        self.assertEqual(by_name[("迈瑞", "TV80S")]["unit_price_cny"], 150_000)
        self.assertEqual(by_name[("联影", "uAngio960")]["family"], "DSA")
        # Multi-valued cells are never attributed to one price.
        self.assertNotIn(("卡尔史托斯； 其他详见附件", "IMAGE1 S 4U; 其他详见附件"), by_name)
        self.assertFalse(any(row["name"].startswith("口腔综合治疗仪") for row in rows))
        # Newest first, stable within an award.
        dates = [row["published_at"] for row in rows]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_lookback_and_cap_are_enforced_and_reported(self) -> None:
        awards = _all_awards()
        old = copy.deepcopy(awards[0])
        old["award_id"] = "ccgpaward_old_reference"
        old["source"]["url"] = old["source"]["url"].replace(".htm", "_old.htm")
        old["facts"]["published_at"] = "2025-01-15"
        old["facts"]["items"] = [
            {"package_no": None, "category": None, "name": "老旧彩超", "brand": "老品牌", "model": "X1", "quantity": "1", "unit_price_cny": 100},
        ]
        rows = award_price_reference_rows([*awards, old], AS_OF, lookback_days=365)
        self.assertFalse(any(row["award_id"] == "ccgpaward_old_reference" for row in rows))
        rows_wide = award_price_reference_rows([*awards, old], AS_OF, lookback_days=3650)
        self.assertTrue(any(row["award_id"] == "ccgpaward_old_reference" for row in rows_wide))

        reference = build_award_price_reference(awards, AS_OF, max_rows=5)
        self.assertEqual(reference["row_count"], 5)
        self.assertTrue(reference["truncated"])
        self.assertEqual(sum(reference["family_row_counts"].values()), 5)
        self.assertEqual(reference["families"], device_families_payload())
        full = build_award_price_reference(awards, AS_OF)
        self.assertEqual(full["max_rows"], MAX_REFERENCE_ROWS)
        self.assertFalse(full["truncated"])

    def test_combine_dedupes_and_keeps_newest_first(self) -> None:
        tianjin = build_award_price_reference(_store("tianjin_award_records.json"), AS_OF)
        regional = build_award_price_reference(_store("regional_award_records.json"), AS_OF)
        combined = combine_award_price_references(tianjin, regional)
        self.assertEqual(combined["row_count"], tianjin["row_count"] + regional["row_count"])
        again = combine_award_price_references(combined, tianjin, None)
        self.assertEqual(again["row_count"], combined["row_count"])
        dates = [row["published_at"] for row in again["rows"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(again["families"], device_families_payload())
        empty = combine_award_price_references(None, None)
        self.assertEqual(empty["row_count"], 0)
        self.assertEqual(empty["rows"], [])

    def test_snapshot_embeds_reference_and_ledger_items_carry_category(self) -> None:
        records = json.loads((PIPELINE_ROOT / "data" / "regional_live_ccgp_records.json").read_text(encoding="utf-8"))
        snapshot = build_public_snapshot(records[:5], AS_OF, [], _store("regional_award_records.json"))
        reference = snapshot["award_price_reference"]
        self.assertEqual(reference["schema_version"], "0.1")
        self.assertGreater(reference["row_count"], 0)
        self.assertEqual({tuple(sorted(row)) for row in reference["rows"]}, {(
            "award_id", "brand", "buyer_name", "family", "line_count", "market_code", "model", "name",
            "project_number", "published_at", "quantity", "source_url", "unit_price_cny",
        )})
        for row in reference["rows"]:
            self.assertNotIn("supplier_address", row)
            self.assertNotIn("public_contact", row)
        item = snapshot["award_ledger"][0]["items"][0]
        self.assertIn("category", item)


if __name__ == "__main__":
    unittest.main()
