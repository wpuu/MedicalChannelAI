"""Test-only stand-in for the `vercel` Python SDK (Runtime Cache + Queues).

Only the surface used by web/collector_runtime.py, web/collector_queue.py and
web/api/collector-run.py is implemented. Behaviour mirrors the documented SDK:
Runtime Cache values round-trip through JSON; reusing a queue idempotency key
raises DuplicateIdempotencyKeyError.
"""
