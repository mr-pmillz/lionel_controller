"""Switch platform for the Lionel Train Controller integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LionelConfigEntry
from .entity import LionelTrainEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LionelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Lionel Train switch platform."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            LionelTrainLightsSwitch(coordinator),
            LionelTrainHornSwitch(coordinator),
            LionelTrainBellSwitch(coordinator),
        ]
    )


class LionelTrainLightsSwitch(LionelTrainEntity, SwitchEntity):
    """Switch for controlling train lights."""

    _attr_translation_key = "lights"
    _attr_name = "Lights"
    _attr_icon = "mdi:lightbulb"

    def __init__(self, coordinator) -> None:
        """Initialize the lights switch."""
        super().__init__(coordinator, "lights")

    @property
    def is_on(self) -> bool:
        """Return True if the lights are on."""
        return self._coordinator.lights_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the lights."""
        await self._coordinator.async_set_lights(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the lights."""
        await self._coordinator.async_set_lights(False)


class LionelTrainHornSwitch(LionelTrainEntity, SwitchEntity):
    """Switch for controlling the train horn."""

    _attr_translation_key = "horn"
    _attr_name = "Horn"
    _attr_icon = "mdi:bullhorn"

    def __init__(self, coordinator) -> None:
        """Initialize the horn switch."""
        super().__init__(coordinator, "horn")

    @property
    def is_on(self) -> bool:
        """Return True if the horn is on."""
        return self._coordinator.horn_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the horn."""
        await self._coordinator.async_set_horn(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the horn."""
        await self._coordinator.async_set_horn(False)


class LionelTrainBellSwitch(LionelTrainEntity, SwitchEntity):
    """Switch for controlling the train bell."""

    _attr_translation_key = "bell"
    _attr_name = "Bell"
    _attr_icon = "mdi:bell"

    def __init__(self, coordinator) -> None:
        """Initialize the bell switch."""
        super().__init__(coordinator, "bell")

    @property
    def is_on(self) -> bool:
        """Return True if the bell is on."""
        return self._coordinator.bell_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the bell."""
        await self._coordinator.async_set_bell(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the bell."""
        await self._coordinator.async_set_bell(False)
