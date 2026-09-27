"""Behavioral tests for the Tianjin official-site early-signal stages.

tjzxfc (in-hospital sourcing / market research), tjzyefy (in-hospital research)
and tjzyefy_intent (procurement intent) are the three Tianjin sources the
GitHub refresh publishes but the Vercel deep cycle used to omit, so a Vercel
publish silently dropped every PRE_MARKET_SIGNAL / PROCUREMENT_INTENT card.

The tests drive the real ``collector_runtime`` against the in-memory ``vercel``
stub (tests/_stubs) and a synthetic ``OfficialSiteSource`` whose fetch/parse
callables are plain Python functions, so no network is touched.
"""

from __future__ import annotations

import json
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_ROOT = Path(__file__).resolve().parent
WEB_ROOT = TESTS_ROOT.parents[1]
STUBS = TESTS_ROOT / "_stubs"

for entry in (str(STUBS), str(WEB_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from vercel import functions as fake_cache  # noqa: E402

import collector_queue  # noqa: E402,F401  (applies the v2 namespace to the runtime)
import collector_namespace as ns  # noqa: E402
import collector_runtime as rt  # noqa: E402
from vercel.functions import RuntimeCache  # noqa: E402

CYCLE_AS_OF = datetime(2026, 9, 27, 5, 52, tzinfo=timezone.utc)  # 13:52 Asia/Shanghai
DATA_ROOT = WEB_ROOT / "pipeline" / "data"


class FakeParseError(ValueError):
    pass


def _candidate(n: int, published: str = "2026-09-20") -> SimpleNamespace:
    return SimpleNamespace(
        title=f"设备需求调研 {n}",
        detail_url=f"https://www.example-hospital.cn/notice/{published.replace('-', '')}/{n}.html",
        published_at=published,
    )


_TEMPLATE_RECORD = json.loads((DATA_ROOT / "tianjin_live_tjzyefy_records.json").read_text(encoding="utf-8"))[0]


def _record(opportunity_id: str, *, title: str = "设备需求调研") -> dict:
    """A schema-valid canonical record (merge_canonical_records validates strictly)."""
    record = json.loads(json.dumps(_TEMPLATE_RECORD))
    record["opportunity_id"] = opportunity_id
    record["facts"]["project_name"] = title
    return record


class FakeSite:
    """Scriptable official website: index candidates + per-URL detail behaviour."""

    def __init__(self, candidates: list[SimpleNamespace]) -> None:
        self.candidates = candidates
        self.detail_behaviour: dict[str, object] = {}
        self.fetch_calls: list[str] = []
        self.index_url = "https://www.example-hospital.cn/notice/"
        self.transient_failures: dict[str, int] = {}

    def fetch_page(self, url: str, *, timeout_seconds: int) -> str:
        self.fetch_calls.append(url)
        assert timeout_seconds == rt.SOURCE_REQUEST_TIMEOUT_SECONDS
        remaining = self.transient_failures.get(url, 0)
        if remaining > 0:
            self.transient_failures[url] = remaining - 1
            raise RuntimeError("FAKE_HTTP_503")
        return f"<html>{url}</html>"

    def parse_index(self, html: str) -> list[SimpleNamespace]:
        assert html.endswith(f"{self.index_url}</html>")
        return list(self.candidates)

    @staticmethod
    def select_candidates(candidates, *, start_date, end_date, max_candidates):
        selected = [c for c in candidates if start_date <= datetime.fromisoformat(c.published_at).date() <= end_date]
        return selected[:max_candidates]

    def parse_detail(self, html: str, *, source_url: str, index_url: str, index_published_at: str, expected_title: str, observed_at: str, opportunity_id: str) -> dict:
        assert index_url == self.index_url
        assert observed_at == CYCLE_AS_OF.isoformat()
        behaviour = self.detail_behaviour.get(source_url)
        if isinstance(behaviour, Exception):
            raise behaviour
        return _record(opportunity_id, title=expected_title)

    @staticmethod
    def opportunity_id(detail_url: str) -> str:
        return "fake_" + detail_url.rsplit("/", 1)[-1].removesuffix(".html")

    @staticmethod
    def is_retryable_fetch_error(exc: Exception) -> bool:
        return str(exc) == "FAKE_HTTP_503"


def _source_for(site: FakeSite, *, stage: str = "tjzxfc") -> rt.OfficialSiteSource:
    return replace(
        rt.OFFICIAL_SITE_SOURCES[stage],
        index_url=site.index_url,
        fetch_page=site.fetch_page,
        parse_index=site.parse_index,
        select_candidates=site.select_candidates,
        parse_detail=site.parse_detail,
        opportunity_id=site.opportunity_id,
        parse_error=FakeParseError,
        unsupported_codes=frozenset({"FAKE_NON_MEDICAL"}),
        is_retryable_fetch_error=site.is_retryable_fetch_error,
    )


class OfficialSiteStageTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_cache.reset_store()
        self.cache = RuntimeCache()
        self.state = {"local_date": "2026-09-27", "cycle_as_of": CYCLE_AS_OF.isoformat(), "stages": {}}
        self.sleeps: list[float] = []
        self._patches = [
            mock.patch.object(rt, "_sleep", lambda seconds: self.sleeps.append(seconds)),
        ]
        for patch in self._patches:
            patch.start()
        rt._begin_stage_budget(None)

    def tearDown(self) -> None:
        for patch in reversed(self._patches):
            patch.stop()

    # ------------------------------------------------------------------ wiring
    def test_three_tianjin_sources_are_deep_cycle_stages_before_the_regional_chain(self) -> None:
        order = rt.STAGE_ORDER
        for stage in ("tjzxfc", "tjzyefy", "tjzyefy_intent"):
            self.assertIn(stage, order)
            self.assertIn(stage, rt.OFFICIAL_SITE_SOURCES)
            self.assertLess(order.index("tjfch"), order.index(stage))
            self.assertLess(order.index(stage), order.index("regional_bj"))
            # Output keys live in the isolated v2 namespace like every other stage.
            (key,) = rt._stage_output_keys(stage)
            self.assertTrue(key.endswith(":v2"), key)
            self.assertEqual(key, getattr(ns, rt.OFFICIAL_SITE_SOURCES[stage].records_key_name))
        self.assertEqual(rt.OFFICIAL_SITE_SOURCES["tjzyefy_intent"].parse_detail, rt.parse_tjzyefy_procurement_intent)
        self.assertEqual(rt.OFFICIAL_SITE_SOURCES["tjzxfc"].parse_detail, rt.parse_tjzxfc_market_research)
        self.assertEqual(rt.OFFICIAL_SITE_SOURCES["tjzyefy"].parse_detail, rt.parse_tjzyefy_market_research)
        # Bootstrap files exist and are the same live files the GitHub refresh maintains.
        for source in rt.OFFICIAL_SITE_SOURCES.values():
            self.assertTrue((DATA_ROOT / source.bootstrap_file).is_file(), source.bootstrap_file)

    def test_real_sources_share_the_github_sync_window_and_unsupported_codes(self) -> None:
        self.assertEqual((rt.OFFICIAL_SITE_LOOKBACK_DAYS, rt.OFFICIAL_SITE_MAX_CANDIDATES), (30, 20))
        self.assertIn("TJZXFC_NON_MEDICAL_EARLY_SIGNAL", rt.OFFICIAL_SITE_SOURCES["tjzxfc"].unsupported_codes)
        self.assertIn("TJZYEFY_NON_MEDICAL_RESEARCH", rt.OFFICIAL_SITE_SOURCES["tjzyefy"].unsupported_codes)
        self.assertIn("TJZYEFY_INTENT_NON_MEDICAL", rt.OFFICIAL_SITE_SOURCES["tjzyefy_intent"].unsupported_codes)

    # ------------------------------------------------------------------ behaviour
    def test_first_run_bootstraps_from_the_bundled_live_records_then_merges_new_ones(self) -> None:
        site = FakeSite([_candidate(1), _candidate(2)])
        source = _source_for(site, stage="tjzyefy_intent")
        bundled = json.loads((DATA_ROOT / source.bootstrap_file).read_text(encoding="utf-8"))
        self.assertGreater(len(bundled), 0)

        result = rt._run_official_site_stage(self.cache, self.state, source)

        self.assertTrue(result["bootstrapped_records"])
        self.assertEqual(result["new_verified_record_count"], 2)
        self.assertEqual(result["merged_record_count"], len(bundled) + 2)
        self.assertEqual(result["publish_gate_reason"], "PASS")
        stored = self.cache.get(source.records_key())
        self.assertEqual(len(stored), len(bundled) + 2)
        self.assertEqual(source.records_key(), ns.TJZYEFY_INTENT_RECORDS_KEY)
        self.assertEqual(self.sleeps, [rt.OFFICIAL_SITE_REQUEST_DELAY_SECONDS] * 2)

    def test_candidates_outside_the_lookback_window_are_not_fetched(self) -> None:
        site = FakeSite([_candidate(1, "2026-09-26"), _candidate(2, "2026-08-01")])
        source = _source_for(site)
        self.cache.set(source.records_key(), [])
        result = rt._run_official_site_stage(self.cache, self.state, source)
        self.assertEqual(result["selected_candidate_count"], 1)
        self.assertEqual([u for u in site.fetch_calls if u != site.index_url], [site.candidates[0].detail_url])

    def test_unsupported_notice_is_skipped_as_an_explicit_non_fact(self) -> None:
        site = FakeSite([_candidate(1), _candidate(2)])
        site.detail_behaviour[site.candidates[0].detail_url] = FakeParseError("FAKE_NON_MEDICAL")
        source = _source_for(site)
        self.cache.set(source.records_key(), [])
        result = rt._run_official_site_stage(self.cache, self.state, source)
        self.assertEqual(result["unsupported_candidate_count"], 1)
        self.assertEqual(result["new_verified_record_count"], 1)
        self.assertEqual([r["opportunity_id"] for r in self.cache.get(source.records_key())], ["fake_2"])

    def test_unresolved_verification_failure_blocks_the_source_without_touching_canonical_state(self) -> None:
        site = FakeSite([_candidate(1), _candidate(2)])
        site.detail_behaviour[site.candidates[1].detail_url] = FakeParseError("FAKE_TEMPLATE_CHANGED")
        source = _source_for(site)
        self.cache.set(source.records_key(), [_record("fake_existing")])
        with self.assertRaises(rt.CollectorStageBlocked) as ctx:
            rt._run_official_site_stage(self.cache, self.state, source)
        self.assertTrue(str(ctx.exception).startswith("TJZXFC_CANDIDATE_VERIFICATION_INCOMPLETE:1:FakeParseError:FAKE_TEMPLATE_CHANGED"))
        self.assertEqual([r["opportunity_id"] for r in self.cache.get(source.records_key())], ["fake_existing"])

    def test_failure_on_an_already_verified_notice_is_resolved_by_canonical_state(self) -> None:
        site = FakeSite([_candidate(1), _candidate(2)])
        site.detail_behaviour[site.candidates[1].detail_url] = RuntimeError("FAKE_HTTP_500")
        source = _source_for(site)
        self.cache.set(source.records_key(), [_record("fake_2")])
        result = rt._run_official_site_stage(self.cache, self.state, source)
        self.assertEqual(result["resolved_failure_count"], 1)
        self.assertEqual(result["failure_count"], 0)
        self.assertEqual(sorted(r["opportunity_id"] for r in self.cache.get(source.records_key())), ["fake_1", "fake_2"])

    def test_transient_fetch_errors_are_retried_once_within_the_budget(self) -> None:
        site = FakeSite([_candidate(1)])
        site.transient_failures[site.index_url] = 1
        site.transient_failures[site.candidates[0].detail_url] = 1
        source = _source_for(site)
        self.cache.set(source.records_key(), [])
        result = rt._run_official_site_stage(self.cache, self.state, source)
        self.assertEqual(result["new_verified_record_count"], 1)
        self.assertEqual(site.fetch_calls.count(site.index_url), 2)
        self.assertEqual(site.fetch_calls.count(site.candidates[0].detail_url), 2)

        # A second transient failure is not retried forever.
        site2 = FakeSite([_candidate(1)])
        site2.transient_failures[site2.index_url] = 5
        with self.assertRaises(rt.CollectorStageBlocked) as ctx:
            rt._run_official_site_stage(self.cache, self.state, _source_for(site2))
        self.assertTrue(str(ctx.exception).startswith("TJZXFC_INDEX_DISCOVERY_FAILED:RuntimeError:FAKE_HTTP_503"))
        self.assertEqual(len(site2.fetch_calls), rt.OFFICIAL_SITE_FETCH_ATTEMPTS)

    def test_budget_exhaustion_commits_verified_records_and_defers_the_rest(self) -> None:
        site = FakeSite([_candidate(n) for n in range(1, 6)])
        source = _source_for(site)
        self.cache.set(source.records_key(), [])
        verified = 0

        original_parse = site.parse_detail

        def parse_then_exhaust(html, **kwargs):
            nonlocal verified
            verified += 1
            if verified == 2:
                rt._begin_stage_budget(0)  # the budget runs out after the 2nd detail
            return original_parse(html, **kwargs)

        source = replace(source, parse_detail=parse_then_exhaust)
        result = rt._run_official_site_stage(self.cache, self.state, source)
        self.assertEqual(result["new_verified_record_count"], 2)
        self.assertEqual(result["deferred_candidate_count"], 3)
        self.assertEqual(len(self.cache.get(source.records_key())), 2)

        # Nothing attempted at all -> explicit failure, no canonical write.
        rt._begin_stage_budget(0)
        site3 = FakeSite([_candidate(1)])
        source3 = _source_for(site3, stage="tjzyefy")
        self.cache.set(source3.records_key(), [])
        with self.assertRaises(rt.CollectorStageBlocked) as ctx:
            rt._run_official_site_stage(self.cache, self.state, source3)
        self.assertEqual(str(ctx.exception), "COLLECTOR_STAGE_BUDGET_EXHAUSTED:tjzyefy:detail")
        self.assertEqual(self.cache.get(source3.records_key()), [])

    def test_missing_output_of_a_completed_official_site_stage_is_replayed(self) -> None:
        cache = self.cache
        for key in (rt.CCGP_RECORDS_KEY, rt.CCGP_EVENTS_KEY, rt.CCGP_WATCH_KEY, rt.TJMUGH_RECORDS_KEY, rt.TJNOTHOP_RECORDS_KEY, rt.TEDA_RECORDS_KEY, rt.TJFCH_RECORDS_KEY):
            cache.set(key, [])
        state = {
            "schema_version": "0.1", "local_date": "2026-09-27", "cycle_as_of": CYCLE_AS_OF.isoformat(),
            "stages": {stage: {"status": "COMPLETED", "attempt_count": 1} for stage in rt.STAGE_ORDER[: rt.STAGE_ORDER.index("tjzxfc") + 1]},
        }
        ns.write_collector_state(cache, state, now=CYCLE_AS_OF)
        # tjzxfc says COMPLETED but its canonical key evaporated from Runtime Cache.
        prepared, previous = rt._prepare_stage(cache, "tjzxfc", CYCLE_AS_OF, CYCLE_AS_OF)
        self.assertIsNone(previous)
        stage = prepared["stages"]["tjzxfc"]
        self.assertEqual(stage["status"], "RUNNING")
        self.assertEqual(stage["attempt_count"], 1)
        self.assertEqual(stage["replay_reason"], "COLLECTOR_STAGE_OUTPUT_MISSING:collector-tjzxfc-records:v2")


class PublishIncludesOfficialSiteSourcesTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_cache.reset_store()
        self.cache = RuntimeCache()
        self.state = {"local_date": "2026-09-27", "cycle_as_of": CYCLE_AS_OF.isoformat(), "stages": {}}
        for key in (rt.CCGP_RECORDS_KEY, rt.CCGP_EVENTS_KEY, rt.TJMUGH_RECORDS_KEY, rt.TJNOTHOP_RECORDS_KEY, rt.TEDA_RECORDS_KEY, rt.TJFCH_RECORDS_KEY):
            self.cache.set(key, [])
        for market in rt.REGIONAL_STAGE_MARKET_CODES.values():
            self.cache.set(rt._regional_records_key(market), [])
        self._patches = [
            mock.patch.object(rt, "_publish_regression_gate", lambda snapshot: {"decision": "BYPASSED"}),
            mock.patch.object(rt, "_persist_verified_snapshot_durably", lambda snapshot: {"status": "STORED"}),
        ]
        for patch in self._patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in reversed(self._patches):
            patch.stop()

    def test_publish_refuses_to_run_without_the_official_site_canonical_state(self) -> None:
        with self.assertRaises(rt.CollectorPrecondition) as ctx:
            rt._run_publish(self.cache, self.state)
        self.assertEqual(str(ctx.exception), "COLLECTOR_CANONICAL_STATE_INCOMPLETE:tjzxfc,tjzyefy,tjzyefy_intent")

    def test_published_pool_carries_the_tianjin_procurement_intent_signals(self) -> None:
        intents = json.loads((DATA_ROOT / "tianjin_live_tjzyefy_intent_records.json").read_text(encoding="utf-8"))
        research = json.loads((DATA_ROOT / "tianjin_live_tjzyefy_records.json").read_text(encoding="utf-8"))
        self.cache.set(rt.TJZXFC_RECORDS_KEY, [])
        self.cache.set(rt.TJZYEFY_RECORDS_KEY, research)
        self.cache.set(rt.TJZYEFY_INTENT_RECORDS_KEY, intents)

        result = rt._run_publish(self.cache, self.state)

        self.assertEqual(result["canonical_record_count"], len(intents) + len(research))
        snapshot = self.cache.get(rt.LATEST_RUNTIME_SNAPSHOT_KEY)
        pool = snapshot["opportunity_pool"]
        intent_ids = {record["opportunity_id"] for record in intents}
        published_intents = [card for card in pool if card["opportunity_id"] in intent_ids]
        self.assertEqual(len(published_intents), len(intents))
        for card in published_intents:
            self.assertEqual(card["facts"]["lifecycle_state"], "PROCUREMENT_INTENT")
            self.assertEqual(card["recommendation_mode"], "PRE_MARKET_SIGNAL")
            self.assertTrue(card["evidence_source_urls"][0].startswith("https://www.tjzyefy.com/"))


if __name__ == "__main__":
    unittest.main()
