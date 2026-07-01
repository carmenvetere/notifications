"""Deferred delivery: quiet-hours batch + digest flush, against a running HA."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import alerts, count, rule_subentry, setup_nc

TARGETS = {"mobile_targets": ["notify.mobile_app_test"]}

# A fixed instant to freeze at. The flush timer fires via async_fire_time_changed
# (which advances the event loop clock), but the engine's _flush re-reads
# dt_util.now() to decide which held alerts are due — so the wall clock must
# advance too, or nothing is considered due. freeze_time controls both.
FROZEN = "2026-06-01 18:00:00"  # noon-ish local, well clear of default quiet hours


def _clock(minutes: int) -> str:
    """A local clock time `minutes` from the frozen now (small delta so the
    flush timer fires promptly once we advance the frozen clock)."""
    return (dt_util.now() + timedelta(minutes=minutes)).strftime("%H:%M:%S")


async def test_digest_deferred_then_flushed(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    with freeze_time(FROZEN) as frozen:
        hass.states.async_set("sensor.batt", "5")
        await setup_nc(
            hass,
            rule_subentry(
                name="Batteries", dedup_tag="batt", source_type="template",
                condition_template="{{ states('sensor.batt') | float(100) < 20 }}",
                priority="info", deliver_as_digest=True, digest_group="batteries",
                channels=["mobile"],
            ),
            options={**TARGETS, "digest_time": _clock(2)},
        )
        # In the tray immediately, but the push is held for the digest window.
        assert count(hass) == "1"
        assert len(calls) == 0

        frozen.move_to(dt_util.utcnow() + timedelta(minutes=3))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert len(calls) == 1


async def test_quiet_hours_batch_deferred_then_flushed(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    with freeze_time(FROZEN) as frozen:
        hass.states.async_set("input_boolean.x", "on")
        await setup_nc(
            hass,
            rule_subentry(
                name="X", dedup_tag="x", source_type="state",
                entity_id="input_boolean.x", operator="==", value="on",
                priority="warning", channels=["mobile"], quiet_hours_behavior="batch",
            ),
            # In quiet hours now (started an hour ago), window ends in 2 minutes.
            options={
                **TARGETS,
                "quiet_hours_start": _clock(-60),
                "quiet_hours_end": _clock(2),
            },
        )
        assert count(hass) == "1"
        assert len(calls) == 0  # held (batched during quiet hours)

        frozen.move_to(dt_util.utcnow() + timedelta(minutes=3))
        async_fire_time_changed(hass)
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
        options={**TARGETS, "digest_time": _clock(2)},
    )
    await hass.services.async_call(DOMAIN, "dismiss", {"tag": "b2"}, blocking=True)
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=3))
    await hass.async_block_till_done()
    assert len(calls) == 0  # dismissed before the window -> never pushed


async def test_dismiss_digest_item(hass: HomeAssistant):
    hass.states.async_set("sensor.d", "5")
    await setup_nc(
        hass,
        rule_subentry(
            name="D", dedup_tag="d", source_type="template",
            condition_template="{{ states('sensor.d') | float(100) < 20 }}",
            priority="info", deliver_as_digest=True, channels=["wall"],
            items_template=(
                "{{ [{'name': 'One', 'detail': '1%'}, {'name': 'Two', 'detail': '2%'}] }}"
            ),
        ),
    )
    assert len(alerts(hass)[0]["items"]) == 2

    await hass.services.async_call(
        DOMAIN, "dismiss_item", {"tag": "d", "item": "One"}, blocking=True
    )
    await hass.async_block_till_done()
    assert [i["name"] for i in alerts(hass)[0]["items"]] == ["Two"]
