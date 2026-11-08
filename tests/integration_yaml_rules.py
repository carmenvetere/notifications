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


async def test_wrapped_rules_file_is_unwrapped(hass: HomeAssistant):
    # Common mistake #1: the included file has its own top-level `rules:` key,
    # so the configured value is {"rules": [...]} instead of the bare list.
    hass.states.async_set("binary_sensor.garage_door", "on")
    await _setup_yaml(hass, [{"rules": [GARAGE_RULE]}])
    assert count(hass) == "1"
    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, "yaml_rules_invalid") is None


async def test_pasted_export_response_is_unwrapped(hass: HomeAssistant):
    # Common mistake #2: the whole export_rules response was saved to the file
    # (count / rules / yaml) instead of just the yaml field's contents.
    hass.states.async_set("binary_sensor.garage_door", "on")
    wrapped = {"count": 1, "rules": [GARAGE_RULE], "yaml": "..."}
    await _setup_yaml(hass, [wrapped])
    assert count(hass) == "1"


async def test_invalid_rules_hidden_from_panel_list(hass: HomeAssistant, hass_ws_client):
    # The panel list must match what the engine loaded — no junk rows for
    # rules that failed validation (those are covered by the repair issue).
    await _setup_yaml(hass, [GARAGE_RULE, {"name": "Broken", "priority": "urgent"}])
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/rules/list"})
    res = await client.receive_json()
    assert [r["data"]["dedup_tag"] for r in res["result"]["rules"]] == ["garage_open"]


# --- rules_file mode: the file is the source of truth AND the panel edits it ---

RULES_REL = "notification_center/rules.yaml"


def _write_rules(hass: HomeAssistant, rules: list[dict]) -> str:
    import os

    from homeassistant.util.yaml import dump

    path = hass.config.path(RULES_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(dump(rules))
    return path


def _read_rules(path: str) -> list[dict]:
    from homeassistant.util.yaml import load_yaml

    return list(load_yaml(path) or [])


async def _setup_file_mode(hass: HomeAssistant, tmp_path, rules: list[dict]) -> str:
    hass.config.config_dir = str(tmp_path)
    path = _write_rules(hass, rules)
    entry = MockConfigEntry(domain=DOMAIN, title="NC", unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {"rules_file": RULES_REL}})
    await hass.async_block_till_done()
    return path


async def test_rules_file_loads_and_panel_is_editable(hass: HomeAssistant, hass_ws_client, tmp_path):
    hass.states.async_set("binary_sensor.garage_door", "on")
    await _setup_file_mode(hass, tmp_path, [GARAGE_RULE])
    assert count(hass) == "1"

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/meta"})
    res = await client.receive_json()
    assert res["result"]["yaml_mode"] is True
    assert res["result"]["read_only"] is False
    assert res["result"]["rules_file"] == RULES_REL


async def test_rules_file_panel_create_update_delete_write_the_file(
    hass: HomeAssistant, hass_ws_client, tmp_path
):
    hass.states.async_set("binary_sensor.garage_door", "off")
    hass.states.async_set("input_boolean.leak", "on")
    path = await _setup_file_mode(hass, tmp_path, [GARAGE_RULE])
    client = await hass_ws_client(hass)

    # create -> appended to the file and live in the engine right away.
    leak = {
        "name": "Leak", "dedup_tag": "leak", "source_type": "state",
        "entity_id": "input_boolean.leak", "operator": "==", "value": "on",
        "priority": "critical", "channels": ["wall"], "quiet_hours_behavior": "ignore",
    }
    await client.send_json({"id": 1, "type": f"{DOMAIN}/rules/create", "rule": leak})
    res = await client.receive_json()
    assert res["success"], res
    assert res["result"]["subentry_id"] == "yaml_leak"
    await hass.async_block_till_done()
    assert [r["dedup_tag"] for r in _read_rules(path)] == ["garage_open", "leak"]
    assert count(hass) == "1"  # the leak rule fired

    # update (rename the tag) -> file rewritten under the new tag.
    await client.send_json(
        {"id": 2, "type": f"{DOMAIN}/rules/update", "subentry_id": "yaml_leak",
         "rule": {**leak, "dedup_tag": "water_leak"}}
    )
    res = await client.receive_json()
    assert res["success"], res
    assert res["result"]["subentry_id"] == "yaml_water_leak"
    assert [r["dedup_tag"] for r in _read_rules(path)] == ["garage_open", "water_leak"]

    # delete -> gone from the file and the engine.
    await client.send_json(
        {"id": 3, "type": f"{DOMAIN}/rules/delete", "subentry_id": "yaml_water_leak"}
    )
    res = await client.receive_json()
    assert res["success"], res
    await hass.async_block_till_done()
    assert [r["dedup_tag"] for r in _read_rules(path)] == ["garage_open"]
    assert count(hass) == "0"


async def test_rules_file_external_edit_applies_on_reload(hass: HomeAssistant, tmp_path):
    hass.states.async_set("binary_sensor.garage_door", "on")
    hass.states.async_set("input_boolean.leak", "on")
    path = await _setup_file_mode(hass, tmp_path, [GARAGE_RULE])
    assert count(hass) == "1"

    # Edit the file outside the panel (git / editor / Claude Code)…
    leak = {**GARAGE_RULE, "name": "Leak", "dedup_tag": "leak",
            "entity_id": "input_boolean.leak"}
    _write_rules(hass, [GARAGE_RULE, leak])
    # …and reload: the new rule is live.
    await hass.services.async_call(DOMAIN, "reload", {}, blocking=True)
    await hass.async_block_till_done()
    assert count(hass) == "2"


async def test_rules_file_bad_yaml_keeps_last_good_rules(hass: HomeAssistant, tmp_path):
    hass.states.async_set("binary_sensor.garage_door", "on")
    path = await _setup_file_mode(hass, tmp_path, [GARAGE_RULE])
    assert count(hass) == "1"

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("- name: broken\n  channels: [wall\n")  # unterminated list
    await hass.services.async_call(DOMAIN, "reload", {}, blocking=True)
    await hass.async_block_till_done()
    # Rules survive, and the problem is visible in Repairs.
    assert count(hass) == "1"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "yaml_rules_file_error") is not None


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
