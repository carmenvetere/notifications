"""Custom-action resolution by stable id (G21), against a running HA."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import rule_subentry, setup_nc


async def test_run_action_resolves_by_stable_id(hass: HomeAssistant):
    a = async_mock_service(hass, "script", "a")
    b = async_mock_service(hass, "script", "b")
    hass.states.async_set("input_boolean.x", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="X", dedup_tag="x", source_type="state",
            entity_id="input_boolean.x", operator="==", value="on", priority="info",
            channels=["wall"],
            custom_actions=[
                {"id": "aa", "label": "A", "service": "script.a"},
                {"id": "bb", "label": "B", "service": "script.b"},
            ],
        ),
    )
    # Run the second action *by its id* — the correct service fires.
    await hass.services.async_call(
        DOMAIN, "run_action", {"tag": "x", "action": "bb"}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(a) == 0
    assert len(b) == 1


async def test_run_action_legacy_index_still_works(hass: HomeAssistant):
    a = async_mock_service(hass, "script", "a")
    b = async_mock_service(hass, "script", "b")
    hass.states.async_set("input_boolean.y", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Y", dedup_tag="y", source_type="state",
            entity_id="input_boolean.y", operator="==", value="on", priority="info",
            channels=["wall"],
            custom_actions=[  # no ids -> resolve by index
                {"label": "A", "service": "script.a"},
                {"label": "B", "service": "script.b"},
            ],
        ),
    )
    await hass.services.async_call(
        DOMAIN, "run_action", {"tag": "y", "action": "1"}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(a) == 0
    assert len(b) == 1
