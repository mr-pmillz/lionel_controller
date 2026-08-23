"""Button platform for the Lionel Train Controller integration."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LionelConfigEntry
from .const import ANNOUNCEMENTS
from .coordinator import LionelTrainCoordinator
from .entity import LionelTrainEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class LionelButtonDescription(ButtonEntityDescription):
    """Describes a Lionel button entity."""

    press_fn: Callable[[LionelTrainCoordinator], Awaitable[bool]]
    # Stays pressable even when the locomotive looks unreachable, so a stalled
    # connection can always be retried from the UI.
    always_available: bool = False


BUTTON_DESCRIPTIONS: tuple[LionelButtonDescription, ...] = (
    LionelButtonDescription(
        key="stop",
        name="Stop",
        icon="mdi:stop",
        press_fn=lambda coordinator: coordinator.async_set_speed(0),
    ),
    LionelButtonDescription(
        key="forward",
        name="Forward",
        icon="mdi:arrow-right",
        press_fn=lambda coordinator: coordinator.async_set_direction(True),
    ),
    LionelButtonDescription(
        key="reverse",
        name="Reverse",
        icon="mdi:arrow-left",
        press_fn=lambda coordinator: coordinator.async_set_direction(False),
    ),
    LionelButtonDescription(
        key="reconnect",
        name="Reconnect",
        icon="mdi:bluetooth-connect",
        press_fn=lambda coordinator: coordinator.async_force_reconnect(),
        always_available=True,
    ),
    LionelButtonDescription(
        key="disconnect",
        name="Disconnect",
        icon="mdi:bluetooth-off",
        press_fn=lambda coordinator: coordinator.async_disconnect(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LionelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Lionel Train button platform."""
    coordinator = config_entry.runtime_data

    buttons: list[ButtonEntity] = [
        LionelTrainButton(coordinator, description)
        for description in BUTTON_DESCRIPTIONS
    ]
    buttons.extend(
        LionelTrainButton(
            coordinator,
            LionelButtonDescription(
                key=f"announcement_{label.lower().replace(' ', '_')}",
                name=f"Announcement {label}",
                icon="mdi:bullhorn-variant",
                press_fn=(
                    lambda coordinator, _code=details["code"]: (
                        coordinator.async_play_announcement(_code)
                    )
                ),
            ),
        )
        for label, details in ANNOUNCEMENTS.items()
    )

    async_add_entities(buttons)


class LionelTrainButton(LionelTrainEntity, ButtonEntity):
    """A one-shot control on the locomotive."""

    entity_description: LionelButtonDescription

    def __init__(
        self,
        coordinator: LionelTrainCoordinator,
        description: LionelButtonDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Return True if the button can be pressed."""
        if self.entity_description.always_available:
            return True
        return super().available

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.entity_description.press_fn(self._coordinator)
