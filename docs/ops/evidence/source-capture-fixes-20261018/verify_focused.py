"""Affected transport/index/core checks only; outbound sockets prohibited."""
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
for path in ('web', 'web/pipeline', 'web/pipeline/tests'):
    sys.path.insert(0, str(ROOT / path))
MODULES = ['test_official_source_capture_fixes', 'test_official_source_transport',
           'test_official_source_index', 'test_twice_daily_source_parity']

if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('OFFLINE_ONLY')), \
         patch.object(socket.socket, 'connect_ex', side_effect=AssertionError('OFFLINE_ONLY')), \
         patch.object(socket, 'create_connection', side_effect=AssertionError('OFFLINE_ONLY')):
        suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
