"""Service behavior + clearing-model gating against a running HA."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import count, flush_debounce, rule_subentry, setup_nc


async def test_dismiss_gated_by_clear_mode(hass: HomeAssistant):
    hass.states.async_set("input_boolean.info", "on")
    hass.states.async_set("input_boolean.warn", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Info", dedup_tag="info1", source_type="state",
            entity_id="input_boolean.info", operator="==", value="on", priority="info",
        ),
        rule_subentry(
            name="Warn", dedup_tag="warn1", source_type="state",
            entity_id="input_boolean.warn", operator="==", value="on", priority="warning",
        ),
    )
    assert count(hass) == "2"

    # Info can be dismissed.
    await hass.services.async_call(DOMAIN, "dismiss", {"tag": "info1"}, blocking=True)
    await hass.async_block_till_done()
    assert count(hass) == "1"

    # Warning is locked — dismiss is a no-op.
    await hass.services.async_call(DOMAIN, "dismiss", {"tag": "warn1"}, blocking=True)
    await hass.async_block_till_done()
    assert count(hass) == "1"


async def test_dismiss_sticky_until_resolved(hass: HomeAssistant):
    hass.states.async_set("input_boolean.info", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="Info", dedup_tag="info1", source_type="state",
            entity_id="input_boolean.info", operator="==", value="on", priority="info",
        ),
    )
    await hass.services.async_call(DOMAIN, "dismiss", {"tag": "info1"}, blocking=True)
    await hass.async_block_till_done()
    assert count(hass) == "0"

    # Still true -> stays hidden until it resolves and re-fires.
    hass.states.async_set("input_boolean.info", "off")
    await flush_debounce(hass)
    hass.states.async_set("input_boolean.info", "on")
    await flush_debounce(hass)
    assert count(hass) == "1"


async def test_run_action_calls_service_and_clears(hass: HomeAssistant):
    calls = async_mock_service(hass, "script", "reset_filter")
    hass.states.async_set("input_number.filter", "3000")
    await setup_nc(
        hass,
        rule_subentry(
            name="Filter", dedup_tag="filter1", source_type="numeric",
            entity_id="input_number.filter", operator=">", value=2000, priority="info",
            custom_actions=[
                {"label": "I replaced it", "service": "script.reset_filter", "clear_on_run": True}
            ],
        ),
    )
    assert count(hass) == "1"

    await hass.services.async_call(
        DOMAIN, "run_action", {"tag": "filter1", "action": 0}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert count(hass) == "0"


async def test_send_manual_alert(hass: HomeAssistant):
    await setup_nc(hass)  # no rules
    await hass.services.async_call(
        DOMAIN,
        "send",
        {"tag": "manual1", "title": "Hi", "message": "there", "priority": "info", "channels": ["wall"]},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert count(hass) == "1"
