"""Config, options and subentry flows, against a running Home Assistant."""

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.notification_center.const import DOMAIN


async def test_single_instance(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # A second attempt is rejected — single instance.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.ABORT


async def test_options_flow(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"debounce_ms": 500}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["debounce_ms"] == 500


async def test_add_rule_subentry_flow(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    flow = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "rule"), context={"source": "user"}
    )
    assert flow["type"] == FlowResultType.FORM

    async def step(user_input):
        return await hass.config_entries.subentries.async_configure(
            flow["flow_id"], user_input
        )

    # trigger -> (template) -> priority -> channels -> message -> advanced
    await step({"name": "T", "enabled": True, "source_type": "template"})
    await step({"condition_template": "{{ true }}"})
    await step({"priority": "info"})
    await step({"channels": []})
    await step({})  # message
    result = await step(
        {
            "actions_follow_priority": True,
            "auto_clear": True,
            "quiet_hours_behavior": "downgrade",
            "presence_routing": "all",
        }
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert any(s.subentry_type == "rule" for s in entry.subentries.values())
