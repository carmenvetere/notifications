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

    # Entry version bumped (v1 -> v2 -> v3).
    assert entry.version == 3

    # Rule normalized: digest -> info + deliver_as_digest; acknowledge dropped;
    # empty cooldown removed.
    subentry = next(iter(entry.subentries.values()))
    data = dict(subentry.data)
    assert data["priority"] == "info"
    assert data["deliver_as_digest"] is True
    assert "clear_mode" not in data
    assert "cooldown" not in data


async def test_migrate_v2_options_to_one_phone_list(hass: HomeAssistant):
    """v2 -> v3: people get a list of phones, the per-person speaker is
    dropped, unmapped mobile targets become "other phones", and default TTS
    targets become default speakers."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Notification Center",
        unique_id=DOMAIN,
        version=2,
        data={},
        options={
            "persons": [
                {"person": "person.alex", "notify": "notify.mobile_app_alex", "media_player": "media_player.den"},
                {"person": "person.alex", "notify": "notify.mobile_app_alex_ipad"},
                {"person": "person.sam", "notify": "notify.mobile_app_sam"},
            ],
            "mobile_targets": ["notify.mobile_app_sam", "notify.mobile_app_hall_tablet"],
            "tts_default_targets": ["media_player.kitchen"],
            "debounce_ms": 400,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 3
    opts = entry.options
    assert opts["people"] == [
        {"person": "person.alex", "phones": ["notify.mobile_app_alex", "notify.mobile_app_alex_ipad"]},
        {"person": "person.sam", "phones": ["notify.mobile_app_sam"]},
    ]
    assert opts["other_phones"] == ["notify.mobile_app_hall_tablet"]
    assert opts["default_media_players"] == ["media_player.kitchen"]
    assert opts["debounce_ms"] == 400
    for legacy in ("persons", "mobile_targets", "tts_default_targets"):
        assert legacy not in opts
    assert "media_player" not in str(opts["people"])
