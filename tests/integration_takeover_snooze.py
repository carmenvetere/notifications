"""Wall takeover pill, snooze choices + snooze expiry, quiet-hours defaults."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import alerts, count, flush_debounce, rule_subentry, setup_nc


def _feed(hass: HomeAssistant) -> dict:
    return hass.states.get("sensor.notification_center_wall").attributes


def _rule(**kw):
    base = dict(source_type="state", operator="==", value="on", channels=["wall"])
    base.update(kw)
    return rule_subentry(**base)


async def test_takeover_pill_selection_and_refresh(hass: HomeAssistant):
    hass.states.async_set("input_boolean.vacation", "on")
    hass.states.async_set("input_boolean.outage", "off")
    hass.states.async_set("sensor.charge", "76")
    await setup_nc(
        hass,
        _rule(name="Vacation mode", dedup_tag="vacation", entity_id="input_boolean.vacation",
              priority="warning", wall_takeover=True, wall_takeover_target="page:settings"),
        _rule(name="Power outage", dedup_tag="outage", entity_id="input_boolean.outage",
              priority="critical", title_template="Power Outage!", wall_takeover=True,
              wall_takeover_target="page:energy", wall_action="sheet:outage,chime",
              live_activity=True, critical_text_template="{{ states('sensor.charge') }}%",
              channels=["wall", "mobile"]),
        _rule(name="Info thing", dedup_tag="info", entity_id="input_boolean.vacation",
              priority="info", wall_takeover=True),
    )
    f = _feed(hass)
    assert f["takeover"] == "vacation|warning|page:settings|0|Vacation mode"
    assert f["takeover_level"] == "warning"
    assert f["action"] == ""  # a pill never fires an action by itself

    hass.states.async_set("input_boolean.outage", "on")
    await flush_debounce(hass)
    f = _feed(hass)
    assert f["takeover"] == "outage|critical|page:energy|0|Power Outage! 76%"
    nonce = f["action"]
    assert nonce.startswith("outage|sheet:outage,chime|")

    # Battery changes (not the rule's own entity): the periodic content
    # refresh updates the pill text, and action/nonce don't change.
    hass.states.async_set("sensor.charge", "70")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    f = _feed(hass)
    assert f["takeover_text"] == "Power Outage! 70%"
    assert f["action"] == nonce

    # Outage resolves -> falls back to vacation; critical_text unchanged rules.
    hass.states.async_set("input_boolean.outage", "off")
    await flush_debounce(hass)
    assert _feed(hass)["takeover_tag"] == "vacation"


async def test_snooze_fields_and_expiry(hass: HomeAssistant):
    hass.states.async_set("input_boolean.salt", "on")
    await setup_nc(
        hass,
        _rule(name="Pool salt low", dedup_tag="salt", entity_id="input_boolean.salt",
              priority="info", snooze_options=[60, 240]),
        _rule(name="Warn", dedup_tag="warn", entity_id="input_boolean.salt", priority="warning"),
    )
    rows = {r.split("|")[0]: r.split("|") for r in _feed(hass)["items"].split(";")}
    assert rows["salt"][7:9] == ["1", "60,240"]
    assert rows["warn"][7:9] == ["0", ""]
    assert next(a for a in alerts(hass) if a["tag"] == "salt")["snooze_options"] == [60, 240]

    with freeze_time(dt_util.utcnow()) as frozen:
        await hass.services.async_call(DOMAIN, "snooze", {"tag": "salt", "minutes": 60}, blocking=True)
        await hass.async_block_till_done()
        assert count(hass) == "1"

        # Nothing about the entity changes, yet the alert comes back after 60 min.
        frozen.move_to(dt_util.utcnow() + timedelta(minutes=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        frozen.move_to(dt_util.utcnow() + timedelta(seconds=2))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert count(hass) == "2"


async def test_quiet_hours_defaults_and_send_quietly(hass: HomeAssistant):
    push = async_mock_service(hass, "notify", "mobile_app_x")
    speak = async_mock_service(hass, "tts", "speak")
    hass.states.async_set("tts.home_assistant_cloud", "unknown")
    hass.states.async_set("input_boolean.w", "on")
    # Quiet all day; the warning rule doesn't set quiet_hours_behavior, so it
    # takes the priority default: downgrade = silent push, nothing spoken.
    await setup_nc(
        hass,
        rule_subentry(name="W", dedup_tag="w", source_type="state", entity_id="input_boolean.w",
                      operator="==", value="on", priority="warning", channels=["mobile", "tts"],
                      quiet_hours_behavior=None, tts_targets=["media_player.kitchen"]),
        options={"other_phones": ["notify.mobile_app_x"], "quiet_hours_start": "00:00:00",
                 "quiet_hours_end": "23:59:59"},
    )
    assert len(push) == 1
    assert push[0].data["data"]["push"]["interruption-level"] == "passive"
    assert len(speak) == 0
