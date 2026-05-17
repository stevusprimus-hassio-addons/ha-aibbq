"""Sensor platform for AiBBQ Life integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_RSSI, SENSOR_TEMP_CURRENT
from .coordinator import AiBBQCoordinator


@dataclass(frozen=True, kw_only=True)
class AiBBQSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value accessor."""
    value_fn: Callable[[AiBBQCoordinator], float | None]


SENSORS: tuple[AiBBQSensorDescription, ...] = (
    AiBBQSensorDescription(
        key=SENSOR_TEMP_CURRENT,
        name="Probe Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=lambda c: c.data.best_temp,
    ),
    AiBBQSensorDescription(
        key=SENSOR_RSSI,
        translation_key=SENSOR_RSSI,
        name="Signal Strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.rssi,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AiBBQ sensor entities from a config entry."""
    coordinator: AiBBQCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AiBBQSensorEntity(coordinator, entry, description)
        for description in SENSORS
    )


class AiBBQSensorEntity(CoordinatorEntity[AiBBQCoordinator], SensorEntity):
    """A single AiBBQ sensor (temperature or target)."""

    entity_description: AiBBQSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AiBBQCoordinator,
        entry: ConfigEntry,
        description: AiBBQSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        assert entry.unique_id is not None
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name="AiBBQ Life Thermometer",
            manufacturer="AiBBQ",
            model="AIBBQLife",
        )

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
