"""Config-entry migration (v1 -> v2), against a running Home Assistant."""

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.notification_center.const import DOMAIN


async def test_migrate_v1_rules_to_v2(hass: HomeAssistant):
    # A v1 entry with a legacy rule: the old "digest" priority, the retired
    # "acknowledge" clear mode, and an empty cooldown string.
    legacy = ConfigSubentryData(
        data={
            "name": "Batteries",
            "dedup_tag": "batt",
            "source_type": "template",
            "condition_template": "{{ true }}",
            "priority": "digest",
            "clear_mode": "acknowledge",
            "cooldown": "",
            "channels": ["wall"],
            "quiet_hours_behavior": "ignore",
        },
        subentry_type="rule",
        title="Batteries",
        unique_id="batt",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Notification Center",
        unique_id=DOMAIN,
        version=1,
        data={},
        subentries_data=[legacy],
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Entry version bumped.
    assert entry.version == 2

    # Rule normalized: digest -> info + deliver_as_digest; acknowledge dropped;
    # empty cooldown removed.
    subentry = next(iter(entry.subentries.values()))
    data = dict(subentry.data)
    assert data["priority"] == "info"
    assert data["deliver_as_digest"] is True
    assert "clear_mode" not in data
    assert "cooldown" not in data
