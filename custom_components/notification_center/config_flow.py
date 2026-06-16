"""Config, options and per-rule subentry flows for Notification Center."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CHANNELS,
    CONF_AUTO_CLEAR,
    CONF_CHANNELS,
    CONF_COLOR,
    CONF_CONDITION_TEMPLATE,
    CONF_COOLDOWN,
    CONF_DEBOUNCE_MS,
    CONF_DEDUP_TAG,
    CONF_DIGEST_GROUP,
    CONF_ENABLED,
    CONF_ENTITY_ID,
    CONF_ESCALATION_AFTER,
    CONF_FULLY_KIOSK_DEVICES,
    CONF_ICON,
    CONF_MESSAGE_TEMPLATE,
    CONF_MOBILE_TARGETS,
    CONF_NAME,
    CONF_NAVIGATION_TARGET,
    CONF_OPERATOR,
    CONF_PERSONS,
    CONF_PRESENCE_ROUTING,
    CONF_PRIORITY,
    CONF_QUIET_HOURS_BEHAVIOR,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_SOURCE_TYPE,
    CONF_TITLE_TEMPLATE,
    CONF_TTS_DEFAULT_TARGETS,
    CONF_TTS_SERVICE,
    CONF_TTS_TARGETS,
    CONF_VALUE,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_TTS_SERVICE,
    DOMAIN,
    NUMERIC_OPERATORS,
    PARENT_TITLE,
    PRIORITIES,
    PRIORITY_INFO,
    PRESENCE_ALL,
    PRESENCE_ROUTING,
    QH_DOWNGRADE,
    QUIET_HOURS_BEHAVIORS,
    SOURCE_STATE,
    SOURCE_TYPES,
    SUBENTRY_TYPE_RULE,
)


def _select(options: list[str], **kwargs) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            **kwargs,
        )
    )


def _build_rule_schema() -> vol.Schema:
    """Schema for creating/editing a single rule subentry."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_ENABLED, default=True): selector.BooleanSelector(),
            vol.Required(CONF_SOURCE_TYPE, default=SOURCE_STATE): _select(SOURCE_TYPES),
            vol.Optional(CONF_ENTITY_ID): selector.EntitySelector(),
            vol.Optional(CONF_OPERATOR): _select(NUMERIC_OPERATORS),
            vol.Optional(CONF_VALUE): selector.TextSelector(),
            vol.Optional(CONF_CONDITION_TEMPLATE): selector.TemplateSelector(),
            vol.Required(CONF_PRIORITY, default=PRIORITY_INFO): _select(PRIORITIES),
            vol.Optional(CONF_CHANNELS, default=list): _select(CHANNELS, multiple=True),
            vol.Optional(CONF_ICON): selector.IconSelector(),
            vol.Optional(CONF_COLOR): selector.TextSelector(),
            vol.Optional(CONF_TITLE_TEMPLATE): selector.TemplateSelector(),
            vol.Optional(CONF_MESSAGE_TEMPLATE): selector.TemplateSelector(),
            vol.Optional(CONF_NAVIGATION_TARGET): selector.TextSelector(),
            vol.Optional(CONF_DEDUP_TAG): selector.TextSelector(),
            vol.Optional(CONF_COOLDOWN): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, step=1, unit_of_measurement="min", mode="box"
                )
            ),
            vol.Optional(CONF_AUTO_CLEAR, default=True): selector.BooleanSelector(),
            vol.Required(
                CONF_QUIET_HOURS_BEHAVIOR, default=QH_DOWNGRADE
            ): _select(QUIET_HOURS_BEHAVIORS),
            vol.Required(
                CONF_PRESENCE_ROUTING, default=PRESENCE_ALL
            ): _select(PRESENCE_ROUTING),
            vol.Optional(CONF_ESCALATION_AFTER): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, step=1, unit_of_measurement="min", mode="box"
                )
            ),
            vol.Optional(CONF_TTS_TARGETS, default=list): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player", multiple=True)
            ),
            vol.Optional(CONF_DIGEST_GROUP): selector.TextSelector(),
        }
    )


def _build_options_schema() -> vol.Schema:
    """Schema for parent-level routing / global options."""
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

    VERSION = 1

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

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_TYPE_RULE: RuleSubentryFlow}


class NotificationCenterOptionsFlow(OptionsFlow):
    """Global routing / quiet-hours / debounce options."""

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


class RuleSubentryFlow(ConfigSubentryFlow):
    """Add / reconfigure a single notification rule."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=user_input
            )
        return self.async_show_form(step_id="user", data_schema=_build_rule_schema())

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=user_input[CONF_NAME],
                data=user_input,
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _build_rule_schema(), subentry.data
            ),
        )
