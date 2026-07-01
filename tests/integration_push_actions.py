"""Actionable push: mobile_app_notification_action events route to the engine."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.helpers_ha import count, rule_subentry, setup_nc


async def _fire(hass: HomeAssistant, action: str) -> None:
    hass.bus.async_fire("mobile_app_notification_action", {"action": action})
    await hass.async_block_till_done()


async def test_push_dismiss(hass: HomeAssistant):
    hass.states.async_set("input_boolean.a", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Info", dedup_tag="info1", source_type="state",
            entity_id="input_boolean.a", operator="==", value="on", priority="info",
        ),
    )
    assert count(hass) == "1"
    await _fire(hass, "NC::DISMISS::info1")
    assert count(hass) == "0"


async def test_push_dismiss_ignores_locked(hass: HomeAssistant):
    hass.states.async_set("input_boolean.w", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Warn", dedup_tag="warn1", source_type="state",
            entity_id="input_boolean.w", operator="==", value="on", priority="warning",
        ),
    )
    # Warning is locked — a dismiss action is a no-op.
    await _fire(hass, "NC::DISMISS::warn1")
    assert count(hass) == "1"


async def test_push_run_action(hass: HomeAssistant):
    calls = async_mock_service(hass, "script", "reset_x")
    hass.states.async_set("input_number.f", "3000")
    await setup_nc(
        hass,
        rule_subentry(
            name="Filter", dedup_tag="filter1", source_type="numeric",
            entity_id="input_number.f", operator=">", value=2000, priority="info",
            custom_actions=[{"label": "Done", "service": "script.reset_x"}],
        ),
    )
    await _fire(hass, "NC::RUN::filter1::0")
    assert len(calls) == 1
    assert count(hass) == "0"


async def test_push_action_unknown_tag_ignored(hass: HomeAssistant):
    await setup_nc(hass)  # no rules
    await _fire(hass, "NC::DISMISS::nope")  # should not raise
    assert count(hass) == "0"
