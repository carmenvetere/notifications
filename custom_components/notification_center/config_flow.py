"""Config, options and per-rule subentry flows for Notification Center.

The rule subentry flow is a multi-step wizard (Trigger -> Priority -> Channels
-> Message -> Advanced) with conditional sub-steps, replacing the former
single 22-field form. Home Assistant config/subentry flows are rendered by HA
core with ``ha-form`` selectors, so branching is done with separate steps
rather than reactive show/hide.

NOTE: This wizard is intended to be *temporary*. The design direction is to
replace it with a custom setup panel (Lit) that can render the preset cards /
channel chips / live preview the stock ``ha-form`` cannot. Keep it as the
working editor until that panel lands and is proven.
"""

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
    CHANNEL_NAVIGATE,
    CHANNEL_TTS,
    CHANNELS,
    CLEAR_MODES,
    CONF_ACTIONS_FOLLOW_PRIORITY,
    CONF_AUTO_CLEAR,
    CONF_CHANNELS,
    CONF_CLEAR_MODE,
    CONF_COLOR,
    CONF_CONDITION_TEMPLATE,
    CONF_COOLDOWN,
    CONF_CUSTOM_ACTIONS,
    CONF_DEBOUNCE_MS,
    CONF_DEDUP_TAG,
    CONF_DELIVER_AS_DIGEST,
    CONF_DIGEST_GROUP,
    CONF_ENABLED,
    CONF_ENTITY_ID,
    CONF_ESCALATION_AFTER,
    CONF_FULLY_KIOSK_DEVICES,
    CONF_ICON,
    CONF_ITEMS_TEMPLATE,
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
    CONF_SNOOZE_ALLOWED,
    CONF_SOURCE_TYPE,
    CONF_TITLE_TEMPLATE,
    CONF_TTS_DEFAULT_TARGETS,
    CONF_TTS_MESSAGE,
    CONF_TTS_SERVICE,
    CONF_TTS_TARGETS,
    CONF_VALUE,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_TTS_SERVICE,
    DOMAIN,
    OP_EQ,
    OP_GE,
    OP_GT,
    OP_LE,
    OP_LT,
    OP_NE,
    PARENT_TITLE,
    PRIORITIES,
    PRIORITY_INFO,
    PRESENCE_ALL,
    PRESENCE_ROUTING,
    QH_DOWNGRADE,
    QUIET_HOURS_BEHAVIORS,
    SOURCE_NUMERIC,
    SOURCE_STATE,
    SOURCE_TEMPLATE,
    SOURCE_TYPES,
    SUBENTRY_TYPE_RULE,
)

# Operator option labels (value -> human label) shown in the dropdowns.
_STATE_OPERATOR_LABELS = {OP_EQ: "is", OP_NE: "is not"}
_NUMERIC_OPERATOR_LABELS = {
    OP_GT: "> greater than",
    OP_LT: "< less than",
    OP_GE: "≥ at or above",
    OP_LE: "≤ at or below",
    OP_EQ: "= equals",
    OP_NE: "≠ not equal",
}


def _select(options: list[str], **kwargs) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            **kwargs,
        )
    )


def _labelled_select(labels: dict[str, str]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=value, label=label)
                for value, label in labels.items()
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


# --- Per-step rule schemas --------------------------------------------------
def _schema_trigger() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_ENABLED, default=True): selector.BooleanSelector(),
            vol.Required(CONF_SOURCE_TYPE, default=SOURCE_STATE): _select(SOURCE_TYPES),
        }
    )


def _schema_trigger_match(source_type: str) -> vol.Schema:
    if source_type == SOURCE_NUMERIC:
        operator = vol.Required(CONF_OPERATOR, default=OP_GT)
        operator_sel = _labelled_select(_NUMERIC_OPERATOR_LABELS)
    else:
        operator = vol.Required(CONF_OPERATOR, default=OP_EQ)
        operator_sel = _labelled_select(_STATE_OPERATOR_LABELS)
    return vol.Schema(
        {
            vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
            operator: operator_sel,
            vol.Required(CONF_VALUE): selector.TextSelector(),
        }
    )


def _schema_trigger_template() -> vol.Schema:
    return vol.Schema(
        {vol.Required(CONF_CONDITION_TEMPLATE): selector.TemplateSelector()}
    )


def _schema_priority() -> vol.Schema:
    return vol.Schema(
        {vol.Required(CONF_PRIORITY, default=PRIORITY_INFO): _select(PRIORITIES)}
    )


def _schema_channels() -> vol.Schema:
    return vol.Schema(
        {vol.Optional(CONF_CHANNELS, default=list): _select(CHANNELS, multiple=True)}
    )


def _schema_tts() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_TTS_MESSAGE): selector.TemplateSelector(),
            vol.Optional(CONF_TTS_TARGETS, default=list): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player", multiple=True)
            ),
        }
    )


def _schema_navigate() -> vol.Schema:
    return vol.Schema({vol.Optional(CONF_NAVIGATION_TARGET): selector.TextSelector()})


def _schema_message() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_TITLE_TEMPLATE): selector.TemplateSelector(),
            vol.Optional(CONF_MESSAGE_TEMPLATE): selector.TemplateSelector(),
            vol.Optional(CONF_ICON): selector.IconSelector(),
            vol.Optional(CONF_COLOR): selector.TextSelector(),
        }
    )


def _schema_advanced(priority: str) -> vol.Schema:
    schema: dict = {
        vol.Required(
            CONF_ACTIONS_FOLLOW_PRIORITY, default=True
        ): selector.BooleanSelector(),
        vol.Optional(CONF_AUTO_CLEAR, default=True): selector.BooleanSelector(),
    }
    # "Deliver as a digest" is an Info-only delivery option.
    if priority == PRIORITY_INFO:
        schema[vol.Optional(CONF_DELIVER_AS_DIGEST, default=False)] = (
            selector.BooleanSelector()
        )
        schema[vol.Optional(CONF_DIGEST_GROUP)] = selector.TextSelector()
        schema[vol.Optional(CONF_ITEMS_TEMPLATE)] = selector.TemplateSelector()
    schema[vol.Required(CONF_QUIET_HOURS_BEHAVIOR, default=QH_DOWNGRADE)] = _select(
        QUIET_HOURS_BEHAVIORS
    )
    schema[vol.Required(CONF_PRESENCE_ROUTING, default=PRESENCE_ALL)] = _select(
        PRESENCE_ROUTING
    )
    schema[vol.Optional(CONF_COOLDOWN)] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, step=1, unit_of_measurement="min", mode="box"
        )
    )
    schema[vol.Optional(CONF_ESCALATION_AFTER)] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, step=1, unit_of_measurement="min", mode="box"
        )
    )
    schema[vol.Optional(CONF_DEDUP_TAG)] = selector.TextSelector()
    # Custom actions are edited richly in the panel; the flow offers a raw list.
    schema[vol.Optional(CONF_CUSTOM_ACTIONS)] = selector.ObjectSelector()
    return vol.Schema(schema)


def _schema_actions() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CLEAR_MODE): _select(CLEAR_MODES),
            vol.Optional(CONF_SNOOZE_ALLOWED, default=False): selector.BooleanSelector(),
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
    """Add / reconfigure a single notification rule, as a 5-step wizard.

    Accumulated input is carried in ``self._rule_data`` across steps until the
    final step creates or updates the subentry. The reconfigure path runs the
    same steps pre-filled from the existing subentry data.
    """

    _rule_data: dict[str, Any]
    _reconfigure = False

    # --- Entry points -------------------------------------------------------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._rule_data = {}
        self._reconfigure = False
        return await self.async_step_trigger()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._rule_data = dict(self._get_reconfigure_subentry().data)
        self._reconfigure = True
        return await self.async_step_trigger()

    # --- Step 1: Trigger ----------------------------------------------------
    async def async_step_trigger(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            if self._rule_data.get(CONF_SOURCE_TYPE) == SOURCE_TEMPLATE:
                return await self.async_step_trigger_template()
            return await self.async_step_trigger_match()
        return self._show("trigger", _schema_trigger())

    async def async_step_trigger_match(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            return await self.async_step_priority()
        source_type = self._rule_data.get(CONF_SOURCE_TYPE, SOURCE_STATE)
        return self._show("trigger_match", _schema_trigger_match(source_type))

    async def async_step_trigger_template(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            return await self.async_step_priority()
        return self._show("trigger_template", _schema_trigger_template())

    # --- Step 2: Priority ---------------------------------------------------
    async def async_step_priority(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            return await self.async_step_channels()
        return self._show("priority", _schema_priority())

    # --- Step 3: Channels (+ conditional tts / navigate) --------------------
    async def async_step_channels(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            return await self._route_after_channels()
        return self._show("channels", _schema_channels())

    async def _route_after_channels(self) -> SubentryFlowResult:
        channels = self._rule_data.get(CONF_CHANNELS, [])
        if CHANNEL_TTS in channels:
            return await self.async_step_tts()
        if CHANNEL_NAVIGATE in channels:
            return await self.async_step_navigate()
        return await self.async_step_message()

    async def async_step_tts(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            if CHANNEL_NAVIGATE in self._rule_data.get(CONF_CHANNELS, []):
                return await self.async_step_navigate()
            return await self.async_step_message()
        return self._show("tts", _schema_tts())

    async def async_step_navigate(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            return await self.async_step_message()
        return self._show("navigate", _schema_navigate())

    # --- Step 4: Message ----------------------------------------------------
    async def async_step_message(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            return await self.async_step_advanced()
        return self._show("message", _schema_message())

    # --- Step 5: Advanced (+ conditional actions) ---------------------------
    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            if not user_input.get(CONF_ACTIONS_FOLLOW_PRIORITY, True):
                return await self.async_step_actions()
            # Following priority: clear any stale manual overrides.
            self._rule_data.pop(CONF_CLEAR_MODE, None)
            self._rule_data.pop(CONF_SNOOZE_ALLOWED, None)
            return self._finish()
        priority = self._rule_data.get(CONF_PRIORITY, PRIORITY_INFO)
        return self._show("advanced", _schema_advanced(priority))

    async def async_step_actions(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._rule_data.update(user_input)
            return self._finish()
        return self._show("actions", _schema_actions())

    # --- Helpers ------------------------------------------------------------
    def _show(self, step_id: str, schema: vol.Schema) -> SubentryFlowResult:
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, self._rule_data),
        )

    def _finish(self) -> SubentryFlowResult:
        title = self._rule_data.get(CONF_NAME) or "Rule"
        if self._reconfigure:
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=title,
                data=self._rule_data,
            )
        return self.async_create_entry(title=title, data=self._rule_data)
