"""Sensor platform for AiBBQ Life integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_TEMP_CURRENT
from .coordinator import AiBBQCoordinator
from .parser import AiBBQState

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AiBBQSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value accessor."""
    value_fn: Callable[[AiBBQState], float | None]


SENSORS: tuple[AiBBQSensorDescription, ...] = (
    AiBBQSensorDescription(
        key=SENSOR_TEMP_CURRENT,
        name="Probe Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=lambda s: s.best_temp,
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
        """Return the current sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
