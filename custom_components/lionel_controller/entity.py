"""Shared entity base for the Lionel Train Controller integration."""
from __future__ import annotations

from homeassistant.helpers.entity import Entity

from .coordinator import LionelTrainCoordinator


class LionelTrainEntity(Entity):
    """Base entity wired to a LionelTrainCoordinator."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: LionelTrainCoordinator, key: str) -> None:
        """Initialize the entity."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.mac_address}_{key}"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates once the entity is registered.

        Subscribing here rather than in __init__ matters: writing state before
        the entity is added to hass raises NoEntitySpecifiedError.
        """
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.add_update_callback(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Return True if the locomotive is reachable."""
        return self._coordinator.available
