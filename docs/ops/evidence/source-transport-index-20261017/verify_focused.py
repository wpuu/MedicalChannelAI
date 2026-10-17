"""Reproduce transport/index boundaries and affected core checks offline."""
from pathlib import Path
import runpy
import socket
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
base = runpy.run_path(str(ROOT / 'docs/ops/evidence/source-parity-offline-20261017/verify_focused.py'))
MODULES = base['MODULES'] + ['test_official_source_transport', 'test_official_source_index']
if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('OFFLINE_NETWORK_FORBIDDEN')), \
         patch.object(socket.socket, 'connect_ex', side_effect=AssertionError('OFFLINE_NETWORK_FORBIDDEN')), \
         patch.object(socket, 'create_connection', side_effect=AssertionError('OFFLINE_NETWORK_FORBIDDEN')):
        suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(not result.wasSuccessful())
