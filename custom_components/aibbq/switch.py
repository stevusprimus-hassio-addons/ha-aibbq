"""Switch platform for AiBBQ Life integration — enable/disable alarms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SWITCH_ALARM_LOW_ENABLED, SWITCH_ALARM_HIGH_ENABLED
from .coordinator import AiBBQCoordinator


@dataclass(frozen=True, kw_only=True)
class AiBBQSwitchDescription(SwitchEntityDescription):
    is_on_fn: Callable[[AiBBQCoordinator], bool]
    set_fn: Callable[[AiBBQCoordinator, bool], None]


SWITCHES: tuple[AiBBQSwitchDescription, ...] = (
    AiBBQSwitchDescription(
        key=SWITCH_ALARM_LOW_ENABLED,
        translation_key=SWITCH_ALARM_LOW_ENABLED,
        name="Low Alarm Enabled",
        is_on_fn=lambda c: c.low_alarm_enabled,
        set_fn=lambda c, v: c.set_low_alarm_enabled(v),
    ),
    AiBBQSwitchDescription(
        key=SWITCH_ALARM_HIGH_ENABLED,
        translation_key=SWITCH_ALARM_HIGH_ENABLED,
        name="High Alarm Enabled",
        is_on_fn=lambda c: c.high_alarm_enabled,
        set_fn=lambda c, v: c.set_high_alarm_enabled(v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AiBBQCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AiBBQSwitch(coordinator, entry, description) for description in SWITCHES
    )


class AiBBQSwitch(CoordinatorEntity[AiBBQCoordinator], SwitchEntity, RestoreEntity):
    """Alarm enable switch — state is persisted across restarts."""

    entity_description: AiBBQSwitchDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AiBBQCoordinator,
        entry: ConfigEntry,
        description: AiBBQSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self.entity_description.set_fn(self.coordinator, last_state.state == STATE_ON)

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.coordinator)

    async def async_turn_on(self, **kwargs) -> None:
        self.entity_description.set_fn(self.coordinator, True)

    async def async_turn_off(self, **kwargs) -> None:
        self.entity_description.set_fn(self.coordinator, False)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
