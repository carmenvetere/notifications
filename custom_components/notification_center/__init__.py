"""The Notification Center integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CHANNELS,
    DOMAIN,
    PLATFORMS,
    PRIORITIES,
    PRIORITY_INFO,
    SERVICE_ACKNOWLEDGE,
    SERVICE_DISMISS,
    SERVICE_RELOAD,
    SERVICE_SEND,
    SERVICE_SNOOZE,
)
from .engine import NotificationEngine

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Notification Center from a config entry."""
    engine = NotificationEngine(hass, entry)
    await engine.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = engine

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        engine: NotificationEngine = hass.data[DOMAIN].pop(entry.entry_id)
        await engine.async_unload()
        if not hass.data[DOMAIN]:
            _async_unregister_services(hass)
    return unload_ok


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

    async def _acknowledge(call: ServiceCall) -> None:
        for engine in _engines():
            engine.async_acknowledge(call.data["tag"])

    async def _dismiss(call: ServiceCall) -> None:
        for engine in _engines():
            engine.async_dismiss(call.data["tag"])

    async def _snooze(call: ServiceCall) -> None:
        for engine in _engines():
            engine.async_snooze(call.data["tag"], call.data["minutes"])

    async def _reload(call: ServiceCall) -> None:
        for engine in _engines():
            await engine.async_reload()

    hass.services.async_register(DOMAIN, SERVICE_SEND, _send, schema=SEND_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_ACKNOWLEDGE, _acknowledge, schema=TAG_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_DISMISS, _dismiss, schema=TAG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE, _snooze, schema=SNOOZE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RELOAD, _reload)


@callback
def _async_unregister_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_SEND,
        SERVICE_ACKNOWLEDGE,
        SERVICE_DISMISS,
        SERVICE_SNOOZE,
        SERVICE_RELOAD,
    ):
        hass.services.async_remove(DOMAIN, service)
