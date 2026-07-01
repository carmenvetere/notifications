"""Config + options flows for Notification Center.

Rules are created/edited in the custom **panel** (Settings → Notifications),
which manages subentries over the WebSocket API — the former ha-form rule
wizard has been retired. This module keeps only the single-instance parent
config flow and the global options flow.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
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


def _build_options_schema() -> vol.Schema:
    """Schema for parent-level routing / quiet-hours / digest / debounce."""
    return vol.Schema(
        {
            vol.Optional(CONF_MOBILE_TARGETS, default=list): selector.TextSelector(
                selector.TextSelectorConfig(multiple=True)
            ),
            vol.Optional(CONF_PERSONS, default=list): selector.ObjectSelector(),
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
    """Global routing / quiet-hours / digest / debounce options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _build_options_schema(), self.config_entry.options
            ),
        )
