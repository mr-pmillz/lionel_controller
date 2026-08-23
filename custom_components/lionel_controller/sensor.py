"""Sensor platform for the Lionel Train Controller integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LionelConfigEntry
from .entity import LionelTrainEntity

_LOGGER = logging.getLogger(__name__)

NO_DATA = "No data"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LionelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Lionel Train sensor platform."""
    async_add_entities([LionelTrainStatusSensor(config_entry.runtime_data)])


class LionelTrainStatusSensor(LionelTrainEntity, SensorEntity):
    """Sensor exposing the most recent status frame from the locomotive."""

    _attr_name = "Status"
    _attr_icon = "mdi:train"

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str:
        """Return the last notification payload as hex."""
        return self._coordinator.last_notification_hex or NO_DATA

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the decoded locomotive state."""
        return {
            "speed": self._coordinator.speed,
            "direction_forward": self._coordinator.direction_forward,
            "lights_on": self._coordinator.lights_on,
            "bell_on": self._coordinator.bell_on,
            "horn_on": self._coordinator.horn_on,
            "connected": self._coordinator.connected,
        }
