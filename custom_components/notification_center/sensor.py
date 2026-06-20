"""Sensor platform for Notification Center."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    PARENT_TITLE,
    PRIORITY_COLORS,
    PRIORITY_CRITICAL,
    PRIORITY_ICONS,
    PRIORITY_NONE,
    PRIORITY_WARNING,
    SIGNAL_UPDATE,
)
from .engine import NotificationEngine


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    engine: NotificationEngine = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            NotificationCenterSensor(engine, entry),
            NotificationPrioritySensor(engine, entry),
        ]
    )


class _BaseSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, engine: NotificationEngine, entry: ConfigEntry) -> None:
        self._engine = engine
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=PARENT_TITLE,
            manufacturer="Notification Center",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE.format(self._entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class NotificationCenterSensor(_BaseSensor):
    """Main sensor: state is the active alert count; attrs hold the alerts."""

    _attr_name = "Active count"
    _attr_icon = "mdi:bell-badge"

    def __init__(self, engine: NotificationEngine, entry: ConfigEntry) -> None:
        super().__init__(engine, entry)
        self._attr_unique_id = f"{entry.entry_id}_center"
        # Pin the object id so the friendly name can change without altering the
        # entity_id that cards/automations reference (single-instance integration).
        self.entity_id = "sensor.notification_center"

    @property
    def native_value(self) -> int:
        return self._engine.count()

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "priority": self._engine.highest_priority(),
            "alerts": self._engine.alert_list(),
            "by_priority": self._engine.by_priority(),
        }


class NotificationPrioritySensor(_BaseSensor):
    """Highest active priority — drop-in for the old notification_icon_priority."""

    _attr_name = "Highest priority"

    def __init__(self, engine: NotificationEngine, entry: ConfigEntry) -> None:
        super().__init__(engine, entry)
        self._attr_unique_id = f"{entry.entry_id}_priority"
        self.entity_id = "sensor.notification_center_priority"

    @property
    def native_value(self) -> str:
        return self._engine.highest_priority()

    @property
    def icon(self) -> str:
        priority = self._engine.highest_priority()
        if priority == PRIORITY_NONE:
            return "mdi:bell-outline"
        return PRIORITY_ICONS.get(priority, "mdi:bell")

    @property
    def extra_state_attributes(self) -> dict:
        alerts = self._engine.alert_list()
        priority = self._engine.highest_priority()
        return {
            "color": PRIORITY_COLORS.get(priority, "#7295B2")
            if priority != PRIORITY_NONE
            else "#9A988F",
            "critical": [a["tag"] for a in alerts if a["priority"] == PRIORITY_CRITICAL],
            "warning": [a["tag"] for a in alerts if a["priority"] == PRIORITY_WARNING],
            "count": self._engine.count(),
        }
