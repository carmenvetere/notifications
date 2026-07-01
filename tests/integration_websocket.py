"""WebSocket rule-management API against a running HA."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.notification_center.const import DOMAIN


async def _setup_empty(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="NC", unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_ws_meta(hass: HomeAssistant, hass_ws_client):
    await _setup_empty(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/meta"})
    res = await client.receive_json()
    assert res["success"]
    assert res["result"]["priorities"] == ["critical", "warning", "info"]
    assert "info" in res["result"]["priority_defaults"]


async def test_ws_rule_crud(hass: HomeAssistant, hass_ws_client):
    await _setup_empty(hass)
    client = await hass_ws_client(hass)

    # create
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/rules/create",
            "rule": {
                "name": "Test rule",
                "dedup_tag": "test_rule",
                "source_type": "state",
                "entity_id": "binary_sensor.x",
                "operator": "==",
                "value": "on",
                "priority": "info",
                "channels": ["wall"],
            },
        }
    )
    res = await client.receive_json()
    assert res["success"]
    subentry_id = res["result"]["subentry_id"]

    # list
    await client.send_json({"id": 2, "type": f"{DOMAIN}/rules/list"})
    res = await client.receive_json()
    assert res["success"]
    rules = res["result"]["rules"]
    assert any(r["data"]["dedup_tag"] == "test_rule" for r in rules)
    created = next(r for r in rules if r["subentry_id"] == subentry_id)
    assert created["effective"]["clear_mode"] == "dismiss"

    # update
    await client.send_json(
        {
            "id": 3,
            "type": f"{DOMAIN}/rules/update",
            "subentry_id": subentry_id,
            "rule": {**created["data"], "priority": "critical"},
        }
    )
    res = await client.receive_json()
    assert res["success"]

    # delete
    await client.send_json(
        {"id": 4, "type": f"{DOMAIN}/rules/delete", "subentry_id": subentry_id}
    )
    res = await client.receive_json()
    assert res["success"]

    await client.send_json({"id": 5, "type": f"{DOMAIN}/rules/list"})
    res = await client.receive_json()
    assert not res["result"]["rules"]


async def test_ws_create_rule_rejects_invalid(hass: HomeAssistant, hass_ws_client):
    await _setup_empty(hass)
    client = await hass_ws_client(hass)

    # Bad priority enum.
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/rules/create",
            "rule": {"name": "Bad", "priority": "urgent"},
        }
    )
    res = await client.receive_json()
    assert not res["success"]
    assert res["error"]["code"] == "invalid_rule"

    # State rule missing its entity_id.
    await client.send_json(
        {
            "id": 2,
            "type": f"{DOMAIN}/rules/create",
            "rule": {"name": "NoEntity", "source_type": "state", "operator": "=="},
        }
    )
    res = await client.receive_json()
    assert not res["success"]
    assert res["error"]["code"] == "invalid_rule"

    # Empty name.
    await client.send_json(
        {
            "id": 3,
            "type": f"{DOMAIN}/rules/create",
            "rule": {"name": "", "priority": "info"},
        }
    )
    res = await client.receive_json()
    assert not res["success"]
    assert res["error"]["code"] == "invalid_rule"

    # Nothing was created.
    await client.send_json({"id": 4, "type": f"{DOMAIN}/rules/list"})
    res = await client.receive_json()
    assert not res["result"]["rules"]
