"""Test mode (fire a rule on demand, as designed) + the wall-panel feed."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import alerts, count, flush_debounce, rule_subentry, setup_nc


def _outage():
    return rule_subentry(
        name="Power Outage", dedup_tag="power_outage", source_type="state",
        entity_id="binary_sensor.grid", operator="==", value="off",
        priority="critical", channels=["mobile", "bell", "wall"],
        title_template="Power Outage!",
        message_template="Battery {{ states('sensor.charge') }}%",
        cooldown=60,
    )


async def test_test_mode_fires_as_designed_and_leaves_no_trace(hass: HomeAssistant):
    push = async_mock_service(hass, "notify", "mobile_app_test")
    hass.states.async_set("binary_sensor.grid", "on")  # condition NOT met
    hass.states.async_set("sensor.charge", "76")
    await setup_nc(hass, _outage(), options={"mobile_targets": ["notify.mobile_app_test"]})
    assert count(hass) == "0"

    # Start: the alert appears everywhere, rendered from the real templates.
    await hass.services.async_call(
        DOMAIN, "test_rule", {"tag": "power_outage"}, blocking=True
    )
    await hass.async_block_till_done()
    a = alerts(hass)
    assert [x["tag"] for x in a] == ["power_outage"]
    assert a[0]["test"] is True
    assert a[0]["title"] == "Power Outage!"
    assert a[0]["message"] == "Battery 76%"
    assert len(push) == 1  # the real push went out

    # The real condition is ignored while testing (grid is still "on").
    hass.states.async_set("sensor.charge", "70")
    await flush_debounce(hass)
    assert count(hass) == "1"

    # Stop: gone, no history, and no cooldown left behind.
    await hass.services.async_call(
        DOMAIN, "test_rule", {"tag": "power_outage", "enabled": False}, blocking=True
    )
    await hass.async_block_till_done()
    assert count(hass) == "0"
    st = hass.states.get("sensor.notification_center")
    assert st.attributes["history"] == []

    # The rule still fires for real afterwards — and pushes (no cooldown).
    hass.states.async_set("binary_sensor.grid", "off")
    await flush_debounce(hass)
    assert count(hass) == "1"
    assert alerts(hass)[0].get("test") is not True
    assert len(push) == 2


async def test_test_mode_auto_stops_after_ten_minutes(hass: HomeAssistant):
    hass.states.async_set("binary_sensor.grid", "on")
    hass.states.async_set("sensor.charge", "50")
    await setup_nc(hass, _outage())
    await hass.services.async_call(
        DOMAIN, "test_rule", {"tag": "power_outage"}, blocking=True
    )
    await hass.async_block_till_done()
    assert count(hass) == "1"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10, seconds=5))
    await hass.async_block_till_done()
    assert count(hass) == "0"


async def test_dismissing_a_test_alert_does_not_hide_the_real_one(hass: HomeAssistant):
    hass.states.async_set("binary_sensor.grid", "on")
    hass.states.async_set("sensor.charge", "50")
    await setup_nc(
        hass,
        rule_subentry(
            name="Info thing", dedup_tag="info_thing", source_type="state",
            entity_id="binary_sensor.grid", operator="==", value="off",
            priority="info", channels=["wall"],
        ),
    )
    await hass.services.async_call(DOMAIN, "test_rule", {"tag": "info_thing"}, blocking=True)
    await hass.async_block_till_done()
    assert count(hass) == "1"
    # Dismiss (allowed for info) just ends the test…
    await hass.services.async_call(DOMAIN, "dismiss", {"tag": "info_thing"}, blocking=True)
    await hass.async_block_till_done()
    assert count(hass) == "0"
    # …without the usual "hidden until the condition resolves" hold.
    hass.states.async_set("binary_sensor.grid", "off")
    await flush_debounce(hass)
    assert count(hass) == "1"


async def test_wall_feed_encoding(hass: HomeAssistant):
    hass.states.async_set("binary_sensor.grid", "off")
    hass.states.async_set("sensor.charge", "76")
    await setup_nc(
        hass,
        _outage(),
        rule_subentry(
            name="Pool | salt; low", dedup_tag="pool_salt", source_type="state",
            entity_id="binary_sensor.grid", operator="==", value="off",
            priority="info", channels=["wall"],
            message_template="Line one\nLine two",
        ),
    )
    st = hass.states.get("sensor.notification_center_wall")
    assert st.state == "2"
    rows = st.attributes["items"].split(";")
    assert rows[0] == "power_outage|critical|Power Outage!|Battery 76%|Just now|0|0"
    # Separators inside text are neutralised; newlines flattened.
    assert rows[1] == "pool_salt|info|Pool / salt, low|Line one Line two|Just now|1|0"
    assert st.attributes["critical_text"] == "Power Outage!"
    assert st.attributes["rows"][1]["dismissable"] is True
    assert st.attributes["testing"] == []
