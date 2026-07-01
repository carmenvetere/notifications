"""Cooldown + escalation timing, against a running Home Assistant."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from tests.helpers_ha import count, flush_debounce, rule_subentry, setup_nc

TARGETS = {"mobile_targets": ["notify.mobile_app_test"]}


async def test_cooldown_suppresses_redelivery(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("input_boolean.c", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="C", dedup_tag="c", source_type="state",
            entity_id="input_boolean.c", operator="==", value="on", priority="info",
            channels=["mobile"], cooldown=60,
        ),
        options=TARGETS,
    )
    assert len(calls) == 1  # delivered on first fire

    # Clear, then re-fire within the cooldown window.
    hass.states.async_set("input_boolean.c", "off")
    await flush_debounce(hass)
    hass.states.async_set("input_boolean.c", "on")
    await flush_debounce(hass)

    assert count(hass) == "1"       # shows in the tray again
    assert len(calls) == 1          # but the push is NOT re-sent (cooldown)


async def test_escalation_redelivers(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("input_boolean.e", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="E", dedup_tag="e", source_type="state",
            entity_id="input_boolean.e", operator="==", value="on", priority="critical",
            channels=["mobile"], escalation_after=1,
        ),
        options=TARGETS,
    )
    assert len(calls) == 1

    # Advance past the 1-minute escalation interval.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert len(calls) == 2
