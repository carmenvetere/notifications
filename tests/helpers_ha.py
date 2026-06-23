"""Shared helpers for the Home Assistant integration tests."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.notification_center.const import DOMAIN


def rule_subentry(**data: Any) -> ConfigSubentryData:
    """Build a rule subentry. Defaults to the wall channel (no service calls)
    and ignores quiet hours so priority assertions don't depend on the CI clock
    (the test HA runs in US/Pacific)."""
    data.setdefault("channels", ["wall"])
    data.setdefault("quiet_hours_behavior", "ignore")
    return ConfigSubentryData(
        data=data,
        subentry_type="rule",
        title=data.get("name", "Rule"),
        unique_id=data.get("dedup_tag") or data.get("name") or "rule",
    )


async def setup_nc(hass: HomeAssistant, *subentries: ConfigSubentryData) -> MockConfigEntry:
    """Create + set up a Notification Center entry with the given rules."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Notification Center",
        unique_id=DOMAIN,
        data={},
        subentries_data=list(subentries),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def flush_debounce(hass: HomeAssistant) -> None:
    """Fire past the engine's re-evaluation debounce and settle.

    Settle first so the pending state-change event is processed and the engine
    has actually scheduled its debounce timer, then advance time to fire it.
    """
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()


def count(hass: HomeAssistant) -> str:
    return hass.states.get("sensor.notification_center").state


def alerts(hass: HomeAssistant) -> list[dict]:
    return hass.states.get("sensor.notification_center").attributes["alerts"]
