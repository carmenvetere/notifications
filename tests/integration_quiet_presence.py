"""Quiet-hours downgrade/suppress + presence routing, against a running HA."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.helpers_ha import alerts, count, rule_subentry, setup_nc

# Noon local — freeze so we can place a quiet-hours window around "now".
FROZEN = "2026-06-01 18:00:00"


def _clock(minutes: int) -> str:
    return (dt_util.now() + timedelta(minutes=minutes)).strftime("%H:%M:%S")


async def test_quiet_hours_downgrade_drops_priority(hass: HomeAssistant):
    with freeze_time(FROZEN):
        hass.states.async_set("input_boolean.q", "on")
        await setup_nc(
            hass,
            rule_subentry(
                name="Q", dedup_tag="q", source_type="state",
                entity_id="input_boolean.q", operator="==", value="on",
                priority="warning", channels=["wall"],
                quiet_hours_behavior="downgrade",
            ),
            # In quiet hours now (window spans the frozen time).
            options={"quiet_hours_start": _clock(-60), "quiet_hours_end": _clock(60)},
        )
        # Warning fired inside quiet hours -> downgraded one level to info.
        assert alerts(hass)[0]["priority"] == "info"


async def test_quiet_hours_suppress_skips_push_keeps_tray(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    with freeze_time(FROZEN):
        hass.states.async_set("input_boolean.s", "on")
        await setup_nc(
            hass,
            rule_subentry(
                name="S", dedup_tag="s", source_type="state",
                entity_id="input_boolean.s", operator="==", value="on",
                priority="warning", channels=["mobile", "wall"],
                quiet_hours_behavior="suppress",
            ),
            options={
                "mobile_targets": ["notify.mobile_app_test"],
                "quiet_hours_start": _clock(-60),
                "quiet_hours_end": _clock(60),
            },
        )
        assert count(hass) == "1"   # still shown (wall)
        assert len(calls) == 0      # but the push is suppressed


async def test_presence_away_only_routes_to_away_person(hass: HomeAssistant):
    phone = async_mock_service(hass, "notify", "mobile_app_phone")
    tablet = async_mock_service(hass, "notify", "mobile_app_tablet")
    hass.states.async_set("person.alex", "home")
    hass.states.async_set("person.sam", "not_home")
    hass.states.async_set("input_boolean.p", "on")
    await setup_nc(
        hass,
        rule_subentry(
            name="P", dedup_tag="p", source_type="state",
            entity_id="input_boolean.p", operator="==", value="on",
            priority="warning", channels=["mobile"], presence_routing="away_only",
        ),
        options={
            "persons": [
                {"person": "person.alex", "notify": "notify.mobile_app_phone"},
                {"person": "person.sam", "notify": "notify.mobile_app_tablet"},
            ]
        },
    )
    # away_only -> only the person who is away (sam / tablet) is notified.
    assert len(phone) == 0
    assert len(tablet) == 1
