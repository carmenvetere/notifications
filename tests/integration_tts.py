"""Spoken (TTS) announcements: tts.speak must name its engine, against a running HA."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import rule_subentry, setup_nc

SPEAKERS = "media_player.kitchen_speaker"


def _outage_rule():
    return rule_subentry(
        name="Power Outage", dedup_tag="power_outage", source_type="state",
        entity_id="binary_sensor.grid_status", operator="==", value="off",
        priority="critical", channels=["tts"],
    )


async def test_speak_uses_cloud_engine_automatically(hass: HomeAssistant):
    speak = async_mock_service(hass, "tts", "speak")
    hass.states.async_set("tts.home_assistant_cloud", "unknown")
    hass.states.async_set("tts.other_engine", "unknown")
    hass.states.async_set("binary_sensor.grid_status", "off")
    await setup_nc(
        hass, _outage_rule(), options={"tts_default_targets": [SPEAKERS]}
    )
    assert len(speak) == 1
    data = speak[0].data
    # The engine is the action's target; without it HA runs it on nothing.
    assert data["entity_id"] in ("tts.home_assistant_cloud", ["tts.home_assistant_cloud"])
    assert data["media_player_entity_id"] == [SPEAKERS]
    assert "Power Outage" in data["message"]
    assert ir.async_get(hass).async_get_issue(DOMAIN, "no_tts_engine") is None


async def test_configured_engine_wins(hass: HomeAssistant):
    speak = async_mock_service(hass, "tts", "speak")
    hass.states.async_set("tts.home_assistant_cloud", "unknown")
    hass.states.async_set("tts.piper", "unknown")
    hass.states.async_set("binary_sensor.grid_status", "off")
    await setup_nc(
        hass,
        _outage_rule(),
        options={"tts_default_targets": [SPEAKERS], "tts_engine": "tts.piper"},
    )
    assert len(speak) == 1
    assert speak[0].data["entity_id"] in ("tts.piper", ["tts.piper"])


async def test_no_engine_raises_repair_instead_of_silence(hass: HomeAssistant):
    speak = async_mock_service(hass, "tts", "speak")
    hass.states.async_set("binary_sensor.grid_status", "off")
    await setup_nc(
        hass, _outage_rule(), options={"tts_default_targets": [SPEAKERS]}
    )
    # No engine exists: nothing is sent, and the failure is visible in Repairs.
    assert len(speak) == 0
    assert ir.async_get(hass).async_get_issue(DOMAIN, "no_tts_engine") is not None
