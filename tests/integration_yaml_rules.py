"""YAML-mode rules (#47): file as sole source, read-only panel, export."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import count, rule_subentry, setup_nc

GARAGE_RULE = {
    "name": "Garage door left open",
    "dedup_tag": "garage_open",
    "source_type": "state",
    "entity_id": "binary_sensor.garage_door",
    "operator": "==",
    "value": "on",
    "priority": "warning",
    "channels": ["wall"],
    "quiet_hours_behavior": "ignore",
}


async def _setup_yaml(hass: HomeAssistant, rules: list[dict]) -> MockConfigEntry:
    """Set up the integration with YAML-mode rules (entry + component config)."""
    entry = MockConfigEntry(domain=DOMAIN, title="NC", unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {"rules": rules}})
    await hass.async_block_till_done()
    return entry


async def test_yaml_rules_load_and_fire(hass: HomeAssistant):
    hass.states.async_set("binary_sensor.garage_door", "on")
    await _setup_yaml(hass, [GARAGE_RULE])
    assert count(hass) == "1"


async def test_yaml_mode_panel_is_read_only(hass: HomeAssistant, hass_ws_client):
    await _setup_yaml(hass, [GARAGE_RULE])
    client = await hass_ws_client(hass)

    # meta advertises yaml mode so the panel renders the read-only banner.
    await client.send_json({"id": 1, "type": f"{DOMAIN}/meta"})
    res = await client.receive_json()
    assert res["result"]["yaml_mode"] is True

    # list serves the file rules.
    await client.send_json({"id": 2, "type": f"{DOMAIN}/rules/list"})
    res = await client.receive_json()
    assert res["result"]["yaml_mode"] is True
    assert [r["data"]["dedup_tag"] for r in res["result"]["rules"]] == ["garage_open"]

    # mutations are rejected.
    await client.send_json(
        {"id": 3, "type": f"{DOMAIN}/rules/create", "rule": {"name": "X"}}
    )
    res = await client.receive_json()
    assert not res["success"]
    assert res["error"]["code"] == "read_only"

    await client.send_json(
        {"id": 4, "type": f"{DOMAIN}/rules/delete", "subentry_id": "yaml_garage_open"}
    )
    res = await client.receive_json()
    assert not res["success"]
    assert res["error"]["code"] == "read_only"


async def test_invalid_yaml_rule_skipped_with_repair(hass: HomeAssistant):
    hass.states.async_set("binary_sensor.garage_door", "on")
    bad = {"name": "Broken", "priority": "urgent"}  # invalid priority enum
    await _setup_yaml(hass, [GARAGE_RULE, bad])
    # The good rule still loaded and fired…
    assert count(hass) == "1"
    # …and the bad one is surfaced as a repair, not silently dropped.
    reg = ir.async_get(hass)
    issue = reg.async_get_issue(DOMAIN, "yaml_rules_invalid")
    assert issue is not None
    assert "Broken" in (issue.translation_placeholders or {}).get("errors", "")


async def test_export_rules_returns_yaml(hass: HomeAssistant):
    # Subentry mode: export what the panel manages, as data + YAML text.
    hass.states.async_set("input_boolean.x", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="X", dedup_tag="x", source_type="state",
            entity_id="input_boolean.x", operator="==", value="on", priority="info",
        ),
    )
    response = await hass.services.async_call(
        DOMAIN, "export_rules", {}, blocking=True, return_response=True
    )
    assert response["count"] == 1
    assert response["rules"][0]["dedup_tag"] == "x"
    assert "dedup_tag: x" in response["yaml"]
