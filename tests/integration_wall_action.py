"""wall_action in the wall feed, wall_service calls, recipients end to end,
and the removed `navigate` channel — against a running Home Assistant."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import alerts, count, flush_debounce, rule_subentry, setup_nc


def _feed(hass: HomeAssistant) -> dict:
    return hass.states.get("sensor.notification_center_wall").attributes


def _outage(**extra):
    return rule_subentry(
        name="Power Outage", dedup_tag="power_outage", source_type="state",
        entity_id="binary_sensor.grid", operator="==", value="off",
        priority="critical", channels=["wall"], wall_action="sheet:outage,chime",
        message_template="Battery {{ states('sensor.charge') }}%",
        **extra,
    )


async def test_wall_action_published_once_per_fire(hass: HomeAssistant):
    hass.states.async_set("binary_sensor.grid", "on")
    hass.states.async_set("sensor.charge", "80")
    await setup_nc(hass, _outage())
    assert _feed(hass)["action"] == ""

    hass.states.async_set("binary_sensor.grid", "off")
    await flush_debounce(hass)
    first = _feed(hass)["action"]
    tag, action, nonce = first.split("|")
    assert (tag, action) == ("power_outage", "sheet:outage,chime")
    assert _feed(hass)["action_at"]

    # A silent content refresh (message changes, still active) must NOT re-fire.
    hass.states.async_set("sensor.charge", "70")
    await flush_debounce(hass)
    assert _feed(hass)["action"] == first

    # Resolve, then fire again -> same tag/action, new nonce.
    hass.states.async_set("binary_sensor.grid", "on")
    await flush_debounce(hass)
    hass.states.async_set("binary_sensor.grid", "off")
    await flush_debounce(hass)
    second = _feed(hass)["action"]
    assert second != first
    assert second.rsplit("|", 1)[0] == first.rsplit("|", 1)[0]


async def test_wall_action_fires_on_test_mode(hass: HomeAssistant):
    hass.states.async_set("binary_sensor.grid", "on")
    hass.states.async_set("sensor.charge", "80")
    await setup_nc(hass, _outage())
    await hass.services.async_call(DOMAIN, "test_rule", {"tag": "power_outage"}, blocking=True)
    await hass.async_block_till_done()
    assert _feed(hass)["action"].startswith("power_outage|sheet:outage,chime|")


async def test_wall_action_skipped_when_quiet_hours_suppress(hass: HomeAssistant):
    # Quiet hours cover the whole day; "suppress" keeps the alert on the wall
    # but skips interruptive delivery -> no wall action either.
    hass.states.async_set("binary_sensor.grid", "off")
    hass.states.async_set("sensor.charge", "80")
    await setup_nc(
        hass,
        _outage(quiet_hours_behavior="suppress"),
        options={"quiet_hours_start": "00:00:00", "quiet_hours_end": "23:59:59"},
    )
    assert count(hass) == "1"
    assert _feed(hass)["action"] == ""


async def test_wall_service_called_and_failure_is_a_repair(hass: HomeAssistant):
    nav = async_mock_service(hass, "esphome", "mudroom_navigate")
    hass.states.async_set("binary_sensor.grid", "off")
    hass.states.async_set("sensor.charge", "80")
    await setup_nc(
        hass,
        _outage(wall_service="esphome.mudroom_navigate"),
        rule_subentry(
            name="Broken", dedup_tag="broken", source_type="state",
            entity_id="binary_sensor.grid", operator="==", value="off",
            priority="info", channels=["wall"], wall_action="chime",
            wall_service="esphome.does_not_exist",
        ),
    )
    await hass.async_block_till_done()
    assert len(nav) == 1
    assert nav[0].data["tag"] == "power_outage"
    assert nav[0].data["action"] == "sheet:outage,chime"
    assert nav[0].data["title"] == "Power Outage"
    # The alert itself still shows; the bad service lands in Repairs.
    assert count(hass) == "2"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "delivery_esphome.does_not_exist") is not None


async def test_legacy_navigate_channel_is_dropped_not_fatal(hass: HomeAssistant):
    hass.states.async_set("binary_sensor.grid", "off")
    await setup_nc(
        hass,
        rule_subentry(
            name="Old", dedup_tag="old", source_type="state",
            entity_id="binary_sensor.grid", operator="==", value="off",
            priority="warning", channels=["wall", "navigate"],
        ),
    )
    assert count(hass) == "1"
    assert alerts(hass)[0]["channels"] == ["wall"]


async def test_recipients_limit_push_and_live_activity(hass: HomeAssistant):
    phone = async_mock_service(hass, "notify", "mobile_app_phone")
    tablet = async_mock_service(hass, "notify", "mobile_app_tablet")
    hass.states.async_set("person.alex", "home")
    hass.states.async_set("person.sam", "home")
    hass.states.async_set("input_boolean.a", "on")
    hass.states.async_set("input_boolean.b", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Only Alex", dedup_tag="only_alex", source_type="state",
            entity_id="input_boolean.a", operator="==", value="on",
            priority="warning", channels=["mobile"], recipients=["person.alex"],
        ),
        rule_subentry(
            name="LA Alex", dedup_tag="la_alex", source_type="state",
            entity_id="input_boolean.b", operator="==", value="on",
            priority="info", channels=["mobile"], recipients=["person.alex"],
            live_activity=True,
        ),
        options={
            "persons": [
                {"person": "person.alex", "notify": "notify.mobile_app_phone"},
                {"person": "person.sam", "notify": "notify.mobile_app_tablet"},
            ]
        },
    )
    # push + Live Activity start -> alex only.
    assert len(phone) == 2
    assert len(tablet) == 0
    # Live Activity end -> alex only too.
    hass.states.async_set("input_boolean.b", "off")
    await flush_debounce(hass)
    assert len(phone) == 3
    assert phone[-1].data["message"] == "clear_notification"
    assert len(tablet) == 0


async def test_unmapped_recipient_raises_repair(hass: HomeAssistant):
    async_mock_service(hass, "notify", "mobile_app_phone")
    hass.states.async_set("input_boolean.a", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Ghost", dedup_tag="ghost", source_type="state",
            entity_id="input_boolean.a", operator="==", value="on",
            priority="warning", channels=["mobile"], recipients=["person.nobody"],
        ),
        options={"persons": [{"person": "person.alex", "notify": "notify.mobile_app_phone"}]},
    )
    assert ir.async_get(hass).async_get_issue(DOMAIN, "recipient_unmapped_ghost") is not None
