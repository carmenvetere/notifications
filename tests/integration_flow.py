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
    hass.states.async_set("person.alex", "home")
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)

    # The options flow opens on a menu.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU

    # Routing & timing settings -> back to the menu.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"debounce_ms": 500}
    )
    assert result["type"] == FlowResultType.MENU

    # Add a presence-mapped person without hand-writing JSON -> back to the menu.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "persons"}
    )
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"person": "person.alex", "notify": "notify.mobile_app_phone"},
    )
    assert result["type"] == FlowResultType.MENU

    # Save & close persists everything accumulated across the steps.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "finish"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["debounce_ms"] == 500
    assert entry.options["persons"] == [
        {"person": "person.alex", "notify": "notify.mobile_app_phone"}
    ]
