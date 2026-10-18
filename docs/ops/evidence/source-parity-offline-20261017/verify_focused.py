"""Run only the source-core and affected boundaries; deny outbound sockets."""
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'web/pipeline/tests'))
sys.path.insert(0, str(ROOT / 'web/pipeline'))
MODULES = [
    'test_twice_daily_source_parity', 'test_twice_daily_search',
    'test_twice_daily_terminal_race', 'test_collector_native_reliability',
    'test_execution_namespace', 'test_tjzyefy_discovery',
    'test_tjzyefy_market_research', 'test_tjzyefy_intent_discovery',
    'test_tjzyefy_procurement_intent', 'test_tjzxfc_discovery',
    'test_tjzxfc_market_research',
]
if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('OFFLINE_NETWORK_FORBIDDEN')), \
         patch.object(socket.socket, 'connect_ex', side_effect=AssertionError('OFFLINE_NETWORK_FORBIDDEN')), \
         patch.object(socket, 'create_connection', side_effect=AssertionError('OFFLINE_NETWORK_FORBIDDEN')):
        suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(not result.wasSuccessful())
