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


async def test_mobile_rule_without_targets_raises_issue(hass: HomeAssistant):
    # A mobile-channel rule fires but no notify targets are configured.
    hass.states.async_set("input_boolean.m", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="M", dedup_tag="m", source_type="state",
            entity_id="input_boolean.m", operator="==", value="on", priority="warning",
            channels=["mobile"],
        ),
        options={},  # no mobile_targets / persons
    )
    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, "no_mobile_targets") is not None


async def test_test_push_service_delivers_to_targets(hass: HomeAssistant):
    from pytest_homeassistant_custom_component.common import async_mock_service

    calls = async_mock_service(hass, "notify", "mobile_app_test")
    await setup_nc(hass, options={"mobile_targets": ["notify.mobile_app_test"]})
    await hass.services.async_call(DOMAIN, "test_push", {}, blocking=True)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["title"] == "Notification Center"


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
