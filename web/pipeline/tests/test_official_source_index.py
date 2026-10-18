"""All list shapes and captures in these tests are synthetic, not official HTML."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_twice_daily_source_parity as core_tests
from test_collector_native_reliability import runtime
import collector_official_index as index
from collector_official_transport import OfficialPage, SOURCE_INDEXES


OBSERVED = datetime(2026, 9, 29, 0, 41, tzinfo=timezone.utc)
START, END = date(2026, 8, 31), date(2026, 9, 29)


def anchor(day, *, title="公告", number="123", host="www.tjzyefy.com"):
    path = day.strftime("%Y/%m/%d")
    return f'<li><a href="https://{host}/system/{path}/{number}.shtml">{title}</a></li>'


def fixture(*rows, outside=""):
    return f'<html><body>{outside}<ul id="synthetic-notices">{"".join(rows)}</ul></body></html>'


class OfficialSourceIndexTests(unittest.TestCase):
    def setUp(self):
        self.shape = index.IndexShape("tjzyefy", SOURCE_INDEXES["tjzyefy"], "ul", "synthetic-notices")
        self.guards = []
        for name in ("connect", "connect_ex"):
            guard = patch.object(socket.socket, name, side_effect=AssertionError("OFFLINE_NETWORK_FORBIDDEN"))
            guard.start()
            self.addCleanup(guard.stop)

    def page(self, html, *, stage="tjzyefy", url=None):
        return OfficialPage(stage, url or SOURCE_INDEXES[stage], html, hashlib.sha256(html.encode()).hexdigest(), OBSERVED)

    def verify(self, html, *, shape=None):
        shape = shape or self.shape
        return index.verify_single_page_window(self.page(html, stage=shape.stage), shape, start_date=START, end_date=END)

    def test_all_official_contracts_start_unregistered(self):
        page = self.page(fixture(anchor(date(2026, 8, 1))))
        for stage in SOURCE_INDEXES:
            with self.subTest(stage=stage), self.assertRaisesRegex(index.OfficialIndexError, "CONTRACT_UNVERIFIED"):
                index.registered_index_contract(stage)
        with self.assertRaisesRegex(index.OfficialIndexError, "CONTRACT_UNVERIFIED"):
            index.verify_registered_source_window(page, start_date=START, end_date=END)

    def test_boundary_is_checked_on_all_notices_including_non_medical(self):
        raw = fixture(anchor(date(2026, 9, 28), title="医疗设备调研公告", number="1"),
                      anchor(START, title="数据安全服务项目", number="2"))
        window = self.verify(raw)
        self.assertIn("数据安全服务项目", window.scoped_html)
        self.assertEqual(window.start_date, START)
        self.assertEqual(window.raw_html_sha256, hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(window.scoped_html_sha256, hashlib.sha256(window.scoped_html.encode()).hexdigest())

    def test_old_sidebar_link_cannot_prove_list_coverage(self):
        raw = fixture(anchor(date(2026, 9, 28)), outside=anchor(date(2026, 1, 1)))
        with self.assertRaisesRegex(index.OfficialIndexError, "WINDOW_NOT_COVERED"):
            self.verify(raw)

    def test_scoped_html_excludes_sidebar_fact_candidates(self):
        raw = fixture(anchor(START), outside=anchor(date(2026, 9, 27), title="侧栏医疗设备调研", number="sidebar"))
        scoped = self.verify(raw).scoped_html
        self.assertNotIn("侧栏", scoped)
        self.assertNotIn("sidebar", scoped)

    def test_no_next_page_link_is_not_end_of_archive_evidence(self):
        with self.assertRaisesRegex(index.OfficialIndexError, "WINDOW_NOT_COVERED"):
            self.verify(fixture(anchor(date(2026, 9, 28))))

    def test_empty_missing_duplicate_and_unclosed_lists_are_unknown(self):
        row = anchor(START)
        pages = ["<html>login</html>", fixture(), fixture(row) + fixture(row),
                 '<ul id="synthetic-notices">' + row,
                 '<ul id="synthetic-notices" id="synthetic-notices">' + row + '</ul>',
                 fixture('<li>unlinked date</li>'), fixture('<div>' + row + '</div>')]
        for html in pages:
            with self.subTest(html=html), self.assertRaises(index.OfficialIndexError):
                self.verify(html)

    def test_duplicate_identity_and_reverse_order_are_rejected(self):
        duplicate = fixture(anchor(START), anchor(START, host="tjzyefy.com"))
        reverse = fixture(anchor(START), anchor(date(2026, 9, 28), number="2"))
        for html in (duplicate, reverse):
            with self.subTest(html=html), self.assertRaises(index.OfficialIndexError):
                self.verify(html)

    def test_same_day_different_notices_and_nested_text_are_supported(self):
        rows = [anchor(START, title="<span>公告</span><br/>设备", number=str(n)) for n in (1, 2)]
        self.assertIn("公告 设备", self.verify(fixture(*rows)).scoped_html)

    def test_foreign_or_non_detail_link_is_rejected(self):
        for row in ('<li><a href="https://evil.example/system/2026/08/31/1.shtml">notice</a></li>',
                    '<li><a href="/xwgg/ggtz/">notice</a></li>'):
            with self.assertRaises(ValueError):
                self.verify(fixture(row))

    def test_page_identity_hash_date_and_clock_are_bound(self):
        page = self.page(fixture(anchor(START)))
        for invalid in (replace(page, stage="tjzxfc"), replace(page, html_sha256="bad"),
                        replace(page, observed_at=OBSERVED.replace(tzinfo=None)),
                        replace(page, url=page.url + "?page=1")):
            with self.subTest(page=invalid), self.assertRaises(index.OfficialIndexError):
                index.verify_single_page_window(invalid, self.shape, start_date=START, end_date=END)
        with self.assertRaisesRegex(index.OfficialIndexError, "WINDOW_UNVERIFIED"):
            index.verify_single_page_window(page, self.shape, start_date=END, end_date=START)

    def test_future_notice_does_not_create_coverage_proof(self):
        with self.assertRaisesRegex(index.OfficialIndexError, "FUTURE_NOTICE"):
            self.verify(fixture(anchor(date(2026, 10, 1)), anchor(START, number="2")))

    def test_fixture_registry_requires_matching_file_hash_and_safe_path(self):
        raw = fixture(anchor(START))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.html"
            path.write_text(raw)
            evidence = index.CapturedIndexEvidence(path.name, hashlib.sha256(path.read_bytes()).hexdigest(), self.shape.index_url, OBSERVED)
            contract = index.ReviewedIndexContract(self.shape, evidence)
            # Explicit test-only registry injection. This is NOT an official registration.
            with patch.object(index, "FIXTURE_ROOT", Path(directory)), \
                 patch.object(index, "_REGISTERED_INDEX_CONTRACTS", {"tjzyefy": contract}):
                self.assertIs(index.registered_index_contract("tjzyefy"), contract)
                path.write_text(raw + "<!--changed-->")
                with self.assertRaisesRegex(index.OfficialIndexError, "CAPTURE_INVALID"):
                    index.registered_index_contract("tjzyefy")
                bad = replace(contract, capture=replace(evidence, path="../outside.html"))
                with patch.object(index, "_REGISTERED_INDEX_CONTRACTS", {"tjzyefy": bad}):
                    with self.assertRaisesRegex(index.OfficialIndexError, "CAPTURE_INVALID"):
                        index.registered_index_contract("tjzyefy")
        self.assertEqual(len(index._REGISTERED_INDEX_CONTRACTS), 0)

    def test_scoped_mock_window_can_feed_existing_offline_core_without_resetting_budget(self):
        raw_index, pages, index_url = core_tests.synthetic_case("tjzyefy")
        raw = fixture('<li>' + raw_index + '</li>', anchor(START, title="非医疗旧公告", number="old"))
        # The second notice has a synthetic numeric stable ID, as on official paths.
        raw = raw.replace('/old.shtml', '/111.shtml')
        scoped = self.verify(raw)
        proof = runtime.OfficialSourceWindowProof("tjzyefy", index_url, scoped.scoped_html_sha256,
            scoped.start_date, scoped.end_date, scoped.observed_at)
        with patch.object(runtime.time, "monotonic", return_value=10), \
             patch.object(runtime, "_official_source_cycle", return_value="offline-cycle"), \
             patch.object(runtime, "_official_source_records", return_value=[]), \
             patch.object(runtime, "_cycle_as_of", return_value=core_tests.AS_OF), \
             patch.object(runtime, "_now_utc", return_value=core_tests.OBSERVED):
            prepared = runtime._prepare_official_source_refresh(None, {}, "tjzyefy", index_html=scoped.scoped_html,
                window=proof, read_detail=lambda url, deadline: pages[url], work_deadline=30)
        self.assertEqual(prepared.deadline, 30)
        self.assertEqual(json.loads(prepared.result_json)["verified_record_count"], 1)
