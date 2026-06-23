"""The Notification Center integration."""

from __future__ import annotations

import logging
import os

import voluptuous as vol

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify
from homeassistant.util.yaml import load_yaml

from .const import (
    CHANNELS,
    CONF_NAME,
    DOMAIN,
    IMPORTED_RULES_FILE,
    PLATFORMS,
    PRIORITIES,
    PRIORITY_INFO,
    SERVICE_DISMISS,
    SERVICE_IMPORT_RULES,
    SERVICE_RELOAD,
    SERVICE_RUN_ACTION,
    SERVICE_SEND,
    SERVICE_SNOOZE,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUBENTRY_TYPE_RULE,
)
from .engine import NotificationEngine
from .websocket_api import async_register as ws_register

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "notification-center"
PANEL_URL_BASE = "/notification_center_frontend"
PANEL_VERSION = "0.1.5"
PANEL_REGISTERED = f"{DOMAIN}_panel_registered"
STATIC_REGISTERED = f"{DOMAIN}_static_registered"

SEND_SCHEMA = vol.Schema(
    {
        vol.Optional("tag"): cv.string,
        vol.Required("title"): cv.string,
        vol.Optional("message", default=""): cv.string,
        vol.Optional("priority", default=PRIORITY_INFO): vol.In(PRIORITIES),
        vol.Optional("channels", default=list): vol.All(cv.ensure_list, [vol.In(CHANNELS)]),
        vol.Optional("icon"): cv.string,
        vol.Optional("color"): cv.string,
        vol.Optional("navigation_target"): cv.string,
        vol.Optional("tts_targets", default=list): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("tts_message"): cv.string,
        vol.Optional("digest_group"): cv.string,
    }
)

TAG_SCHEMA = vol.Schema({vol.Required("tag"): cv.string})

SNOOZE_SCHEMA = vol.Schema(
    {
        vol.Required("tag"): cv.string,
        vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

IMPORT_SCHEMA = vol.Schema(
    {
        vol.Optional("rules"): vol.All(cv.ensure_list, [dict]),
        vol.Optional("replace_existing", default=False): cv.boolean,
    }
)

RUN_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required("tag"): cv.string,
        vol.Required("action"): vol.Coerce(int),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Notification Center from a config entry."""
    engine = NotificationEngine(hass, entry)
    await engine.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = engine

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    ws_register(hass)
    try:
        await _async_register_panel(hass)
    except Exception:  # noqa: BLE001 - the panel is optional; don't fail setup
        _LOGGER.exception("notification_center: failed to register the setup panel")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        engine: NotificationEngine = hass.data[DOMAIN].pop(entry.entry_id)
        await engine.async_unload()
        if not hass.data[DOMAIN]:
            _async_unregister_services(hass)
            _async_remove_panel(hass)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the entry's persisted runtime state when it's removed."""
    await Store(hass, STORAGE_VERSION, STORAGE_KEY.format(entry.entry_id)).async_remove()


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Serve and register the custom setup panel (once)."""
    if hass.data.get(PANEL_REGISTERED):
        return
    hass.data[PANEL_REGISTERED] = True

    # The static path can only be registered once per HA run (no unregister API).
    if not hass.data.get(STATIC_REGISTERED):
        hass.data[STATIC_REGISTERED] = True
        panel_dir = os.path.join(os.path.dirname(__file__), "panel")
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_URL_BASE, panel_dir, cache_headers=False)]
        )
        # Auto-load the Lovelace card so `custom:notification-center-card` shows
        # up in the card picker without manual resource registration.
        frontend.add_extra_js_url(
            hass, f"{PANEL_URL_BASE}/notification-center-card.js?v={PANEL_VERSION}"
        )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="notification-center-panel",
        module_url=f"{PANEL_URL_BASE}/notification-center-panel.js?v={PANEL_VERSION}",
        sidebar_title="Notifications",
        sidebar_icon="mdi:bell-cog",
        require_admin=True,
        embed_iframe=False,
    )


@callback
def _async_remove_panel(hass: HomeAssistant) -> None:
    if hass.data.pop(PANEL_REGISTERED, None):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload rules in place when subentries/options change (no HA restart)."""
    engine: NotificationEngine | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if engine is not None:
        await engine.async_reload()


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND):
        return

    def _engines() -> list[NotificationEngine]:
        return list(hass.data.get(DOMAIN, {}).values())

    async def _send(call: ServiceCall) -> None:
        for engine in _engines():
            await engine.async_send_manual(dict(call.data))

    async def _dismiss(call: ServiceCall) -> None:
        for engine in _engines():
            engine.async_dismiss(call.data["tag"])

    async def _snooze(call: ServiceCall) -> None:
        for engine in _engines():
            engine.async_snooze(call.data["tag"], call.data["minutes"])

    async def _run_action(call: ServiceCall) -> None:
        for engine in _engines():
            await engine.async_run_action(call.data["tag"], call.data["action"])

    async def _reload(call: ServiceCall) -> None:
        for engine in _engines():
            await engine.async_reload()

    async def _import_rules(call: ServiceCall) -> None:
        rules = call.data.get("rules")
        if rules is None:
            path = os.path.join(os.path.dirname(__file__), IMPORTED_RULES_FILE)
            rules = await hass.async_add_executor_job(load_yaml, path) or []
        await _import_rules_into_entries(
            hass, rules, replace_existing=call.data["replace_existing"]
        )

    hass.services.async_register(DOMAIN, SERVICE_SEND, _send, schema=SEND_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISMISS, _dismiss, schema=TAG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE, _snooze, schema=SNOOZE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_RUN_ACTION, _run_action, schema=RUN_ACTION_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_RELOAD, _reload)
    hass.services.async_register(
        DOMAIN, SERVICE_IMPORT_RULES, _import_rules, schema=IMPORT_SCHEMA
    )


async def _import_rules_into_entries(
    hass: HomeAssistant, rules: list[dict], *, replace_existing: bool
) -> None:
    """Create one rule subentry per rule dict, idempotently (dedup by tag).

    Reuses each rule's ``dedup_tag`` (or a slug of its name) as the subentry
    unique_id so re-running the import skips rules already present.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        if replace_existing:
            for subentry_id, subentry in list(entry.subentries.items()):
                if subentry.subentry_type == SUBENTRY_TYPE_RULE:
                    hass.config_entries.async_remove_subentry(entry, subentry_id)

        existing = {
            subentry.unique_id
            for subentry in entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_RULE
        }
        for rule in rules:
            name = rule.get(CONF_NAME) or "Rule"
            tag = rule.get("dedup_tag") or slugify(name)
            if tag in existing:
                continue
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=dict(rule),
                    subentry_type=SUBENTRY_TYPE_RULE,
                    title=name,
                    unique_id=tag,
                ),
            )
            existing.add(tag)


@callback
def _async_unregister_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_SEND,
        SERVICE_DISMISS,
        SERVICE_SNOOZE,
        SERVICE_RUN_ACTION,
        SERVICE_RELOAD,
        SERVICE_IMPORT_RULES,
    ):
        hass.services.async_remove(DOMAIN, service)
