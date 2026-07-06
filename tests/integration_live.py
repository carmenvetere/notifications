"""G20: an active alert's templated content updates live, against a running HA."""

from homeassistant.core import HomeAssistant

from tests.helpers_ha import alerts, flush_debounce, rule_subentry, setup_nc


async def test_message_updates_while_active(hass: HomeAssistant):
    hass.states.async_set("sensor.temp", "90")
    await setup_nc(
        hass,
        rule_subentry(
            name="Hot", dedup_tag="hot", source_type="numeric",
            entity_id="sensor.temp", operator=">", value=80, priority="warning",
            channels=["wall"],
            message_template="Temp is {{ states('sensor.temp') }}",
        ),
    )
    assert alerts(hass)[0]["message"] == "Temp is 90"

    # Still above threshold (alert stays active) but the value changed.
    hass.states.async_set("sensor.temp", "95")
    await flush_debounce(hass)
    assert alerts(hass)[0]["message"] == "Temp is 95"
