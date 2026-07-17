"""Config + options flows for Notification Center.

Rules are created/edited in the custom **panel** (Settings → Notifications),
which manages subentries over the WebSocket API — the former ha-form rule
wizard has been retired. This module keeps only the single-instance parent
config flow and the global options flow.

The options flow is a small **menu** so a first-time user never has to guess a
service name or hand-write JSON:

- *Routing & timing* — mobile targets (picked from the notify services that
  actually exist on this HA), TTS, Fully Kiosk, quiet hours, digest, debounce.
- *Presence-mapped people* — an add/remove editor (person + notify + optional
  media player) instead of a raw object field.
- *Save & close* — persist and exit.

Edits accumulate in ``self._data`` and are only written when the user chooses
*Save & close*, so the flow is fully backward compatible with existing options.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DEBOUNCE_MS,
    CONF_DIGEST_TIME,
    CONF_FULLY_KIOSK_DEVICES,
    CONF_MOBILE_TARGETS,
    CONF_PERSONS,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_TTS_DEFAULT_TARGETS,
    CONF_TTS_SERVICE,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_DIGEST_TIME,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_TTS_SERVICE,
    DOMAIN,
    PARENT_TITLE,
)


def _notify_selector(hass: HomeAssistant, *, multiple: bool):
    """A dropdown of the notify services that exist (free entry still allowed).

    Falls back to a plain text field when no notify services are registered yet
    (a bare install), so the form still works. Picking from the list rather than
    typing ``notify.mobile_app_*`` by hand is the #1 fix for "notifications
    don't work".
    """
    services = sorted(
        f"notify.{name}" for name in hass.services.async_services().get("notify", {})
    )
    if services:
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=services,
                multiple=multiple,
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    return selector.TextSelector(selector.TextSelectorConfig(multiple=multiple))


def _build_settings_schema(hass: HomeAssistant) -> vol.Schema:
    """Routing / quiet-hours / digest / debounce (people are edited separately)."""
    return vol.Schema(
        {
            vol.Optional(CONF_MOBILE_TARGETS, default=list): _notify_selector(
                hass, multiple=True
            ),
            vol.Optional(
                CONF_TTS_SERVICE, default=DEFAULT_TTS_SERVICE
            ): selector.TextSelector(),
            vol.Optional(
                CONF_TTS_DEFAULT_TARGETS, default=list
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player", multiple=True)
            ),
            vol.Optional(
                CONF_FULLY_KIOSK_DEVICES, default=list
            ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
            vol.Optional(
                CONF_QUIET_HOURS_START, default=DEFAULT_QUIET_HOURS_START
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_QUIET_HOURS_END, default=DEFAULT_QUIET_HOURS_END
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_DIGEST_TIME, default=DEFAULT_DIGEST_TIME
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_DEBOUNCE_MS, default=DEFAULT_DEBOUNCE_MS
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=5000, step=50, unit_of_measurement="ms", mode="box"
                )
            ),
        }
    )


def _person_label(person: dict) -> str:
    """A stable, human-readable label for an existing person mapping."""
    who = person.get("person") or "?"
    via = person.get("notify") or "?"
    return f"{who} → {via}"


class NotificationCenterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance parent config flow."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=PARENT_TITLE, data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NotificationCenterOptionsFlow()


class NotificationCenterOptionsFlow(OptionsFlow):
    """Menu-driven routing / people / quiet-hours / digest / debounce options."""

    def __init__(self) -> None:
        # Working copy of the options; only persisted on "Save & close".
        self._data: dict[str, Any] | None = None

    def _options(self) -> dict[str, Any]:
        if self._data is None:
            self._data = dict(self.config_entry.options)
        return self._data

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        self._options()
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "persons", "finish"],
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._options().update(user_input)
            return await self.async_step_init()
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(
                _build_settings_schema(self.hass), self._options()
            ),
        )

    async def async_step_persons(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        people: list[dict] = list(self._options().get(CONF_PERSONS, []))
        if user_input is not None:
            remove = set(user_input.get("remove", []))
            people = [p for p in people if _person_label(p) not in remove]
            person = user_input.get("person")
            notify = user_input.get("notify")
            if person and notify:
                mapping = {"person": person, "notify": notify}
                media_player = user_input.get("media_player")
                if media_player:
                    mapping["media_player"] = media_player
                people.append(mapping)
            self._options()[CONF_PERSONS] = people
            return await self.async_step_init()

        fields: dict[Any, Any] = {
            vol.Optional("person"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person")
            ),
            vol.Optional("notify"): _notify_selector(self.hass, multiple=False),
            vol.Optional("media_player"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player")
            ),
        }
        if people:
            fields[vol.Optional("remove", default=list)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[_person_label(p) for p in people], multiple=True
                )
            )
        current = (
            "\n".join(f"• {_person_label(p)}" for p in people) if people else "None yet."
        )
        return self.async_show_form(
            step_id="persons",
            data_schema=vol.Schema(fields),
            description_placeholders={"current": current},
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        data = self._options()
        # Keep options tidy for a user who never sets up presence routing.
        if not data.get(CONF_PERSONS):
            data.pop(CONF_PERSONS, None)
        return self.async_create_entry(title="", data=data)
