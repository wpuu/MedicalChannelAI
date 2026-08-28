"""Research-only medical opportunity collection pilot.

Not production ready. Public-source facts must remain evidence-backed and model-independent.
"""

from .adapters import CcgpAdapter, TjmughAdapter
from .ccgp_lifecycle_adapter import (
    AwardPackage,
    CcgpLifecycleAdapter,
    ParsedCcgpLifecycleNotice,
    build_ccgp_lifecycle_event_and_facts,
)
from .collector_core import HostBoundFetcher, ParsedNotice, Snapshot, build_event_and_facts
from .intent_adapter import CcgpIntentAdapter, ParsedIntentNotice, build_intent_event_and_facts
from .lifecycle import LifecycleAggregate, group_and_resolve_lifecycles, resolve_project_lifecycle

__all__ = [
    "AwardPackage",
    "CcgpAdapter",
    "CcgpLifecycleAdapter",
    "CcgpIntentAdapter",
    "TjmughAdapter",
    "HostBoundFetcher",
    "ParsedNotice",
    "ParsedCcgpLifecycleNotice",
    "ParsedIntentNotice",
    "Snapshot",
    "LifecycleAggregate",
    "build_event_and_facts",
    "build_ccgp_lifecycle_event_and_facts",
    "build_intent_event_and_facts",
    "resolve_project_lifecycle",
    "group_and_resolve_lifecycles",
]
