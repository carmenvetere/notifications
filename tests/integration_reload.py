"""Live-reload refreshes the display of already-active alerts."""

from homeassistant.core import HomeAssistant

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import alerts, rule_subentry, setup_nc


async def test_edit_adds_button_to_active_alert(hass: HomeAssistant):
    hass.states.async_set("input_boolean.g", "on")
    entry = await setup_nc(
        hass,
        rule_subentry(
            name="Garage", dedup_tag="garage", source_type="state",
            entity_id="input_boolean.g", operator="==", value="on",
            priority="warning", channels=["wall"],
        ),
    )
    # Active, but the rule has no custom actions yet.
    assert alerts(hass)[0]["buttons"] == []

    # Edit the rule: add a "Close garage" custom action, then live-reload.
    subentry = next(iter(entry.subentries.values()))
    data = {
        **dict(subentry.data),
        "custom_actions": [
            {
                "label": "Close garage",
                "entity": "cover.garage",
                "service": "cover.close_cover",
                "target": {"entity_id": "cover.garage"},
            }
        ],
    }
    hass.config_entries.async_update_subentry(entry, subentry, data=data)
    engine = hass.data[DOMAIN][entry.entry_id]
    await engine.async_reload()
    await hass.async_block_till_done()

    # The already-active alert now shows the new button (no re-fire needed).
    assert [b["label"] for b in alerts(hass)[0]["buttons"]] == ["Close garage"]
