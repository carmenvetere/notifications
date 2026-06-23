"""Restart persistence: state survives an entry unload + re-setup."""

from homeassistant.core import HomeAssistant

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import alerts, count, rule_subentry, setup_nc


async def _reload(hass: HomeAssistant, entry) -> None:
    """Simulate a restart: unload (flushes state) then set the entry up again."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_active_alert_persists(hass: HomeAssistant):
    hass.states.async_set("input_boolean.y", "on")
    entry = await setup_nc(
        hass,
        rule_subentry(
            name="Y", dedup_tag="y", source_type="state",
            entity_id="input_boolean.y", operator="==", value="on", priority="info",
        ),
    )
    assert count(hass) == "1"
    created_first = alerts(hass)[0]["created_at"]

    await _reload(hass, entry)

    assert count(hass) == "1"
    # Same alert restored (not re-fired) — created_at is preserved.
    assert alerts(hass)[0]["created_at"] == created_first


async def test_dismiss_suppression_persists(hass: HomeAssistant):
    hass.states.async_set("input_boolean.x", "on")
    entry = await setup_nc(
        hass,
        rule_subentry(
            name="X", dedup_tag="x", source_type="state",
            entity_id="input_boolean.x", operator="==", value="on", priority="info",
        ),
    )
    await hass.services.async_call(DOMAIN, "dismiss", {"tag": "x"}, blocking=True)
    await hass.async_block_till_done()
    assert count(hass) == "0"

    await _reload(hass, entry)

    # Condition is still true, but the dismissal is remembered across the restart.
    assert count(hass) == "0"


async def test_resolved_while_down_clears_on_restart(hass: HomeAssistant):
    hass.states.async_set("input_boolean.z", "on")
    entry = await setup_nc(
        hass,
        rule_subentry(
            name="Z", dedup_tag="z", source_type="state",
            entity_id="input_boolean.z", operator="==", value="on", priority="info",
        ),
    )
    assert count(hass) == "1"

    # Condition resolves while "down", then we restart.
    hass.states.async_set("input_boolean.z", "off")
    await _reload(hass, entry)

    # Restored active alert auto-clears on the startup re-evaluation.
    assert count(hass) == "0"
