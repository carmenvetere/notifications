"""Custom-action resolution by stable id (G21), against a running HA."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import alerts, rule_subentry, setup_nc


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


async def test_single_action_runs_despite_mismatched_id(hass: HomeAssistant):
    # Reproduces a stale/cached card sending a non-matching action id ("None"):
    # a single-action notification should still run its one action.
    a = async_mock_service(hass, "script", "reset_vacuum")
    hass.states.async_set("input_boolean.pool", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Pool", dedup_tag="pool", source_type="state",
            entity_id="input_boolean.pool", operator="==", value="on", priority="info",
            channels=["wall"],
            custom_actions=[
                {"id": "a3k9x2", "label": "I vacuumed it",
                 "service": "script.reset_vacuum"}
            ],
        ),
    )
    await hass.services.async_call(
        DOMAIN, "run_action", {"tag": "pool", "action": "None"}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(a) == 1


async def test_failed_action_keeps_alert_and_raises_issue(hass: HomeAssistant):
    hass.states.async_set("input_boolean.z", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Z", dedup_tag="z", source_type="state",
            entity_id="input_boolean.z", operator="==", value="on", priority="info",
            channels=["wall"],
            custom_actions=[
                {"id": "reset", "label": "Reset", "service": "script.does_not_exist"}
            ],
        ),
    )
    assert len(alerts(hass)) == 1

    # The service/script doesn't exist -> the action fails.
    await hass.services.async_call(
        DOMAIN, "run_action", {"tag": "z", "action": "reset"}, blocking=True
    )
    await hass.async_block_till_done()

    # Alert is kept (not silently cleared) and a repair issue is raised.
    assert len(alerts(hass)) == 1
    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, "action_script.does_not_exist") is not None
