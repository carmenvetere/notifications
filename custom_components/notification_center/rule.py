"""Rule data model and evaluation for Notification Center.

This module is deliberately free of top-level Home Assistant imports so the
pure evaluation logic (``match_value``) can be unit-tested without a running
HA instance. The few helpers that need ``hass`` import it lazily.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import (
    CLEAR_DISMISS,
    CONF_ACTIONS_FOLLOW_PRIORITY,
    CONF_AUTO_CLEAR,
    CONF_CHANNELS,
    CONF_CLEAR_MODE,
    CONF_COLOR,
    CONF_CONDITION_TEMPLATE,
    CONF_COOLDOWN,
    CONF_CUSTOM_ACTIONS,
    CONF_DEDUP_TAG,
    CONF_DELIVER_AS_DIGEST,
    CONF_DIGEST_GROUP,
    CONF_ENABLED,
    CONF_ENTITY_ID,
    CONF_ESCALATION_AFTER,
    CONF_ICON,
    CONF_ITEMS_TEMPLATE,
    CONF_MESSAGE_TEMPLATE,
    CONF_NAME,
    CONF_NAVIGATION_TARGET,
    CONF_OPERATOR,
    CONF_PRESENCE_ROUTING,
    CONF_PRIORITY,
    CONF_QUIET_HOURS_BEHAVIOR,
    CONF_SNOOZE_ALLOWED,
    CONF_SOURCE_TYPE,
    CONF_TITLE_TEMPLATE,
    CONF_TTS_MESSAGE,
    CONF_TTS_TARGETS,
    CONF_VALUE,
    OP_EQ,
    OP_GE,
    OP_GT,
    OP_LE,
    OP_LT,
    OP_NE,
    PRIORITY_CLEAR_MODE,
    PRIORITY_COLORS,
    PRIORITY_COOLDOWN,
    PRIORITY_ICONS,
    PRIORITY_INFO,
    PRIORITY_SNOOZE_ALLOWED,
    PRESENCE_ALL,
    QH_DOWNGRADE,
    QH_IGNORE,
    SOURCE_NUMERIC,
    SOURCE_STATE,
    SOURCE_TEMPLATE,
)

# State values that mean "unavailable / unknown" and should never match.
_UNAVAILABLE = {"unavailable", "unknown", "none", "", None}


def match_value(source_type: str, operator: str | None, value: Any, state_value: Any) -> bool:
    """Pure comparison of a single state value against a rule's operator/value.

    Returns ``False`` for unavailable/unknown states. Safe to call without
    Home Assistant; used directly by unit tests.
    """
    if source_type == SOURCE_STATE:
        if isinstance(state_value, str) and state_value.lower() in _UNAVAILABLE:
            return False
        op = operator or OP_EQ
        target = "" if value is None else str(value)
        current = "" if state_value is None else str(state_value)
        if op == OP_EQ:
            return current == target
        if op == OP_NE:
            return current != target
        return False

    if source_type == SOURCE_NUMERIC:
        try:
            current = float(state_value)
            target = float(value)
        except (TypeError, ValueError):
            return False
        op = operator or OP_GT
        if op == OP_GT:
            return current > target
        if op == OP_LT:
            return current < target
        if op == OP_GE:
            return current >= target
        if op == OP_LE:
            return current <= target
        if op == OP_EQ:
            return current == target
        if op == OP_NE:
            return current != target
        return False

    return False


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(value)]


@dataclass
class Rule:
    """A single notification rule, hydrated from a config subentry."""

    rule_id: str
    name: str
    enabled: bool = True
    source_type: str = SOURCE_STATE
    entity_id: str | None = None
    operator: str | None = None
    value: Any = None
    condition_template: str | None = None
    priority: str = PRIORITY_INFO
    channels: list[str] = field(default_factory=list)
    icon: str | None = None
    color: str | None = None
    title_template: str | None = None
    message_template: str | None = None
    navigation_target: str | None = None
    dedup_tag: str | None = None
    cooldown: int | None = None
    auto_clear: bool = True
    quiet_hours_behavior: str = QH_DOWNGRADE
    presence_routing: str = PRESENCE_ALL
    escalation_after: int | None = None
    tts_targets: list[str] = field(default_factory=list)
    digest_group: str | None = None
    # Spoken-text + clearing model + digest delivery (UI redesign).
    tts_message: str | None = None
    actions_follow_priority: bool = True
    clear_mode_override: str | None = None
    snooze_allowed_override: bool | None = None
    deliver_as_digest: bool = False
    items_template: str | None = None
    custom_actions: list = field(default_factory=list)

    @classmethod
    def from_subentry(cls, subentry_id: str, data: dict[str, Any]) -> "Rule":
        """Build a Rule from a config subentry's data dict."""
        return cls(
            rule_id=subentry_id,
            name=data.get(CONF_NAME, subentry_id),
            enabled=data.get(CONF_ENABLED, True),
            source_type=data.get(CONF_SOURCE_TYPE, SOURCE_STATE),
            entity_id=data.get(CONF_ENTITY_ID) or None,
            operator=data.get(CONF_OPERATOR) or None,
            value=data.get(CONF_VALUE),
            condition_template=data.get(CONF_CONDITION_TEMPLATE) or None,
            priority=data.get(CONF_PRIORITY, PRIORITY_INFO),
            channels=_as_list(data.get(CONF_CHANNELS)),
            icon=data.get(CONF_ICON) or None,
            color=data.get(CONF_COLOR) or None,
            title_template=data.get(CONF_TITLE_TEMPLATE) or None,
            message_template=data.get(CONF_MESSAGE_TEMPLATE) or None,
            navigation_target=data.get(CONF_NAVIGATION_TARGET) or None,
            dedup_tag=data.get(CONF_DEDUP_TAG) or None,
            cooldown=data.get(CONF_COOLDOWN),
            auto_clear=data.get(CONF_AUTO_CLEAR, True),
            quiet_hours_behavior=data.get(CONF_QUIET_HOURS_BEHAVIOR, QH_DOWNGRADE),
            presence_routing=data.get(CONF_PRESENCE_ROUTING, PRESENCE_ALL),
            escalation_after=data.get(CONF_ESCALATION_AFTER),
            tts_targets=_as_list(data.get(CONF_TTS_TARGETS)),
            digest_group=data.get(CONF_DIGEST_GROUP) or None,
            tts_message=data.get(CONF_TTS_MESSAGE) or None,
            actions_follow_priority=data.get(CONF_ACTIONS_FOLLOW_PRIORITY, True),
            clear_mode_override=data.get(CONF_CLEAR_MODE) or None,
            snooze_allowed_override=data.get(CONF_SNOOZE_ALLOWED),
            deliver_as_digest=data.get(CONF_DELIVER_AS_DIGEST, False),
            items_template=data.get(CONF_ITEMS_TEMPLATE) or None,
            custom_actions=data.get(CONF_CUSTOM_ACTIONS) or [],
        )

    @property
    def tag(self) -> str:
        """Stable dedup key. Falls back to the rule id."""
        return self.dedup_tag or self.rule_id

    @property
    def effective_icon(self) -> str:
        return self.icon or PRIORITY_ICONS.get(self.priority, "mdi:bell")

    @property
    def effective_color(self) -> str:
        return self.color or PRIORITY_COLORS.get(self.priority, "#7295B2")

    # --- Clearing model -----------------------------------------------------
    @property
    def effective_clear_mode(self) -> str:
        """How this alert may be cleared: locked or dismiss."""
        if self.actions_follow_priority:
            return PRIORITY_CLEAR_MODE.get(self.priority, CLEAR_DISMISS)
        return self.clear_mode_override or CLEAR_DISMISS

    @property
    def snooze_allowed(self) -> bool:
        if self.actions_follow_priority:
            return PRIORITY_SNOOZE_ALLOWED.get(self.priority, False)
        return bool(self.snooze_allowed_override)

    @property
    def allowed_actions(self) -> list[str]:
        """Action buttons a surface should render for this alert.

        Locked (critical/warning) -> none. Dismiss (info) -> dismiss, plus
        snooze when allowed.
        """
        actions: list[str] = []
        if self.effective_clear_mode == CLEAR_DISMISS:
            actions.append("dismiss")
        if self.snooze_allowed:
            actions.append("snooze")
        return actions

    @property
    def custom_action_buttons(self) -> list[dict]:
        """Public button descriptors for the surfaces (no service details)."""
        buttons = []
        for i, action in enumerate(self.custom_actions):
            if not isinstance(action, dict):
                continue
            buttons.append(
                {
                    "id": i,
                    "label": action.get("label") or "Run",
                    "icon": action.get("icon"),
                    "confirm": action.get("confirm"),
                }
            )
        return buttons

    @property
    def effective_tts_message(self) -> str | None:
        """Spoken text, falling back to the message template."""
        return self.tts_message or self.message_template

    @property
    def effective_cooldown(self) -> int:
        """Cooldown in minutes; explicit override else the per-priority default."""
        if self.cooldown not in (None, ""):
            try:
                return int(self.cooldown)
            except (TypeError, ValueError):
                pass
        return PRIORITY_COOLDOWN.get(self.priority, 0)

    # --- Entities this rule depends on (for listener registration) ----------
    @property
    def tracked_entities(self) -> list[str]:
        if self.source_type == SOURCE_TEMPLATE:
            return []
        return [self.entity_id] if self.entity_id else []

    @property
    def is_template(self) -> bool:
        return self.source_type == SOURCE_TEMPLATE

    @property
    def primary_template(self) -> str | None:
        """For template-source rules, the template that defines active state."""
        if self.source_type == SOURCE_TEMPLATE:
            return self.condition_template
        return None

    # --- Evaluation (needs hass) --------------------------------------------
    def is_active(self, hass) -> bool:
        """Return whether this rule is currently in an active (alerting) state."""
        if not self.enabled:
            return False

        if self.source_type == SOURCE_TEMPLATE:
            if not self.condition_template:
                return False
            return _render_bool(hass, self.condition_template)

        if not self.entity_id:
            return False

        state = hass.states.get(self.entity_id)
        if state is None:
            return False

        if not match_value(self.source_type, self.operator, self.value, state.state):
            return False

        # An optional condition_template acts as an extra gate for
        # state/numeric rules (e.g. "only when home is occupied").
        if self.condition_template:
            return _render_bool(hass, self.condition_template)

        return True


def _render_bool(hass, template_str: str) -> bool:
    """Render a Jinja template and coerce to bool. Lazy-imports HA helpers."""
    from homeassistant.exceptions import TemplateError
    from homeassistant.helpers.template import Template

    try:
        tpl = Template(template_str, hass)
        result = tpl.async_render(parse_result=True)
    except TemplateError:
        return False
    if isinstance(result, bool):
        return result
    if isinstance(result, (int, float)):
        return result != 0
    if isinstance(result, str):
        return result.strip().lower() in ("true", "on", "yes", "1")
    return bool(result)


def render_items(hass, template_str: str | None) -> list:
    """Render a template that returns the digest's individual items.

    Expected to render a list of dicts (name/detail/icon/color). Returns an
    empty list on error or when no template is set.
    """
    if not template_str:
        return []
    from homeassistant.exceptions import TemplateError
    from homeassistant.helpers.template import Template

    try:
        result = Template(template_str, hass).async_render(parse_result=True)
    except TemplateError:
        return []
    if isinstance(result, list):
        return result
    return []


def render_text(hass, template_str: str | None, default: str = "") -> str:
    """Render a (possibly None) text template to a string."""
    if not template_str:
        return default
    from homeassistant.exceptions import TemplateError
    from homeassistant.helpers.template import Template

    try:
        tpl = Template(template_str, hass)
        return str(tpl.async_render(parse_result=False))
    except TemplateError:
        return template_str
