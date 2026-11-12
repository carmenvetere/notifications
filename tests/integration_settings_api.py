"""Settings tab backend: settings/get|update, test push / announcement, health,
template render, history, rule status — against a running Home Assistant."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.notification_center.const import DOMAIN
from tests.helpers_ha import count, rule_subentry, setup_nc

PEOPLE = {
    "people": [
        {"person": "person.alex", "phones": ["notify.mobile_app_alex", "notify.mobile_app_alex_ipad"]},
        {"person": "person.sam", "phones": []},
    ],
    "other_phones": ["notify.mobile_app_hall"],
}


async def _ws(client, payload):
    await client.send_json(payload)
    return await client.receive_json()


async def test_settings_get_and_update_round_trip(hass: HomeAssistant, hass_ws_client):
    entry = await setup_nc(hass, options={"persons": [{"person": "person.alex", "notify": "notify.mobile_app_alex"}]})
    client = await hass_ws_client(hass)

    res = await _ws(client, {"id": 1, "type": f"{DOMAIN}/settings/get"})
    assert res["success"], res
    st = res["result"]["settings"]
    # Legacy options are read through the new model.
    assert st["people"] == [{"person": "person.alex", "phones": ["notify.mobile_app_alex"]}]
    assert st["quiet_hours_enabled"] is True
    assert st["wall_sounds"] == ["chime"]

    st.update(PEOPLE, default_media_players=["media_player.kitchen"], quiet_hours_enabled=False,
              quiet_hours_start="23:00", digest_time="09:30", wall_sounds=["chime", "alarm"])
    res = await _ws(client, {"id": 2, "type": f"{DOMAIN}/settings/update", "settings": st})
    assert res["success"], res
    assert entry.options["people"] == PEOPLE["people"]
    assert entry.options["other_phones"] == ["notify.mobile_app_hall"]
    assert entry.options["quiet_hours_start"] == "23:00:00"
    assert entry.options["digest_time"] == "09:30:00"
    assert "persons" not in entry.options
    assert entry.options["wall_sounds"] == ["chime", "alarm"]

    # Health: Sam has no phone.
    kinds = [(h["kind"], h.get("person")) for h in res["result"]["health"]]
    assert ("person_no_phone", "person.sam") in kinds


async def test_everyone_reaches_every_phone_once(hass: HomeAssistant):
    calls = {name: async_mock_service(hass, "notify", name) for name in ("mobile_app_alex", "mobile_app_alex_ipad", "mobile_app_hall")}
    hass.states.async_set("person.alex", "home")
    hass.states.async_set("input_boolean.x", "on")
    await setup_nc(
        hass,
        rule_subentry(name="X", dedup_tag="x", source_type="state", entity_id="input_boolean.x",
                      operator="==", value="on", priority="warning", channels=["mobile"]),
        options=PEOPLE,
    )
    assert {n: len(c) for n, c in calls.items()} == {"mobile_app_alex": 1, "mobile_app_alex_ipad": 1, "mobile_app_hall": 1}


async def test_test_push_reports_result(hass: HomeAssistant, hass_ws_client):
    async_mock_service(hass, "notify", "mobile_app_alex")
    await setup_nc(hass, options=PEOPLE)
    client = await hass_ws_client(hass)

    res = await _ws(client, {"id": 1, "type": f"{DOMAIN}/settings/test_push", "notify_service": "notify.mobile_app_alex"})
    assert res["result"] == {"ok": True, "error": None}

    res = await _ws(client, {"id": 2, "type": f"{DOMAIN}/settings/test_push", "notify_service": "notify.mobile_app_gone"})
    assert res["result"]["ok"] is False
    assert "doesn't exist" in res["result"]["error"]

    # The failure shows in Health for a configured phone.
    res = await _ws(client, {"id": 3, "type": f"{DOMAIN}/settings/test_push", "notify_service": "notify.mobile_app_hall"})
    assert res["result"]["ok"] is False
    res = await _ws(client, {"id": 4, "type": f"{DOMAIN}/settings/get"})
    assert {"kind": "phone_failed", "phone": "notify.mobile_app_hall"}.items() <= next(
        h for h in res["result"]["health"] if h["kind"] == "phone_failed"
    ).items()


async def test_test_announcement(hass: HomeAssistant, hass_ws_client):
    speak = async_mock_service(hass, "tts", "speak")
    await setup_nc(hass)
    client = await hass_ws_client(hass)

    res = await _ws(client, {"id": 1, "type": f"{DOMAIN}/settings/test_announcement", "media_players": []})
    assert res["result"]["error"] == "Pick at least one default speaker first."

    res = await _ws(client, {"id": 2, "type": f"{DOMAIN}/settings/test_announcement", "media_players": ["media_player.kitchen"]})
    assert res["result"]["error"] == "There is no voice available."

    hass.states.async_set("tts.home_assistant_cloud", "unknown")
    res = await _ws(client, {"id": 3, "type": f"{DOMAIN}/settings/test_announcement", "media_players": ["media_player.kitchen"]})
    assert res["result"] == {"ok": True, "error": None}
    assert speak[0].data["entity_id"] == "tts.home_assistant_cloud"
    assert speak[0].data["media_player_entity_id"] == ["media_player.kitchen"]


async def test_render_batch(hass: HomeAssistant, hass_ws_client):
    hass.states.async_set("sensor.charge", "76")
    await setup_nc(hass)
    client = await hass_ws_client(hass)
    res = await _ws(client, {
        "id": 1, "type": f"{DOMAIN}/render",
        "templates": {
            "title": "Power Outage! {{ states('sensor.charge') | int }}%",
            "plain": "Just text",
            "bad": "{{ states('sensor.charge') | nope }}",
        },
    })
    r = res["result"]["results"]
    assert r["title"] == {"text": "Power Outage! 76%"}
    assert r["plain"] == {"text": "Just text"}
    assert "error" in r["bad"]


async def test_rule_status_and_history(hass: HomeAssistant, hass_ws_client):
    hass.states.async_set("input_boolean.x", "on")
    await setup_nc(
        hass,
        rule_subentry(name="X", dedup_tag="x", source_type="state", entity_id="input_boolean.x",
                      operator="==", value="on", priority="info", channels=["wall"]),
    )
    client = await hass_ws_client(hass)
    res = await _ws(client, {"id": 1, "type": f"{DOMAIN}/rules/list"})
    row = res["result"]["rules"][0]
    assert row["active"] is True and row["testing"] is False and row["active_since"]

    await hass.services.async_call(DOMAIN, "dismiss", {"tag": "x"}, blocking=True)
    await hass.async_block_till_done()
    assert count(hass) == "0"
    res = await _ws(client, {"id": 2, "type": f"{DOMAIN}/history/list"})
    h = res["result"]["history"][0]
    assert h["tag"] == "x" and h["reason"] == "dismissed"
    assert h["channels"] == ["wall"] and h["was_test"] is False and h["rule_id"]
