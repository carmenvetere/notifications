"""Engine behavior against a running Home Assistant (pytest-homeassistant-…)."""

from homeassistant.core import HomeAssistant

from tests.helpers_ha import alerts, count, flush_debounce, rule_subentry, setup_nc


async def test_state_rule_active_at_setup_and_autoclears(hass: HomeAssistant):
    hass.states.async_set("cover.garage", "open")
    await setup_nc(
        hass,
        rule_subentry(
            name="Garage",
            dedup_tag="garage",
            source_type="state",
            entity_id="cover.garage",
            operator="==",
            value="open",
            priority="warning",
        ),
    )
    assert count(hass) == "1"
    row = alerts(hass)[0]
    assert row["tag"] == "garage"
    assert row["priority"] == "warning"
    assert row["actions"] == []  # warning is locked

    hass.states.async_set("cover.garage", "closed")
    await flush_debounce(hass)
    assert count(hass) == "0"


async def test_numeric_rule(hass: HomeAssistant):
    hass.states.async_set("sensor.utility_temp", "50")
    await setup_nc(
        hass,
        rule_subentry(
            name="Utility cold",
            dedup_tag="utility_cold",
            source_type="numeric",
            entity_id="sensor.utility_temp",
            operator="<",
            value=55,
            priority="info",
        ),
    )
    assert count(hass) == "1"
    # Info alerts are dismissable + snoozable.
    assert set(alerts(hass)[0]["actions"]) == {"dismiss", "snooze"}


async def test_priority_sensors_reflect_highest(hass: HomeAssistant):
    hass.states.async_set("binary_sensor.alarm", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Alarm",
            dedup_tag="alarm",
            source_type="state",
            entity_id="binary_sensor.alarm",
            operator="==",
            value="on",
            priority="critical",
        ),
    )
    assert hass.states.get("sensor.notification_center_priority").state == "critical"
    assert hass.states.get("binary_sensor.notification_center_critical").state == "on"
    assert hass.states.get("binary_sensor.notification_center_active").state == "on"
    assert hass.states.get("binary_sensor.notification_center_warning").state == "off"


async def test_template_rule(hass: HomeAssistant):
    hass.states.async_set("sensor.grid", "off")
    hass.states.async_set("sensor.charge", "10")
    await setup_nc(
        hass,
        rule_subentry(
            name="Powerwall low",
            dedup_tag="pw_low",
            source_type="template",
            condition_template=(
                "{{ is_state('sensor.grid','off') "
                "and states('sensor.charge')|float(100) < 25 }}"
            ),
            priority="critical",
        ),
    )
    assert count(hass) == "1"


async def test_digest_items_in_payload(hass: HomeAssistant):
    hass.states.async_set("sensor.batt", "5")
    await setup_nc(
        hass,
        rule_subentry(
            name="Batteries",
            dedup_tag="batteries",
            source_type="template",
            condition_template="{{ states('sensor.batt')|float(100) < 20 }}",
            priority="info",
            deliver_as_digest=True,
            digest_group="batteries",
            items_template=(
                "{{ [{'name': 'Battery', 'detail': states('sensor.batt') ~ '%'}] }}"
            ),
        ),
    )
    row = alerts(hass)[0]
    assert row["digest"] is True
    assert row["items"][0]["name"] == "Battery"
    assert row["items"][0]["detail"] == "5%"
