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


async def test_options_flow_points_to_panel_settings(hass: HomeAssistant):
    """The Configure dialog is one screen that links to the panel's Settings
    tab; submitting it keeps the stored options unchanged."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={}, version=3,
        options={"people": [{"person": "person.alex", "phones": ["notify.mobile_app_alex"]}], "debounce_ms": 500},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["description_placeholders"]["settings_url"].endswith("#settings")
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["debounce_ms"] == 500
    assert entry.options["people"][0]["phones"] == ["notify.mobile_app_alex"]
