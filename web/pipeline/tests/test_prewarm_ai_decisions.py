from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"
sys.path.insert(0, str(SCRIPTS))

import prewarm_ai_decisions as prewarm  # noqa: E402


class _Response:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Opener:
    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    def open(self, request, timeout):  # noqa: A003 - urllib opener interface
        self.requests.append(request)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return _Response(result)


def _round(generated: int, remaining: int, cached: int = 0, errors: int = 0) -> dict:
    return {
        "mode": "PREWARM",
        "candidate_count": 40,
        "already_cached_count": cached,
        "generated_count": generated,
        "error_count": errors,
        "remaining_miss_count": remaining,
    }


class PrewarmAiDecisionsTests(unittest.TestCase):
    def run_prewarm(self, opener, rounds=5):
        return prewarm.run(
            url="https://example.test/api/ai/analyze",
            token="secret-token",
            rounds=rounds,
            limit=10,
            max_candidates=40,
            timeout=5,
            pause_seconds=0,
            opener=opener,
            sleep=lambda _: None,
        )

    def test_url_must_be_https_and_gets_route(self) -> None:
        self.assertEqual(
            prewarm.validate_url("https://example.test/api/ai/analyze"),
            "https://example.test/api/ai/analyze?route=prewarm",
        )
        self.assertEqual(
            prewarm.validate_url("https://example.test/api/ai/analyze?route=prewarm"),
            "https://example.test/api/ai/analyze?route=prewarm",
        )
        with self.assertRaises(prewarm.PrewarmError):
            prewarm.validate_url("http://example.test/api/ai/analyze")
        with self.assertRaises(prewarm.PrewarmError):
            prewarm.validate_url("https://user:pw@example.test/api/ai/analyze")

    def test_token_prefers_dedicated_secret_then_publisher(self) -> None:
        self.assertEqual(
            prewarm.resolve_token({"AI_PREWARM_TOKEN": "a", "VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "b"}), "a"
        )
        self.assertEqual(prewarm.resolve_token({"AI_PREWARM_TOKEN": " ", "VERIFIED_SNAPSHOT_PUBLISH_TOKEN": "b"}), "b")
        with self.assertRaises(prewarm.PrewarmError):
            prewarm.resolve_token({})

    def test_loops_until_nothing_remains(self) -> None:
        opener = _Opener([_round(10, 15, cached=5), _round(10, 5), _round(5, 0)])
        totals = self.run_prewarm(opener)
        self.assertEqual(totals["rounds"], 3)
        self.assertEqual(totals["generated"], 25)
        self.assertEqual(totals["remaining"], 0)
        request = opener.requests[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        self.assertEqual(json.loads(request.data), {"limit": 10, "max_candidates": 40})

    def test_stops_when_a_round_makes_no_progress(self) -> None:
        opener = _Opener([_round(0, 12, errors=10), _round(10, 0)])
        totals = self.run_prewarm(opener)
        self.assertEqual(totals["rounds"], 1)
        self.assertEqual(len(opener.requests), 1)

    def test_respects_round_budget(self) -> None:
        opener = _Opener([_round(10, 50)] * 3)
        totals = self.run_prewarm(opener, rounds=3)
        self.assertEqual(totals["rounds"], 3)

    def test_http_error_is_reported_without_token(self) -> None:
        error = urllib.error.HTTPError(
            "https://example.test", 401, "no", {}, io.BytesIO(b'{"error":"PREWARM_UNAUTHORIZED"}')
        )
        with self.assertRaises(prewarm.PrewarmError) as ctx:
            self.run_prewarm(_Opener([error]))
        self.assertIn("PREWARM_HTTP_401:PREWARM_UNAUTHORIZED", str(ctx.exception))
        self.assertNotIn("secret-token", str(ctx.exception))

    def test_rejects_non_prewarm_response(self) -> None:
        with self.assertRaises(prewarm.PrewarmError):
            self.run_prewarm(_Opener([{"mode": "BATCH"}]))

    def test_main_is_best_effort_unless_strict(self) -> None:
        import os

        saved = {name: os.environ.pop(name, None) for name in prewarm.TOKEN_ENV_NAMES}
        try:
            self.assertEqual(prewarm.main(["--rounds", "1"]), 0)
            self.assertEqual(prewarm.main(["--rounds", "1", "--strict"]), 2)
        finally:
            for name, value in saved.items():
                if value is not None:
                    os.environ[name] = value

    def test_refresh_workflows_prewarm_after_publish_without_failing_refresh(self) -> None:
        # Both refresh workflows prewarm after publishing; the step must never
        # fail the refresh (see docs/ops/MCAI-PERF-001-2026-09-28.md).
        wired = 0
        for name in ("regional-medical-refresh.yml", "tianjin-medical-refresh.yml"):
            source = (WORKFLOWS / name).read_text(encoding="utf-8")
            marker = "prewarm_ai_decisions.py"
            if marker not in source:
                continue
            wired += 1
            step = source.rindex("- name:", 0, source.index(marker))
            self.assertLess(source.index("Publish and verify optional external snapshot"), step)
            block = source[step : source.index(marker) + len(marker)]
            self.assertIn("continue-on-error: true", block)
        self.assertEqual(wired, 2, "both refresh workflows must prewarm AI decisions")

    def test_workflow_snippet_is_documented(self) -> None:
        doc = (WORKFLOWS.parents[1] / "docs" / "ops" / "MCAI-PERF-001-2026-09-28.md").read_text(encoding="utf-8")
        self.assertIn("prewarm_ai_decisions.py", doc)
        self.assertIn("continue-on-error: true", doc)

if __name__ == "__main__":
    unittest.main()
