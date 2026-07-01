"""Notification history log, against a running Home Assistant."""

from homeassistant.core import HomeAssistant

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import flush_debounce, rule_subentry, setup_nc


def _history(hass):
    return hass.states.get("sensor.notification_center").attributes["history"]


async def test_resolved_alert_recorded(hass: HomeAssistant):
    hass.states.async_set("input_boolean.h", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="H", dedup_tag="h", source_type="state",
            entity_id="input_boolean.h", operator="==", value="on", priority="info",
            channels=["wall"],
        ),
    )
    assert _history(hass) == []

    hass.states.async_set("input_boolean.h", "off")
    await flush_debounce(hass)

    hist = _history(hass)
    assert len(hist) == 1
    assert hist[0]["tag"] == "h"
    assert hist[0]["reason"] == "resolved"
    assert hist[0]["cleared_at"]


async def test_dismissed_alert_recorded(hass: HomeAssistant):
    hass.states.async_set("input_boolean.h2", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="H2", dedup_tag="h2", source_type="state",
            entity_id="input_boolean.h2", operator="==", value="on", priority="info",
            channels=["wall"],
        ),
    )
    await hass.services.async_call(DOMAIN, "dismiss", {"tag": "h2"}, blocking=True)
    await hass.async_block_till_done()

    hist = _history(hass)
    assert hist[0]["tag"] == "h2"
    assert hist[0]["reason"] == "dismissed"
