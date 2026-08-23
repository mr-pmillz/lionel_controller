"""Number platform for the Lionel Train Controller integration."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LionelConfigEntry
from .const import (
    SOUND_SOURCE_BELL,
    SOUND_SOURCE_ENGINE,
    SOUND_SOURCE_HORN,
    SOUND_SOURCE_SPEECH,
    VOLUME_MAX,
    VOLUME_MIN,
)
from .coordinator import LionelTrainCoordinator
from .entity import LionelTrainEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class LionelNumberDescription(NumberEntityDescription):
    """Describes a Lionel number entity."""

    value_fn: Callable[[LionelTrainCoordinator], int]
    set_fn: Callable[[LionelTrainCoordinator, int], Awaitable[bool]]


def _volume_description(
    key: str, name: str, icon: str, source: int
) -> LionelNumberDescription:
    """Build a description for one sound source's volume control."""
    return LionelNumberDescription(
        key=key,
        name=name,
        icon=icon,
        native_min_value=VOLUME_MIN,
        native_max_value=VOLUME_MAX,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=lambda coordinator, _key=key: getattr(coordinator, _key),
        set_fn=lambda coordinator, value, _source=source: (
            coordinator.async_set_sound_volume(_source, value)
        ),
    )


NUMBER_DESCRIPTIONS: tuple[LionelNumberDescription, ...] = (
    LionelNumberDescription(
        key="throttle",
        name="Throttle",
        icon="mdi:train",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        value_fn=lambda coordinator: coordinator.speed,
        set_fn=lambda coordinator, value: coordinator.async_set_speed(value),
    ),
    LionelNumberDescription(
        key="master_volume",
        name="Master Volume",
        icon="mdi:volume-high",
        native_min_value=VOLUME_MIN,
        native_max_value=VOLUME_MAX,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=lambda coordinator: coordinator.master_volume,
        set_fn=lambda coordinator, value: coordinator.async_set_master_volume(value),
    ),
    _volume_description("horn_volume", "Horn Volume", "mdi:bullhorn", SOUND_SOURCE_HORN),
    _volume_description("bell_volume", "Bell Volume", "mdi:bell", SOUND_SOURCE_BELL),
    _volume_description(
        "speech_volume", "Speech Volume", "mdi:account-voice", SOUND_SOURCE_SPEECH
    ),
    _volume_description("engine_volume", "Engine Volume", "mdi:train", SOUND_SOURCE_ENGINE),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LionelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Lionel Train number platform."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        LionelTrainNumber(coordinator, description)
        for description in NUMBER_DESCRIPTIONS
    )


class LionelTrainNumber(LionelTrainEntity, NumberEntity):
    """A numeric control on the locomotive."""

    entity_description: LionelNumberDescription

    def __init__(
        self,
        coordinator: LionelTrainCoordinator,
        description: LionelNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.entity_description.value_fn(self._coordinator)

    async def async_set_native_value(self, value: float) -> None:
        """Send the new value to the locomotive."""
        await self.entity_description.set_fn(self._coordinator, int(value))
