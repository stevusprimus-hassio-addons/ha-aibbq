"""Binary sensor platform for AiBBQ Life integration — low/high alarms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BINARY_SENSOR_ALARM_LOW, BINARY_SENSOR_ALARM_HIGH, BINARY_SENSOR_CONNECTED, DOMAIN
from .coordinator import AiBBQCoordinator


@dataclass(frozen=True, kw_only=True)
class AiBBQBinarySensorDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[AiBBQCoordinator], bool]


BINARY_SENSORS: tuple[AiBBQBinarySensorDescription, ...] = (
    AiBBQBinarySensorDescription(
        key=BINARY_SENSOR_ALARM_LOW,
        translation_key=BINARY_SENSOR_ALARM_LOW,
        name="Low Temperature Alarm",
        is_on_fn=lambda c: c.alarm_low_active,
    ),
    AiBBQBinarySensorDescription(
        key=BINARY_SENSOR_ALARM_HIGH,
        translation_key=BINARY_SENSOR_ALARM_HIGH,
        name="High Temperature Alarm",
        is_on_fn=lambda c: c.alarm_high_active,
    ),
    AiBBQBinarySensorDescription(
        key=BINARY_SENSOR_CONNECTED,
        translation_key=BINARY_SENSOR_CONNECTED,
        name="Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        is_on_fn=lambda c: c.is_connected,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AiBBQCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AiBBQAlarmSensor(coordinator, entry, description) for description in BINARY_SENSORS
    )


class AiBBQAlarmSensor(CoordinatorEntity[AiBBQCoordinator], BinarySensorEntity):
    """Binary sensor that turns on when a temperature threshold is crossed."""

    entity_description: AiBBQBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AiBBQCoordinator,
        entry: ConfigEntry,
        description: AiBBQBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        assert entry.unique_id is not None
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
        )

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.coordinator)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
