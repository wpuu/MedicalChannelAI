"""No source HTTP: mocked responses and real local-only child cancellation."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from email.message import Message
from io import StringIO
import json
import hashlib
from pathlib import Path
import signal
import socket
import ssl
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import test_twice_daily_source_parity as core_tests
from test_collector_native_reliability import runtime
import collector_official_transport as transport


URL = transport.SOURCE_INDEXES["tjzyefy"]
WEB = Path(__file__).resolve().parents[2]


class Response:
    status = 200
    def __init__(self, body=b"<html>fixture</html>", *, url=URL, content_type="text/html; charset=utf-8", length=None, encoding=None):
        self.body, self.url = body, url
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if length is not None:
            self.headers["Content-Length"] = str(length)
        if encoding is not None:
            self.headers["Content-Encoding"] = encoding
        self.read = Mock(side_effect=lambda count: self.body[:count])
    def geturl(self):
        return self.url
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False


class OfficialSourceTransportTests(unittest.TestCase):
    def setUp(self):
        for method in ("connect", "connect_ex"):
            guard = patch.object(socket.socket, method, side_effect=AssertionError("OFFLINE_NETWORK_FORBIDDEN"))
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch.object(socket, "create_connection", side_effect=AssertionError("OFFLINE_NETWORK_FORBIDDEN"))
        guard.start()
        self.addCleanup(guard.stop)

    def worker(self, response):
        with patch.object(transport, "build_opener", return_value=Mock(open=Mock(return_value=response))):
            return transport._worker_fetch("tjzyefy", URL, time.monotonic() + 10)

    def test_existing_allowlists_and_indexes_are_preserved(self):
        for stage in transport.SOURCE_INDEXES:
            adapter, *_ = runtime._official_source_adapter(stage)
            self.assertEqual(transport.SOURCE_INDEXES[stage], adapter.INDEX_URL)
            self.assertEqual(transport.SOURCE_HOSTS[stage], adapter.ALLOWED_HOSTS)

    def test_rejects_nonofficial_credentialed_plaintext_or_unknown_routes(self):
        urls = [
            "http://www.tjzyefy.com/xwgg/ggtz/", "https://evil.example/xwgg/ggtz/",
            "https://user:pass@www.tjzyefy.com/xwgg/ggtz/", URL + "?token=x",
            URL + "#fragment", "https://www.tjzyefy.com:444/xwgg/ggtz/",
            "https://www.tjzyefy.com/system/2026/02/31/1.shtml", URL + "index_1.shtml",
            URL + "\r\nheader", "https://www.tjzxfc.cn/system/2026/09/28/123.shtml",
        ]
        with patch.object(transport.subprocess, "Popen") as spawn:
            for url in urls:
                with self.subTest(url=url), self.assertRaisesRegex(transport.OfficialFetchError, "URL_REJECTED"):
                    transport.fetch_official_page("tjzyefy", url, deadline=time.monotonic() + 20)
            spawn.assert_not_called()

    def test_redirect_is_validated_before_following(self):
        redirect = transport._OfficialRedirects("tjzyefy")
        for target in ("https://evil.example/", "http://www.tjzyefy.com/xwgg/ggtz/"):
            with self.assertRaisesRegex(transport.OfficialFetchError, "URL_REJECTED"):
                redirect.redirect_request(None, None, 302, "", {}, target)

    def test_redirect_total_is_bounded_even_for_repeated_urls(self):
        from urllib.request import Request
        redirect = transport._OfficialRedirects("tjzyefy")
        req = Request(URL)
        for _ in range(3):
            redirect.redirect_request(req, None, 302, "", {}, URL)
        with self.assertRaisesRegex(transport.OfficialFetchError, "REDIRECT_LIMIT"):
            redirect.redirect_request(req, None, 302, "", {}, URL)

    def test_worker_reads_bounded_bytes_without_app_credentials(self):
        response = Response()
        result = self.worker(response)
        self.assertEqual(result["html"], "<html>fixture</html>")
        response.read.assert_called_once_with(transport.MAX_PAGE_BYTES + 1)

    def test_rejects_response_type_encoding_empty_and_oversize(self):
        responses = [
            Response(content_type="application/json"), Response(encoding="gzip"),
            Response(body=b""), Response(body=b"x" * (transport.MAX_PAGE_BYTES + 1)),
            Response(length=transport.MAX_PAGE_BYTES + 1), Response(length="invalid"), Response(length="1" * 5000),
            Response(content_type="text/html; charset=unknown"), Response(body=b"\xff"),
            Response(url="https://evil.example/"),
        ]
        for response in responses:
            with self.subTest(headers=response.headers), self.assertRaises(transport.OfficialFetchError):
                self.worker(response)

    def test_worker_network_errors_have_bounded_retry_categories(self):
        errors = [
            (HTTPError(URL, 503, "", None, None), True),
            (HTTPError(URL, 403, "", None, None), False),
            (URLError("temporary"), True),
            (URLError(ssl.SSLCertVerificationError("certificate")), False),
        ]
        for error, retryable in errors:
            with self.subTest(error=error), patch.object(transport, "build_opener", return_value=Mock(open=Mock(side_effect=error))):
                with self.assertRaises(transport.OfficialFetchError) as caught:
                    transport._worker_fetch("tjzyefy", URL, time.monotonic() + 10)
                self.assertIs(caught.exception.retryable, retryable)

    def test_successful_child_envelope_is_strictly_parsed(self):
        envelope = {"ok": True, "html": "<html>offline</html>", "url": URL,
                    "observed_at": datetime.now(timezone.utc).isoformat()}
        with patch.object(transport, "_run_bounded_worker", return_value=json.dumps(envelope).encode()) as run:
            page = transport.fetch_official_page("tjzyefy", URL, deadline=time.monotonic() + 60)
        self.assertEqual(page.html, envelope["html"])
        self.assertEqual(run.call_args.args[0][1], "-I")
        self.assertLessEqual(run.call_args.args[1] - time.monotonic(), 20)
        for invalid in ({"ok": 1}, {**envelope, "url": "https://evil.example/"}, {**envelope, "observed_at": "not-a-time"}):
            with patch.object(transport, "_run_bounded_worker", return_value=json.dumps(invalid).encode()):
                with self.assertRaises(transport.OfficialFetchError):
                    transport.fetch_official_page("tjzyefy", URL, deadline=time.monotonic() + 20)

    def test_worker_main_uses_real_argument_layout_and_child_only_alarm(self):
        out = StringIO()
        with patch.object(sys, "argv", ["worker.py", "--fetch", "tjzyefy", URL, "20"]), \
             patch.object(transport.time, "monotonic", return_value=1), \
             patch.object(transport.signal, "signal") as set_handler, \
             patch.object(transport.signal, "setitimer") as alarm, \
             patch.object(transport, "_worker_fetch", return_value={"html": "fixture"}) as fetch, redirect_stdout(out):
            self.assertEqual(transport._worker_main(), 0)
        fetch.assert_called_once_with("tjzyefy", URL, 20)
        alarm.assert_called_once_with(signal.ITIMER_REAL, 19)
        set_handler.assert_called_once_with(signal.SIGALRM, signal.SIG_DFL)
        self.assertIs(json.loads(out.getvalue())["ok"], True)

    def run_local_hang(self, setup, marker):
        # Child code uses only stubbed operations; no source request is made.
        script = f"""
import sys,socket,time
sys.path.insert(0,{str(WEB)!r})
import collector_official_transport as m
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('OFFLINE_NETWORK_FORBIDDEN'))
socket.socket.connect_ex=socket.socket.connect
{setup}
m._worker_fetch('tjzyefy',{URL!r},time.monotonic()+30)
"""
        processes = []
        real_spawn = subprocess.Popen
        def spawn(*args, **kwargs):
            process = real_spawn(*args, **kwargs)
            processes.append(process)
            return process
        start = time.monotonic()
        with patch.object(transport.subprocess, "Popen", side_effect=spawn):
            with self.assertRaisesRegex(transport.OfficialFetchError, "REQUEST_DEADLINE") as caught:
                transport._run_bounded_worker([sys.executable, "-I", "-c", script], start + 1)
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())
        self.assertIsInstance(caught.exception.__cause__, subprocess.TimeoutExpired)
        self.assertIn(marker.encode(), caught.exception.__cause__.output or b"")

    def test_real_child_blocked_dns_is_killed_and_reaped(self):
        self.run_local_hang("socket.getaddrinfo=lambda *a,**k: (print('DNS_ENTERED',flush=True),time.sleep(30))[1]", "DNS_ENTERED")

    def test_real_child_blocked_body_read_is_killed_and_reaped(self):
        self.run_local_hang(f"""
from email.message import Message
class Response:
    status=200
    headers=Message()
    headers['Content-Type']='text/html; charset=utf-8'
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def geturl(self): return {URL!r}
    def read(self,*a):
        print('BODY_ENTERED',flush=True)
        time.sleep(30)
class Opener:
    def open(self,*a,**k): return Response()
m.build_opener=lambda *a: Opener()
""", "BODY_ENTERED")

    def test_child_self_alarm_is_classified_as_deadline(self):
        script = "import signal,time;signal.signal(signal.SIGALRM,signal.SIG_DFL);signal.setitimer(signal.ITIMER_REAL,0.1);time.sleep(30)"
        with self.assertRaisesRegex(transport.OfficialFetchError, "REQUEST_DEADLINE"):
            transport._run_bounded_worker([sys.executable, "-I", "-c", script], time.monotonic() + 2)

    def test_spawn_unavailable_and_expired_budget_do_not_fall_back_to_threads(self):
        with patch.object(transport.subprocess, "Popen", side_effect=OSError("not supported")):
            with self.assertRaisesRegex(transport.OfficialFetchError, "WORKER_UNAVAILABLE"):
                transport._run_bounded_worker(["fixed-worker"], time.monotonic() + 20)
        for deadline in (float("nan"), True, time.monotonic() - 1):
            with patch.object(transport.subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(transport.OfficialFetchError, "REQUEST_DEADLINE"):
                    transport._run_bounded_worker(["fixed-worker"], deadline)
                spawn.assert_not_called()

    def test_session_shares_index_retry_gap_and_detail_budget(self):
        now = [0.0]
        def sleep(seconds): now[0] += seconds
        page = transport.OfficialPage("tjzyefy", URL, "fixture", "hash", datetime.now(timezone.utc))
        def fetch(stage, url, *, deadline):
            self.assertEqual(deadline, 240)
            now[0] += 20
            return page
        with patch.object(transport.time, "monotonic", side_effect=lambda: now[0]), \
             patch.object(transport.time, "sleep", side_effect=sleep), \
             patch.object(transport, "fetch_official_page", side_effect=[transport.OfficialFetchError("OFFICIAL_HTTP_503", retryable=True), page]) as request:
            session = transport.OfficialFetchSession("tjzyefy")
            session.fetch(URL)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(now[0], 3)
            request.side_effect = fetch
            session.fetch("https://www.tjzyefy.com/system/2026/09/28/030199113.shtml")
            self.assertEqual(session.deadline, 240)
            self.assertEqual(now[0], 26)
            now[0] = 240
            with self.assertRaisesRegex(transport.OfficialFetchError, "BUDGET_EXHAUSTED"):
                session.fetch(URL)

    def test_permanent_error_is_not_retried(self):
        with patch.object(transport, "fetch_official_page", side_effect=transport.OfficialFetchError("OFFICIAL_HTTP_403")) as fetch:
            with self.assertRaisesRegex(transport.OfficialFetchError, "HTTP_403"):
                transport.OfficialFetchSession("tjzyefy").fetch(URL)
        self.assertEqual(fetch.call_count, 1)

    def test_prepare_keeps_prior_index_deadline_instead_of_resetting_budget(self):
        index, _, index_url = core_tests.synthetic_case("tjzyefy", title="数据安全服务项目调研公告")
        end = core_tests.AS_OF.date()
        window = runtime.OfficialSourceWindowProof("tjzyefy", index_url,
            hashlib.sha256(index.encode()).hexdigest(), end - timedelta(days=29), end, core_tests.OBSERVED)
        with patch.object(runtime.time, "monotonic", return_value=100), \
             patch.object(runtime, "_official_source_cycle", return_value="bound-cycle"), \
             patch.object(runtime, "_official_source_records", return_value=[]), \
             patch.object(runtime, "_cycle_as_of", return_value=core_tests.AS_OF), \
             patch.object(runtime, "_now_utc", return_value=core_tests.OBSERVED):
            prepared = runtime._prepare_official_source_refresh(None, {}, "tjzyefy", index_html=index,
                window=window, read_detail=Mock(), work_deadline=150)
        self.assertEqual(prepared.deadline, 150)
        for deadline in (float("inf"), float("nan"), True):
            with self.assertRaisesRegex(runtime.CollectorPrecondition, "DEADLINE_INVALID"):
                runtime._prepare_official_source_refresh(None, {}, "tjzyefy", index_html=index,
                    window=window, read_detail=Mock(), work_deadline=deadline)

    def test_parent_cleanup_on_cancellation_and_credentials_not_inherited(self):
        process = Mock()
        process.poll.return_value = None
        process.communicate.side_effect = [KeyboardInterrupt(), (b"", None)]
        with patch.dict(transport.os.environ, {"TEST_SECRET": "offline-secret", "DATABASE_URL": "offline-db"}), \
             patch.object(transport.subprocess, "Popen", return_value=process) as spawn:
            with self.assertRaises(KeyboardInterrupt):
                transport._run_bounded_worker(["fixed-worker"], time.monotonic() + 5)
        process.kill.assert_called_once()
        self.assertEqual(process.communicate.call_count, 2)
        self.assertNotIn("TEST_SECRET", spawn.call_args.kwargs["env"])
        self.assertNotIn("DATABASE_URL", spawn.call_args.kwargs["env"])

    def test_process_start_cost_counts_towards_deadline(self):
        now = [0.0]
        process = Mock()
        process.poll.return_value = None
        process.communicate.return_value = (b"", None)
        def spawn(*a, **k):
            now[0] = 2
            return process
        with patch.object(transport.time, "monotonic", side_effect=lambda: now[0]), \
             patch.object(transport.subprocess, "Popen", side_effect=spawn):
            with self.assertRaisesRegex(transport.OfficialFetchError, "REQUEST_DEADLINE"):
                transport._run_bounded_worker(["fixed-worker"], 1)
        process.kill.assert_called_once()

    def test_cleanup_failure_is_reported_and_not_retryable_success(self):
        process = Mock()
        process.poll.return_value = None
        process.communicate.side_effect = subprocess.TimeoutExpired(["worker"], 1)
        with patch.object(transport.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(transport.OfficialFetchError, "CLEANUP_FAILED") as caught:
                transport._run_bounded_worker(["fixed-worker"], time.monotonic() + 5)
        self.assertFalse(caught.exception.retryable)
        process.kill.assert_called_once()
