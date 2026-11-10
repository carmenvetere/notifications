"""Config + options flows for Notification Center.

Rules and all global settings are edited in the custom **panel** (sidebar →
Notifications): rules on its Rules tab, people, phones, voice, speakers and
quiet hours on its Settings tab, over the WebSocket API. This module keeps the
single-instance parent config flow and a one-screen options flow that points
to the panel's Settings tab, so the gear icon on the integration still leads
somewhere useful.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, PARENT_TITLE

PANEL_SETTINGS_PATH = "/notification-center#settings"


class NotificationCenterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance parent config flow."""

    VERSION = 3

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
    """One screen that sends people to the panel's Settings tab.

    Submitting it changes nothing: the stored options are written back as-is.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders={"settings_url": PANEL_SETTINGS_PATH},
        )
