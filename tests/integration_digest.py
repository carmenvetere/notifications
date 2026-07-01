"""Deferred delivery: quiet-hours batch + digest flush, against a running HA."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from tests.helpers_ha import count, rule_subentry, setup_nc

TARGETS = {"mobile_targets": ["notify.mobile_app_test"]}


async def test_digest_deferred_then_flushed(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("sensor.batt", "5")
    await setup_nc(
        hass,
        rule_subentry(
            name="Batteries", dedup_tag="batt", source_type="template",
            condition_template="{{ states('sensor.batt') | float(100) < 20 }}",
            priority="info", deliver_as_digest=True, digest_group="batteries",
            channels=["mobile"],
        ),
        options={**TARGETS, "digest_time": "08:00:00"},
    )
    # In the tray immediately, but the push is held for the digest window.
    assert count(hass) == "1"
    assert len(calls) == 0

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=25))
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_quiet_hours_batch_deferred_then_flushed(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("input_boolean.x", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="X", dedup_tag="x", source_type="state",
            entity_id="input_boolean.x", operator="==", value="on", priority="warning",
            channels=["mobile"], quiet_hours_behavior="batch",
        ),
        # Force "always quiet" so the batch path is exercised regardless of clock.
        options={**TARGETS, "quiet_hours_start": "00:00:00", "quiet_hours_end": "23:59:00"},
    )
    assert count(hass) == "1"
    assert len(calls) == 0  # held (batched during quiet hours)

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=25))
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_dismiss_before_flush_cancels_push(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("sensor.batt2", "5")
    await setup_nc(
        hass,
        rule_subentry(
            name="Batteries", dedup_tag="b2", source_type="template",
            condition_template="{{ states('sensor.batt2') | float(100) < 20 }}",
            priority="info", deliver_as_digest=True, channels=["mobile"],
        ),
        options={**TARGETS, "digest_time": "08:00:00"},
    )
    from custom_components.notification_center.const import DOMAIN

    await hass.services.async_call(DOMAIN, "dismiss", {"tag": "b2"}, blocking=True)
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=25))
    await hass.async_block_till_done()
    assert len(calls) == 0  # dismissed before the window -> never pushed
