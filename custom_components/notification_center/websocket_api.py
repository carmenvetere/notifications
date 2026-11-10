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
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template
from homeassistant.util import slugify

from .const import (
    CHANNELS,
    CLEAR_MODES,
    DEFAULT_SNOOZE_OPTIONS,
    PRIORITY_QUIET_HOURS_DEFAULT,
    TAKEOVER_MAX_CHARS,
    DATA_YAML_RULES,
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
    SOURCE_NUMERIC,
    SOURCE_STATE,
    SOURCE_TEMPLATE,
    SOURCE_TYPES,
    STATE_OPERATORS,
    SUBENTRY_TYPE_RULE,
)
from . import settings as nc_settings
from .rule import Rule
from .yaml_rules import (
    async_save_yaml_rules,
    rule_id_for,
    rules_file_rel,
    yaml_source,
)

_LOGGER = logging.getLogger(__name__)

# Fields that must be ints (or absent), but arrive from the panel as strings.
_NUMERIC_FIELDS = ("cooldown", "escalation_after", "activity_timeout")

# Server-side rule validation. The panel is the sole rule editor, so this is
# the last line of defense before a bad rule reaches storage / the engine. It
# is deliberately permissive about *extra* keys (icons, templates, custom
# actions, digest fields evolve over time) but strict about the constrained
# enums and the trigger fields the engine relies on. Runs after _sanitize, so
# cooldown/escalation_after are already ints or absent.
RULE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): vol.All(str, vol.Length(min=1)),
        vol.Optional("enabled"): vol.Coerce(bool),
        vol.Optional("source_type"): vol.In(SOURCE_TYPES),
        vol.Optional("entity_id"): str,
        # "==" / "!=" (state) are a subset of the numeric operators.
        vol.Optional("operator"): vol.In(NUMERIC_OPERATORS),
        vol.Optional("value"): vol.Any(str, int, float, bool),
        vol.Optional("condition_template"): str,
        vol.Optional("priority"): vol.In(PRIORITIES),
        vol.Optional("channels"): [vol.In(CHANNELS)],
        vol.Optional("quiet_hours_behavior"): vol.In(QUIET_HOURS_BEHAVIORS),
        vol.Optional("presence_routing"): vol.In(PRESENCE_ROUTING),
        vol.Optional("clear_mode"): vol.In(CLEAR_MODES),
        vol.Optional("cooldown"): vol.Any(int, None),
        vol.Optional("escalation_after"): vol.Any(int, None),
        vol.Optional("recipients"): [str],
        vol.Optional("wall_action"): str,
        vol.Optional("wall_service"): str,
        vol.Optional("wall_takeover"): vol.Coerce(bool),
        vol.Optional("wall_takeover_text"): vol.Any(str, None),
        vol.Optional("wall_takeover_target"): vol.Any(str, None),
        vol.Optional("snooze_options"): [vol.All(vol.Coerce(int), vol.Range(min=1))],
    },
    extra=vol.ALLOW_EXTRA,
)


def _validate_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Validate a sanitized rule dict; raise vol.Invalid with a clear message.

    Beyond the field-level schema, enforce the trigger contract: state/numeric
    rules need an entity + operator, template rules need a condition template.
    """
    validated = RULE_SCHEMA(rule)
    source_type = validated.get("source_type")
    if source_type in (SOURCE_STATE, SOURCE_NUMERIC):
        if not validated.get("entity_id"):
            raise vol.Invalid("entity_id is required for state/numeric rules")
        if not validated.get("operator"):
            raise vol.Invalid("operator is required for state/numeric rules")
    elif source_type == SOURCE_TEMPLATE and not validated.get("condition_template"):
        raise vol.Invalid("condition_template is required for template rules")
    return validated


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
    # Drop channels this version no longer has (e.g. the old Fully Kiosk
    # "navigate") instead of failing the whole rule.
    chans = out.get("channels")
    if isinstance(chans, str):
        chans = [c.strip() for c in chans.split(",") if c.strip()]
    if isinstance(chans, list):
        kept = [c for c in chans if c in CHANNELS]
        if len(kept) != len(chans):
            _LOGGER.info(
                "notification_center: dropping unsupported channel(s) %s from rule %r",
                sorted(set(chans) - set(kept)),
                out.get("name"),
            )
        out["channels"] = kept
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
        ws_test_rule,
        ws_render,
        ws_history,
        ws_settings_get,
        ws_settings_update,
        ws_settings_test_push,
        ws_settings_test_announcement,
    ):
        websocket_api.async_register_command(hass, handler)


def _entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def _yaml_mode(hass: HomeAssistant) -> bool:
    """True when rules come from YAML (#47): inline `rules:` or `rules_file:`."""
    return yaml_source(hass) is not None


def _file_mode(hass: HomeAssistant) -> bool:
    """True when rules live in `rules_file:` — the panel edits that file."""
    return yaml_source(hass) == "file"


def _read_only(hass: HomeAssistant) -> bool:
    """Inline `rules:` is part of configuration.yaml, which we never rewrite."""
    return yaml_source(hass) == "inline"


def _reject_if_read_only(hass: HomeAssistant, connection, msg) -> bool:
    """Reject a mutation in read-only (inline YAML) mode; True when rejected."""
    if _read_only(hass):
        connection.send_error(
            msg["id"],
            "read_only",
            "Rules are defined inline in configuration.yaml (notification_center: "
            "rules) — edit the file and call notification_center.reload, or switch "
            "to `rules_file:` to edit them here as well.",
        )
        return True
    return False


def _engines(hass: HomeAssistant) -> list:
    return list(hass.data.get(DOMAIN, {}).values())


def _settings(hass: HomeAssistant) -> dict[str, Any]:
    entry = _entry(hass)
    return nc_settings.normalize(dict(entry.options) if entry else {})


def _person_name(hass: HomeAssistant, person: str) -> str:
    state = hass.states.get(person) if person else None
    return (state.attributes.get("friendly_name") if state else None) or (
        person.split(".", 1)[-1].replace("_", " ").title() if person else ""
    )


def _persons(hass: HomeAssistant) -> list[dict[str, Any]]:
    """People from Settings (for the per-rule recipients picker)."""
    out = []
    for p in _settings(hass)[nc_settings.CONF_PEOPLE]:
        out.append(
            {
                "person": p["person"],
                "name": _person_name(hass, p["person"]),
                "phones": list(p["phones"]),
                # Back-compat with older panels: the first phone.
                "notify": p["phones"][0] if p["phones"] else "",
            }
        )
    return out


def _alert_for(hass: HomeAssistant, tag: str) -> dict[str, Any] | None:
    for engine in _engines(hass):
        alert = engine.active.get(tag)
        if alert is not None:
            return alert
    return None


def _with_status(hass: HomeAssistant, view: dict[str, Any]) -> dict[str, Any]:
    """Add live status (active / active_since / testing) to a rule view."""
    tag = view["data"].get("dedup_tag") or Rule.from_subentry(view["subentry_id"], view["data"]).tag
    alert = _alert_for(hass, tag)
    view["active"] = alert is not None and not alert.get("test")
    view["active_since"] = alert.get("created_at") if alert else None
    view["testing"] = bool(alert and alert.get("test"))
    view["tag"] = tag
    return view


def _testing(hass: HomeAssistant) -> list[str]:
    """Rule ids currently in test mode (across engines)."""
    return [
        rid
        for engine in hass.data.get(DOMAIN, {}).values()
        for rid in engine.testing_rule_ids()
    ]


def _yaml_rules(hass: HomeAssistant) -> list[dict[str, Any]]:
    return [dict(r) for r in hass.data.get(DATA_YAML_RULES) or []]


def _yaml_index(hass: HomeAssistant, subentry_id: str) -> int | None:
    for index, rule in enumerate(_yaml_rules(hass)):
        if rule_id_for(rule) == subentry_id:
            return index
    return None


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
            "yaml_mode": _yaml_mode(hass),
            "read_only": _read_only(hass),
            "rules_file": rules_file_rel(hass) if _file_mode(hass) else None,
            "persons": _persons(hass),
            "mobile_targets": list(_settings(hass)[nc_settings.CONF_OTHER_PHONES]),
            "wall_sheets": list(_settings(hass)[nc_settings.CONF_WALL_SHEETS]),
            "wall_pages": list(_settings(hass)[nc_settings.CONF_WALL_PAGES]),
            "quiet_defaults": dict(PRIORITY_QUIET_HOURS_DEFAULT),
            "snooze_default": list(DEFAULT_SNOOZE_OPTIONS),
            "takeover_max_chars": TAKEOVER_MAX_CHARS,
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
    if _yaml_mode(hass):
        # YAML mode: list the file rules (read-only in the panel), with ids
        # matching what the engine registered (yaml_<tag>). Only rules that
        # validate are shown — invalid ones are skipped by the engine too and
        # surfaced via the yaml_rules_invalid repair issue, so the panel view
        # always matches what's actually loaded.
        rules = []
        for data in hass.data.get(DATA_YAML_RULES) or []:
            try:
                validated = _validate_rule(_sanitize(dict(data)))
            except vol.Invalid:
                continue
            rules.append(_with_status(hass, _rule_view(rule_id_for(validated), validated)))
        connection.send_result(
            msg["id"],
            {
                "rules": rules,
                "yaml_mode": True,
                "read_only": _read_only(hass),
                "testing": _testing(hass),
            },
        )
        return
    rules = [
        _with_status(hass, _rule_view(sid, dict(sub.data)))
        for sid, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_TYPE_RULE
    ]
    connection.send_result(msg["id"], {"rules": rules, "testing": _testing(hass)})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/rules/create",
        vol.Required("rule"): dict,
    }
)
@websocket_api.async_response
async def ws_create_rule(hass, connection, msg) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    if _reject_if_read_only(hass, connection, msg):
        return
    try:
        rule = _validate_rule(_sanitize(msg["rule"]))
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalid_rule", str(err))
        return
    name = rule.get("name") or "Rule"
    tag = rule.get("dedup_tag") or slugify(name)

    if _file_mode(hass):
        rules = _yaml_rules(hass)
        if any(rule_id_for(r) == f"yaml_{tag}" for r in rules):
            connection.send_error(msg["id"], "duplicate", f"A rule with tag '{tag}' exists")
            return
        rules.append(rule)
        try:
            await async_save_yaml_rules(hass, rules)
        except Exception as err:  # noqa: BLE001 - surface the file error to the panel
            _LOGGER.exception("notification_center: failed to save rules file")
            connection.send_error(msg["id"], "create_failed", str(err))
            return
        connection.send_result(msg["id"], {"subentry_id": rule_id_for(rule)})
        return

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
@websocket_api.async_response
async def ws_update_rule(hass, connection, msg) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    if _reject_if_read_only(hass, connection, msg):
        return
    try:
        rule = _validate_rule(_sanitize(msg["rule"]))
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalid_rule", str(err))
        return

    if _file_mode(hass):
        rules = _yaml_rules(hass)
        index = _yaml_index(hass, msg["subentry_id"])
        if index is None:
            connection.send_error(msg["id"], "not_found", "Rule not found")
            return
        new_id = rule_id_for(rule)
        if new_id != msg["subentry_id"] and any(
            rule_id_for(r) == new_id for i, r in enumerate(rules) if i != index
        ):
            connection.send_error(msg["id"], "duplicate", "A rule with that tag exists")
            return
        rules[index] = rule
        try:
            await async_save_yaml_rules(hass, rules)
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("notification_center: failed to save rules file")
            connection.send_error(msg["id"], "update_failed", str(err))
            return
        connection.send_result(msg["id"], {"subentry_id": new_id})
        return

    subentry = entry.subentries.get(msg["subentry_id"])
    if subentry is None or subentry.subentry_type != SUBENTRY_TYPE_RULE:
        connection.send_error(msg["id"], "not_found", "Rule not found")
        return
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
@websocket_api.async_response
async def ws_delete_rule(hass, connection, msg) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    if _reject_if_read_only(hass, connection, msg):
        return

    if _file_mode(hass):
        rules = _yaml_rules(hass)
        index = _yaml_index(hass, msg["subentry_id"])
        if index is None:
            connection.send_error(msg["id"], "not_found", "Rule not found")
            return
        rules.pop(index)
        try:
            await async_save_yaml_rules(hass, rules)
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("notification_center: failed to save rules file")
            connection.send_error(msg["id"], "delete_failed", str(err))
            return
        connection.send_result(msg["id"], {"success": True})
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


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/rules/test",
        vol.Required("subentry_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.async_response
async def ws_test_rule(hass, connection, msg) -> None:
    """Start/stop test mode: fire the rule as designed through every channel."""
    found = False
    for engine in hass.data.get(DOMAIN, {}).values():
        found = await engine.async_test_rule(msg["subentry_id"], msg["enabled"]) or found
    if not found:
        connection.send_error(msg["id"], "not_found", "Rule not found")
        return
    connection.send_result(msg["id"], {"testing": _testing(hass)})


# --- Template rendering (editor previews, "Shows as" lines) -----------------
_RENDER_MAX = 2000


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/render",
        vol.Required("templates"): {str: vol.Any(str, None)},
    }
)
@callback
def ws_render(hass, connection, msg) -> None:
    """Render several templates at once: {key: template} -> {key: {text}|{error}}.

    Plain text renders to itself. Errors are returned per key so one bad
    template doesn't blank the rest of the preview.
    """
    results: dict[str, dict[str, str]] = {}
    for key, source in msg["templates"].items():
        source = source or ""
        if "{" not in source:
            results[key] = {"text": source}
            continue
        try:
            text = Template(source, hass).async_render(parse_result=False)
            results[key] = {"text": str(text)[:_RENDER_MAX]}
        except TemplateError as err:
            results[key] = {"error": str(err)}
        except Exception as err:  # noqa: BLE001 - surface any failure as text
            results[key] = {"error": str(err) or type(err).__name__}
    connection.send_result(msg["id"], {"results": results})


# --- History (Recent tab) ---------------------------------------------------
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/history/list", vol.Optional("limit"): int}
)
@callback
def ws_history(hass, connection, msg) -> None:
    items: list[dict[str, Any]] = []
    for engine in _engines(hass):
        items.extend(engine.history())
    items.sort(key=lambda h: h.get("cleared_at") or "", reverse=True)
    connection.send_result(msg["id"], {"history": items[: msg.get("limit") or 50]})


# --- Settings tab -----------------------------------------------------------
def _available_phones(hass: HomeAssistant) -> list[str]:
    """Phones Home Assistant knows about (companion-app notify services)."""
    return sorted(
        f"notify.{name}"
        for name in hass.services.async_services().get("notify", {})
        if name.startswith("mobile_app_")
    )


def _settings_payload(hass: HomeAssistant) -> dict[str, Any]:
    st = _settings(hass)
    health: list[dict[str, Any]] = []
    status: dict[str, Any] = {}
    for engine in _engines(hass):
        health.extend(engine.health())
        status.update(engine.phone_status())
    return {
        "settings": st,
        "health": health,
        "phone_status": status,
        "available_phones": _available_phones(hass),
        "read_only": False,
    }


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/get"})
@callback
def ws_settings_get(hass, connection, msg) -> None:
    if _entry(hass) is None:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    connection.send_result(msg["id"], _settings_payload(hass))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/settings/update", vol.Required("settings"): dict}
)
@websocket_api.async_response
async def ws_settings_update(hass, connection, msg) -> None:
    """Save the whole settings object in one call (the panel's Save)."""
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    try:
        options = nc_settings.to_options(msg["settings"], dict(entry.options))
        hass.config_entries.async_update_entry(entry, options=options)
    except Exception as err:  # noqa: BLE001 - surface a real message
        _LOGGER.exception("notification_center: failed to save settings")
        connection.send_error(msg["id"], "update_failed", str(err))
        return
    # The update listener reloads the engine; let it settle before reporting
    # health so it reflects the new settings.
    await hass.async_block_till_done()
    connection.send_result(msg["id"], _settings_payload(hass))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/settings/test_push", vol.Required("notify_service"): str}
)
@websocket_api.async_response
async def ws_settings_test_push(hass, connection, msg) -> None:
    engines = _engines(hass)
    if not engines:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    error = await engines[0].async_test_push_one(msg["notify_service"])
    connection.send_result(msg["id"], {"ok": error is None, "error": error})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/settings/test_announcement",
        vol.Optional("engine"): vol.Any(str, None),
        vol.Optional("media_players", default=list): [str],
    }
)
@websocket_api.async_response
async def ws_settings_test_announcement(hass, connection, msg) -> None:
    engines = _engines(hass)
    if not engines:
        connection.send_error(msg["id"], "not_found", "Notification Center not set up")
        return
    error = await engines[0].async_test_announcement(msg.get("engine"), msg["media_players"])
    connection.send_result(msg["id"], {"ok": error is None, "error": error})
