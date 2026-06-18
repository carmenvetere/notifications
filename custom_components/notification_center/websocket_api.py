"""WebSocket API for the custom setup panel.

The stock subentry config flow only renders ha-form, which can't express the
designed editor (preset cards, channel chips, live preview). These commands let
the custom panel manage rule subentries directly with our own data model.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import slugify

from .const import (
    CHANNELS,
    CLEAR_MODES,
    DOMAIN,
    NUMERIC_OPERATORS,
    PRESENCE_ROUTING,
    PRIORITIES,
    PRIORITY_CLEAR_MODE,
    PRIORITY_COLORS,
    PRIORITY_COOLDOWN,
    PRIORITY_ICONS,
    PRIORITY_INTERRUPTION_LEVEL,
    PRIORITY_SNOOZE_ALLOWED,
    QUIET_HOURS_BEHAVIORS,
    SOURCE_TYPES,
    STATE_OPERATORS,
    SUBENTRY_TYPE_RULE,
)
from .rule import Rule

_LOGGER = logging.getLogger(__name__)

# Fields that must be ints (or absent), but arrive from the panel as strings.
_NUMERIC_FIELDS = ("cooldown", "escalation_after")


def _sanitize(rule: dict[str, Any]) -> dict[str, Any]:
    """Coerce panel input into storable types.

    Number inputs arrive as strings ("" when empty); drop empties and cast the
    rest to int so they don't later break (e.g. ``"5" * 60``).
    """
    out = dict(rule)
    for key in _NUMERIC_FIELDS:
        val = out.get(key)
        if val in (None, ""):
            out.pop(key, None)
            continue
        try:
            out[key] = int(val)
        except (TypeError, ValueError):
            out.pop(key, None)
    return out


def _update_subentry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    subentry: ConfigSubentry,
    rule: dict[str, Any],
) -> None:
    """Update a rule subentry, tolerant of HA version differences.

    Prefer ``async_update_subentry``; fall back to remove + re-add (preserving
    ids) on older cores that lack it or use a different signature.
    """
    centries = hass.config_entries
    title = rule.get("name") or subentry.title
    try:
        centries.async_update_subentry(entry, subentry, data=rule, title=title)
        return
    except (AttributeError, TypeError):
        _LOGGER.debug("async_update_subentry unavailable; using remove+add")
    centries.async_remove_subentry(entry, subentry.subentry_id)
    centries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=rule,
            subentry_type=SUBENTRY_TYPE_RULE,
            title=title,
            unique_id=subentry.unique_id,
            subentry_id=subentry.subentry_id,
        ),
    )


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register all notification_center WebSocket commands (idempotent)."""
    for handler in (
        ws_meta,
        ws_list_rules,
        ws_create_rule,
        ws_update_rule,
        ws_delete_rule,
    ):
        websocket_api.async_register_command(hass, handler)


def _entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def _rule_view(subentry_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Serialize a rule plus its derived/effective fields for the editor."""
    rule = Rule.from_subentry(subentry_id, data)
    return {
        "subentry_id": subentry_id,
        "data": dict(data),
        "effective": {
            "clear_mode": rule.effective_clear_mode,
            "snooze_allowed": rule.snooze_allowed,
            "actions": rule.allowed_actions,
            "color": rule.effective_color,
            "icon": rule.effective_icon,
            "cooldown": rule.effective_cooldown,
        },
    }


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/meta"})
@callback
def ws_meta(hass, connection, msg) -> None:
    """Option lists + per-priority defaults, so the panel stays in sync."""
    connection.send_result(
        msg["id"],
        {
            "priorities": PRIORITIES,
            "channels": CHANNELS,
            "source_types": SOURCE_TYPES,
            "operators": {"state": STATE_OPERATORS, "numeric": NUMERIC_OPERATORS},
            "quiet_hours_behaviors": QUIET_HOURS_BEHAVIORS,
            "presence_routing": PRESENCE_ROUTING,
            "clear_modes": CLEAR_MODES,
            "priority_defaults": {
                p: {
                    "color": PRIORITY_COLORS.get(p),
                    "icon": PRIORITY_ICONS.get(p),
                    "cooldown": PRIORITY_COOLDOWN.get(p),
                    "push": PRIORITY_INTERRUPTION_LEVEL.get(p),
                    "clear_mode": PRIORITY_CLEAR_MODE.get(p),
                    "snooze": PRIORITY_SNOOZE_ALLOWED.get(p),
                }
                for p in PRIORITIES
            },
        },
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/rules/list"})
@callback
def ws_list_rules(hass, connection, msg) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    rules = [
        _rule_view(sid, dict(sub.data))
        for sid, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_TYPE_RULE
    ]
    connection.send_result(msg["id"], {"rules": rules})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/rules/create",
        vol.Required("rule"): dict,
    }
)
@callback
def ws_create_rule(hass, connection, msg) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    rule = _sanitize(msg["rule"])
    name = rule.get("name") or "Rule"
    tag = rule.get("dedup_tag") or slugify(name)
    existing = {
        s.unique_id
        for s in entry.subentries.values()
        if s.subentry_type == SUBENTRY_TYPE_RULE
    }
    if tag in existing:
        connection.send_error(msg["id"], "duplicate", f"A rule with tag '{tag}' exists")
        return
    try:
        subentry = ConfigSubentry(
            data=rule,
            subentry_type=SUBENTRY_TYPE_RULE,
            title=name,
            unique_id=tag,
        )
        hass.config_entries.async_add_subentry(entry, subentry)
    except Exception as err:  # noqa: BLE001 - surface a real message, not "unknown error"
        _LOGGER.exception("notification_center: failed to create rule")
        connection.send_error(msg["id"], "create_failed", str(err))
        return
    connection.send_result(msg["id"], {"subentry_id": subentry.subentry_id})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/rules/update",
        vol.Required("subentry_id"): str,
        vol.Required("rule"): dict,
    }
)
@callback
def ws_update_rule(hass, connection, msg) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    subentry = entry.subentries.get(msg["subentry_id"])
    if subentry is None or subentry.subentry_type != SUBENTRY_TYPE_RULE:
        connection.send_error(msg["id"], "not_found", "Rule not found")
        return
    rule = _sanitize(msg["rule"])
    try:
        _update_subentry(hass, entry, subentry, rule)
    except Exception as err:  # noqa: BLE001 - surface a real message, not "unknown error"
        _LOGGER.exception("notification_center: failed to update rule")
        connection.send_error(msg["id"], "update_failed", str(err))
        return
    connection.send_result(msg["id"], {"subentry_id": subentry.subentry_id})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/rules/delete",
        vol.Required("subentry_id"): str,
    }
)
@callback
def ws_delete_rule(hass, connection, msg) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    if msg["subentry_id"] not in entry.subentries:
        connection.send_error(msg["id"], "not_found", "Rule not found")
        return
    try:
        hass.config_entries.async_remove_subentry(entry, msg["subentry_id"])
    except Exception as err:  # noqa: BLE001 - surface a real message
        _LOGGER.exception("notification_center: failed to delete rule")
        connection.send_error(msg["id"], "delete_failed", str(err))
        return
    connection.send_result(msg["id"], {"success": True})
