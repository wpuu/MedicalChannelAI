from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


POLICY_PATH = Path(__file__).with_name("discovery_cadence.tianjin.v0.1.json")


@dataclass(frozen=True)
class DiscoveryCadenceDecision:
    source_id: str
    source_group: str
    local_time: str
    weekend: bool
    base_interval_minutes: int
    interval_minutes: int
    minute_offset: int
    jitter_percent: int
    failure_count: int
    reason: str

    def as_dict(self) -> dict:
        return {
            "schema_version": "0.1",
            "source_id": self.source_id,
            "source_group": self.source_group,
            "local_time": self.local_time,
            "weekend": self.weekend,
            "base_interval_minutes": self.base_interval_minutes,
            "interval_minutes": self.interval_minutes,
            "minute_offset": self.minute_offset,
            "jitter_percent": self.jitter_percent,
            "failure_count": self.failure_count,
            "reason": self.reason,
        }


def load_discovery_policy(path: Path = POLICY_PATH) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    if hour == "24":
        return 24 * 60
    return int(hour) * 60 + int(minute)


def _window_contains(window: str, minute_of_day: int) -> bool:
    start, end = window.split("-", 1)
    return _minutes(start) <= minute_of_day < _minutes(end)


def _source_group(policy: dict, source_id: str) -> str:
    matches = [
        group
        for group, source_ids in policy["source_groups"].items()
        if source_id in source_ids
    ]
    if len(matches) != 1:
        raise ValueError(f"source_id must belong to exactly one cadence group: {source_id}")
    return matches[0]


def _minute_offset(policy: dict, source_id: str, base_interval: int) -> int:
    offsets = policy.get("source_minute_offsets") or {}
    if source_id not in offsets:
        raise ValueError(f"source_id is missing source_minute_offsets entry: {source_id}")
    offset = int(offsets[source_id])
    if offset < 0 or offset >= base_interval:
        # Backoff may increase interval, but a source's stable phase must always fit
        # inside its fastest/base interval for the current window.
        raise ValueError(
            f"source minute offset must be within current base interval: {source_id} offset={offset} base={base_interval}"
        )
    return offset


def plan_discovery_cadence(
    source_id: str,
    *,
    now: datetime,
    consecutive_failures: int = 0,
    policy_path: Path = POLICY_PATH,
) -> DiscoveryCadenceDecision:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if consecutive_failures < 0:
        raise ValueError("consecutive_failures cannot be negative")

    policy = load_discovery_policy(policy_path)
    timezone = ZoneInfo(policy["timezone"])
    local = now.astimezone(timezone)
    group = _source_group(policy, source_id)
    weekend = local.weekday() >= 5
    windows = policy["weekend_windows"] if weekend else policy["weekday_windows"]
    minute_of_day = local.hour * 60 + local.minute

    matching = [item for item in windows if _window_contains(item["window"], minute_of_day)]
    if len(matching) != 1:
        raise ValueError("cadence windows must cover the local day exactly once")
    base = int(matching[0]["interval_minutes"][group])
    offset = _minute_offset(policy, source_id, base)

    backoff = policy["failure_backoff"]
    multiplier = int(backoff["multiplier"])
    max_interval = int(backoff["max_interval_minutes"])
    interval = min(max_interval, base * (multiplier ** consecutive_failures))

    reason = (
        f"{group} {'weekend' if weekend else 'weekday'} cadence; "
        f"window={matching[0]['window']}; stable_minute_offset={offset}; failures={consecutive_failures}"
    )
    return DiscoveryCadenceDecision(
        source_id=source_id,
        source_group=group,
        local_time=local.isoformat(),
        weekend=weekend,
        base_interval_minutes=base,
        interval_minutes=interval,
        minute_offset=offset,
        jitter_percent=int(policy.get("jitter_percent") or 0),
        failure_count=consecutive_failures,
        reason=reason,
    )
