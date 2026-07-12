"""Live Activity lifecycle (start / update / end + timeout), against a running HA."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from tests.helpers_ha import flush_debounce, rule_subentry, setup_nc

TARGETS = {"mobile_targets": ["notify.mobile_app_test"]}


async def test_live_activity_start_update_end(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("sensor.washer_progress", "40")
    await setup_nc(
        hass,
        rule_subentry(
            name="Washer", dedup_tag="washer", source_type="numeric",
            entity_id="sensor.washer_progress", operator=">", value=0,
            priority="info", channels=["mobile"],
            live_activity=True,
            progress_template="{{ states('sensor.washer_progress') }}",
            progress_max_template="100",
        ),
        options=TARGETS,
    )
    # Start: one push, as a Live Update, with the initial progress.
    assert len(calls) == 1
    assert calls[0].data["data"]["live_update"] is True
    assert calls[0].data["data"]["tag"] == "washer"
    assert calls[0].data["data"]["progress"] == 40

    # Update: progress changes while active -> silent update, same tag.
    hass.states.async_set("sensor.washer_progress", "80")
    await flush_debounce(hass)
    assert len(calls) == 2
    assert calls[1].data["data"]["progress"] == 80

    # End: condition resolves (0, not > 0) -> clear_notification.
    hass.states.async_set("sensor.washer_progress", "0")
    await flush_debounce(hass)
    assert len(calls) == 3
    assert calls[2].data["message"] == "clear_notification"
    assert calls[2].data["data"] == {"tag": "washer"}


async def test_activity_timeout_ends_even_when_still_active(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("input_boolean.grid", "off")
    await setup_nc(
        hass,
        rule_subentry(
            name="Outage", dedup_tag="outage", source_type="state",
            entity_id="input_boolean.grid", operator="==", value="off",
            priority="warning", channels=["mobile"],
            live_activity=True, activity_timeout=1,  # minutes
        ),
        options=TARGETS,
    )
    assert len(calls) == 1  # started

    # Condition is still active, but the timeout elapses -> auto clear_notification.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert calls[1].data["message"] == "clear_notification"
