"""Existing regressions with external networking and real SDK import blocked."""
from pathlib import Path
import os
import sys
import unittest


def offline(event, args):
    if event == 'import' and (args[0] == 'vercel' or args[0].startswith('vercel.')):
        raise ImportError('REAL_SDK_IMPORT_FORBIDDEN')
    if event in ('socket.connect', 'socket.getaddrinfo'):
        address = args[1] if event == 'socket.connect' else args[0]
        host = address[0] if isinstance(address, tuple) else address
        # An existing redirect-security unit test uses a loopback HTTP stub.
        if host not in ('127.0.0.1', '::1', 'localhost'):
            raise RuntimeError('EXTERNAL_NETWORK_FORBIDDEN')


os.chdir(Path(__file__).resolve().parents[4] / 'web/pipeline')
sys.path.insert(0, str(Path.cwd()))
sys.addaudithook(offline)
result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover('tests'))
raise SystemExit(0 if result.wasSuccessful() else 1)
