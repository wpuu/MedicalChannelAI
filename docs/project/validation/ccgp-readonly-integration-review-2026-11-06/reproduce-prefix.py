"""Synthetic-only integration counterexample; no SDK, credentials or network."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'web'))
import collector_readonly_export as core
import collector_namespace as ns
from collector_epoch import _EpochCache, epoch_key


class LocalRawGet:
    def __init__(self, present_key):
        self.present_key = present_key
        self.reads = []

    def get(self, key):
        self.reads.append(key)
        return [] if key == self.present_key else None


class IncorrectHiddenEpochFacade:
    def __init__(self, local_raw, epoch):
        # Only a local stub is wrapped. Never collector_epoch.RuntimeCache().
        self._wrapped = _EpochCache(local_raw, epoch)

    def get(self, key):
        return self._wrapped.get(key)


def reproduce():
    scope = dict(core._D_SCOPE)
    epoch = scope['preview_epoch']
    physical = epoch_key(ns.CCGP_RECORDS_KEY, epoch)
    correct = LocalRawGet(physical)
    incorrect = LocalRawGet(physical)
    with patch('collector_epoch.RuntimeCache', side_effect=AssertionError('CLIENT_FORBIDDEN')), \
         patch('socket.create_connection', side_effect=AssertionError('NETWORK_FORBIDDEN')), \
         patch('urllib.request.urlopen', side_effect=AssertionError('NETWORK_FORBIDDEN')):
        direct = core.observe_d_canonical(correct, scope=scope, expected_scope=scope)
        doubled = core.observe_d_canonical(IncorrectHiddenEpochFacade(incorrect, epoch),
                                           scope=scope, expected_scope=scope)
    assert direct['shards'][ns.CCGP_RECORDS_KEY]['state'] == 'PRESENT_EMPTY'
    assert doubled['shards'][ns.CCGP_RECORDS_KEY]['state'] == 'UNINITIALIZED_OR_UNAVAILABLE'
    assert correct.reads == [epoch_key(key, epoch) for key in core._plan()]*2
    assert incorrect.reads == [epoch_key(epoch_key(key, epoch), epoch) for key in core._plan()]*2
    assert all(result['read_plan_complete'] and not result['migration_usable']
               and not result['scope_provenance_verified'] and not result['apply_allowed']
               for result in (direct, doubled))
    return {'kind':'SYNTHETIC_LOCAL_INTEGRATION_COUNTEREXAMPLE',
        'native_client_constructed':False,'cloud_access_performed':False,
        'correct':{'first_forwarded_key':correct.reads[0], 'calls':len(correct.reads),
                   'ccgp_state':direct['shards'][ns.CCGP_RECORDS_KEY]['state']},
        'incorrect_hidden_epoch':{'first_forwarded_key':incorrect.reads[0], 'calls':len(incorrect.reads),
                   'ccgp_state':doubled['shards'][ns.CCGP_RECORDS_KEY]['state']},
        'conclusion':'Equal observation passes do not authenticate a facade or detect a stable wrong key transform.',
        'actual_kernel_defect_reproduced':False, 'apply_allowed':False}


if __name__ == '__main__':
    print(json.dumps(reproduce(),ensure_ascii=False,indent=2))
