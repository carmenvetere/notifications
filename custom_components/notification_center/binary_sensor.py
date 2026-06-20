"""Binary sensor platform for Notification Center."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    PARENT_TITLE,
    PRIORITY_CRITICAL,
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
            ActiveBinarySensor(engine, entry),
            PriorityBinarySensor(
                engine, entry, PRIORITY_CRITICAL, "Critical active", "critical"
            ),
            PriorityBinarySensor(
                engine, entry, PRIORITY_WARNING, "Warning active", "warning"
            ),
        ]
    )


class _BaseBinarySensor(BinarySensorEntity):
    # No device_class: these read as On/Off rather than Problem/OK.
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


class ActiveBinarySensor(_BaseBinarySensor):
    _attr_name = "Any active"

    def __init__(self, engine: NotificationEngine, entry: ConfigEntry) -> None:
        super().__init__(engine, entry)
        self._attr_unique_id = f"{entry.entry_id}_active"
        self.entity_id = "binary_sensor.notification_center_active"

    @property
    def is_on(self) -> bool:
        return self._engine.count() > 0


class PriorityBinarySensor(_BaseBinarySensor):
    def __init__(
        self,
        engine: NotificationEngine,
        entry: ConfigEntry,
        priority: str,
        name: str,
        object_id: str,
    ) -> None:
        super().__init__(engine, entry)
        self._priority = priority
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{priority}"
        self.entity_id = f"binary_sensor.notification_center_{object_id}"

    @property
    def is_on(self) -> bool:
        return self._engine.by_priority().get(self._priority, 0) > 0
