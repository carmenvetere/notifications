"""Repair issues for misconfiguration, against a running Home Assistant."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import rule_subentry, setup_nc


async def test_delivery_failure_raises_and_clears_issue(hass: HomeAssistant):
    hass.states.async_set("input_boolean.d", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="D", dedup_tag="d", source_type="state",
            entity_id="input_boolean.d", operator="==", value="on", priority="critical",
            channels=["mobile"],
        ),
        options={"mobile_targets": ["notify.does_not_exist"]},
    )
    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, "delivery_notify.does_not_exist") is not None


async def test_template_syntax_error_raises_issue(hass: HomeAssistant):
    await setup_nc(
        hass,
        rule_subentry(
            name="T", dedup_tag="t", source_type="template",
            condition_template="{{ this is not valid ",
        ),
    )
    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, "template_t") is not None


async def test_valid_rule_has_no_issue(hass: HomeAssistant):
    hass.states.async_set("input_boolean.ok", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="OK", dedup_tag="ok", source_type="state",
            entity_id="input_boolean.ok", operator="==", value="on", priority="info",
            channels=["wall"],
        ),
    )
    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, "template_ok") is None
