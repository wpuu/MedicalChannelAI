from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


WEB_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('pipeline_health_under_test', WEB_ROOT / 'api' / 'pipeline-health.py')
assert SPEC and SPEC.loader
health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health)


def status_payload(*, freshness='FRESH', source_status='HEALTHY', degraded=False):
    return {
        'service': 'MedicalChannelAI', 'ready': True, 'degraded': degraded,
        'snapshot': {
            'available': True, 'source_mode': 'DATABASE', 'freshness': freshness,
            'age_minutes': 5, 'source_health': {'status': source_status},
        },
    }


class PipelineHealthCronSecretTests(unittest.TestCase):
    def test_production_requires_cron_secret_but_preview_does_not(self):
        with patch.dict(os.environ, {'VERCEL_ENV': 'production', 'CRON_SECRET': ''}):
            self.assertEqual(health.cron_secret_state(), (False, True))
        with patch.dict(os.environ, {'VERCEL_ENV': 'preview', 'CRON_SECRET': ''}):
            self.assertEqual(health.cron_secret_state(), (False, False))

    def read_status(self, payload):
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps(payload).encode()
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with patch.dict(os.environ, {
            'VERCEL_URL': 'current-deployment.vercel.app',
            'VERCEL_PROJECT_PRODUCTION_URL': 'production-alias.vercel.app',
            'VERCEL_ENV': 'preview',
        }), patch.object(health, 'build_opener', return_value=opener), patch.object(health, 'RuntimeCache') as cache:
            result = health.served_snapshot_health()
        self.assertEqual(opener.open.call_args.args[0].full_url, 'https://current-deployment.vercel.app/api/status')
        cache.assert_not_called()
        return result

    def test_health_uses_the_snapshot_served_by_the_same_deployment(self):
        result = self.read_status(status_payload())
        self.assertTrue(result['available'])
        self.assertTrue(result['fresh'])
        self.assertFalse(result['degraded'])
        self.assertEqual(result['source'], 'DATABASE')
        self.assertEqual(result['age_seconds'], 300)

    def test_readable_stale_snapshot_stays_available_and_degraded(self):
        result = self.read_status(status_payload(freshness='STALE', degraded=True))
        self.assertTrue(result['available'])
        self.assertFalse(result['fresh'])
        self.assertTrue(result['degraded'])

    def test_recent_snapshot_does_not_hide_unknown_source_health(self):
        result = self.read_status(status_payload(source_status='UNKNOWN'))
        self.assertTrue(result['available'])
        self.assertFalse(result['fresh'])
        self.assertTrue(result['degraded'])
        payload = status_payload()
        del payload['snapshot']['source_health']
        self.assertFalse(self.read_status(payload)['fresh'])

    def test_invalid_age_never_becomes_healthy(self):
        for age in (None, True, -1, float('inf')):
            payload = status_payload()
            payload['snapshot']['age_minutes'] = age
            with self.subTest(age=age):
                self.assertFalse(self.read_status(payload)['fresh'])

    def test_unavailable_serving_status_never_promotes_a_cache_candidate(self):
        with patch.dict(os.environ, {'VERCEL_URL': 'current-deployment.vercel.app'}), \
                patch.object(health, 'build_opener', side_effect=OSError('status unavailable')), \
                patch.object(health, 'RuntimeCache') as cache:
            cache.return_value.get.return_value = {'snapshot_as_of': '2099-01-01T00:00:00Z'}
            result = health.served_snapshot_health()
        self.assertFalse(result['available'])
        self.assertFalse(result['fresh'])
        self.assertEqual(result['source_health']['status'], 'UNKNOWN')
        cache.assert_not_called()

    def test_pipeline_availability_and_source_freshness_are_separate_axes(self):
        response = MagicMock()
        request_handler = health.handler.__new__(health.handler)
        request_handler._send_json = response
        served = {'available': True, 'fresh': False, 'degraded': True, 'source': 'DATABASE',
                  'age_seconds': 300, 'freshness': 'FRESH', 'source_health': {'status': 'STALE'}}
        with patch.object(health, '_IMPORT_OK', True), patch.object(health, '_DATA_OK', True), \
                patch.object(health, 'cache_roundtrip', return_value=True), \
                patch.object(health, 'cron_secret_state', return_value=(True, True)), \
                patch.object(health, 'served_snapshot_health', return_value=served):
            request_handler.do_GET()
        code, payload = response.call_args.args
        self.assertEqual(code, 200)
        self.assertTrue(payload['ready'])
        self.assertTrue(payload['degraded'])
        self.assertTrue(payload['pipeline_runtime']['verified_snapshot_available'])
        self.assertFalse(payload['pipeline_runtime']['verified_snapshot_fresh'])

    def test_status_redirect_is_not_followed_to_a_different_deployment(self):
        self.assertIsNone(health._NoStatusRedirect().redirect_request(None, None, 302, '', {}, 'https://another.vercel.app/api/status'))

    def test_preview_self_request_attaches_runtime_oidc_only_to_its_exact_host(self):
        with patch.dict(os.environ, {'VERCEL_OIDC_TOKEN': 'preview-test-oidc'}), \
                patch.object(health, 'Request', wraps=health.Request) as request:
            self.assertTrue(self.read_status(status_payload())['fresh'])
        self.assertEqual(request.call_args.kwargs['headers']['x-vercel-trusted-oidc-idp-token'], 'preview-test-oidc')

    def test_preview_invalid_or_production_host_never_receives_oidc(self):
        for host in ('medicalchannelai.vercel.app', 'evil.example', 'good.vercel.app@evil.example', 'good.vercel.app/path'):
            with self.subTest(host=host), patch.dict(os.environ, {
                'VERCEL_ENV': 'preview', 'VERCEL_URL': host, 'VERCEL_OIDC_TOKEN': 'preview-test-oidc',
            }), patch.object(health, 'build_opener') as opener:
                self.assertFalse(health.served_snapshot_health()['available'])
                opener.assert_not_called()

    def test_production_health_request_does_not_forward_runtime_oidc(self):
        opener = MagicMock()
        opener.open.side_effect = OSError('offline test')
        with patch.dict(os.environ, {
            'VERCEL_ENV': 'production', 'VERCEL_URL': 'prod-exact.vercel.app', 'VERCEL_OIDC_TOKEN': 'test-oidc',
        }), patch.object(health, 'build_opener', return_value=opener):
            health.served_snapshot_health()
        headers = dict((key.lower(), value) for key, value in opener.open.call_args.args[0].header_items())
        self.assertNotIn('x-vercel-trusted-oidc-idp-token', headers)


if __name__ == '__main__':
    unittest.main()
