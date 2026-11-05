from __future__ import annotations

import importlib.util
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request


SPEC = importlib.util.spec_from_file_location('public_demo_smoke', Path(__file__).resolve().parents[2] / 'scripts' / 'public-demo-smoke.py')
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class PublicDemoSmokeTests(unittest.TestCase):
    def test_real_http_redirect_is_rejected_before_contacting_another_origin(self):
        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', 'https://example.invalid/today')
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaisesRegex(smoke.SmokeFailure, 'CROSS_ORIGIN_REDIRECT'):
                smoke.check_endpoint(f'http://127.0.0.1:{server.server_port}/')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_cross_origin_redirect_to_vercel_fails(self):
        with self.assertRaisesRegex(smoke.SmokeFailure, 'CROSS_ORIGIN_REDIRECT'):
            smoke.SameOriginRedirect().redirect_request(
                Request('https://medicalai.qd.je/'), None, 302, 'Found', {}, 'https://medicalchannelai.vercel.app/today')

    def test_same_origin_redirect_is_allowed(self):
        request = smoke.SameOriginRedirect().redirect_request(
            Request('https://medicalai.qd.je/'), None, 302, 'Found', {}, 'https://medicalai.qd.je/today')
        self.assertEqual(request.full_url, 'https://medicalai.qd.je/today')

    def test_stale_degraded_and_unknown_source_status_are_not_green(self):
        healthy = {'service': 'MedicalChannelAI', 'ready': True, 'degraded': False,
                   'snapshot': {'available': True, 'freshness': 'FRESH', 'source_health': {'status': 'HEALTHY'}}}
        smoke.validate_status(healthy)
        for overrides in [{'degraded': True}, {'snapshot': {'available': True, 'freshness': 'STALE'}},
                          {'snapshot': {'available': True, 'freshness': 'FRESH', 'source_health': {'status': 'UNKNOWN'}}}]:
            with self.subTest(overrides=overrides), self.assertRaises(smoke.SmokeFailure):
                smoke.validate_status({**healthy, **overrides})

    def test_smoke_checks_the_qd_entrypoint_api_itself(self):
        with patch.object(smoke, 'check_endpoint') as check:
            smoke.main()
        self.assertIn((('https://medicalai.qd.je/api/status',), {'status_endpoint': True}),
                      [(call.args, call.kwargs) for call in check.call_args_list])


if __name__ == '__main__':
    unittest.main()
