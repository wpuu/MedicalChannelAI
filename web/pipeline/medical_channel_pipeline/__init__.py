from .validation import ValidationError, validate_records
from .public_snapshot import build_public_snapshot as _build_public_snapshot
from .channel_scope import filter_public_snapshot_to_medical_channel


def build_public_snapshot(records, as_of, notice_events=None):
    snapshot = _build_public_snapshot(records, as_of, notice_events)
    return filter_public_snapshot_to_medical_channel(snapshot)


__all__ = ["ValidationError", "validate_records", "build_public_snapshot"]
