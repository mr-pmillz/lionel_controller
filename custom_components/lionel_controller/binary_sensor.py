"""Binary sensor platform for the Lionel Train Controller integration."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up the Lionel Train binary sensor platform."""
    async_add_entities([LionelTrainConnectionSensor(config_entry.runtime_data)])


class LionelTrainConnectionSensor(LionelTrainEntity, BinarySensorEntity):
    """Binary sensor reporting the Bluetooth connection state."""

    _attr_name = "Connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, "connection")

    @property
    def is_on(self) -> bool:
        """Return True if the locomotive is connected."""
        return self._coordinator.connected

    @property
    def available(self) -> bool:
        """Always available: it reports connection state, including 'off'."""
        return True
