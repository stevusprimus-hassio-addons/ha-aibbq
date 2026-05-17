"""Number platform for AiBBQ Life integration — min/max temperature thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Awaitable

from homeassistant.components.number import NumberMode, RestoreNumber, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUMBER_TEMP_MIN, NUMBER_TEMP_MAX
from .coordinator import AiBBQCoordinator


@dataclass(frozen=True, kw_only=True)
class AiBBQNumberDescription(NumberEntityDescription):
    value_fn: Callable[[AiBBQCoordinator], float | None]
    set_fn: Callable[[AiBBQCoordinator, float], Awaitable[None]]


NUMBERS: tuple[AiBBQNumberDescription, ...] = (
    AiBBQNumberDescription(
        key=NUMBER_TEMP_MIN,
        translation_key=NUMBER_TEMP_MIN,
        name="Min Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=300,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda c: c.ha_min_temp,
        set_fn=lambda c, v: c.async_set_min_temp(v),
    ),
    AiBBQNumberDescription(
        key=NUMBER_TEMP_MAX,
        translation_key=NUMBER_TEMP_MAX,
        name="Max Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=300,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda c: c.ha_max_temp,
        set_fn=lambda c, v: c.async_set_max_temp(v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AiBBQCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AiBBQNumberEntity(coordinator, entry, description) for description in NUMBERS
    )


class AiBBQNumberEntity(CoordinatorEntity[AiBBQCoordinator], RestoreNumber):
    """Min or max temperature threshold — value is persisted across restarts."""

    entity_description: AiBBQNumberDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AiBBQCoordinator,
        entry: ConfigEntry,
        description: AiBBQNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        assert entry.unique_id is not None
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data and last_data.native_value is not None:
            await self.entity_description.set_fn(self.coordinator, float(last_data.native_value))

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.set_fn(self.coordinator, value)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
