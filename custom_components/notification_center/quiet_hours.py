"""Quiet-hours handling. Pure logic, unit-testable without Home Assistant."""

from __future__ import annotations

from datetime import time

from .const import (
    QH_BATCH,
    QH_DOWNGRADE,
    QH_IGNORE,
    QH_SUPPRESS,
)

# Priority chain used when downgrading one level. Info is the floor.
_DOWNGRADE = {
    "critical": "warning",
    "warning": "info",
    "info": "info",
}


def parse_time(value: str | time) -> time:
    """Parse "HH:MM" / "HH:MM:SS" into a ``time``."""
    if isinstance(value, time):
        return value
    parts = [int(p) for p in str(value).split(":")]
    while len(parts) < 3:
        parts.append(0)
    return time(parts[0], parts[1], parts[2])


def in_quiet_hours(now: time, start: time, end: time) -> bool:
    """Whether ``now`` falls within the quiet window, handling midnight wrap."""
    if start == end:
        return False
    if start < end:
        return start <= now < end
    # Wraps past midnight, e.g. 22:00 -> 07:00.
    return now >= start or now < end


def apply_quiet_hours(
    priority: str,
    behavior: str,
    is_quiet: bool,
) -> tuple[str, bool, bool]:
    """Resolve a rule's priority during quiet hours.

    Returns ``(effective_priority, suppress_push, batch_push)``.

    - ``suppress_push``: still show on wall/bell, but skip mobile/tts.
    - ``batch_push``: hold the push for the next digest/window.
    """
    if not is_quiet or behavior == QH_IGNORE:
        return priority, False, False

    if behavior == QH_DOWNGRADE:
        return _DOWNGRADE.get(priority, priority), False, False

    if behavior == QH_SUPPRESS:
        return priority, True, False

    if behavior == QH_BATCH:
        return priority, False, True

    return priority, False, False
