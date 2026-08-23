"""The Lionel Train Controller integration."""
from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import (
    CONF_MAC_ADDRESS,
    CONF_SERVICE_UUID,
    DEFAULT_SERVICE_UUID,
    DOMAIN,
    SERVICE_RELOAD_INTEGRATION,
)
from .coordinator import LionelTrainCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

type LionelConfigEntry = ConfigEntry[LionelTrainCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LionelConfigEntry) -> bool:
    """Set up Lionel Train Controller from a config entry."""
    mac_address = entry.data[CONF_MAC_ADDRESS]
    name = entry.data.get(CONF_NAME) or entry.title
    service_uuid = entry.data.get(CONF_SERVICE_UUID, DEFAULT_SERVICE_UUID)

    coordinator = LionelTrainCoordinator(hass, mac_address, name, service_uuid)

    # A locomotive that is switched off simply is not advertising yet. That is
    # normal, not a setup failure, so the entry loads either way and connects
    # when the locomotive appears.
    if await coordinator.async_setup():
        _LOGGER.debug("Connected to Lionel locomotive at %s during setup", mac_address)
    else:
        _LOGGER.info(
            "Lionel locomotive at %s is not reachable yet; it will connect "
            "automatically when powered on and in range",
            mac_address,
        )

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Watch for the locomotive advertising so availability updates and a
    # connection is established as soon as it is powered on.
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            coordinator.async_on_advertisement,
            BluetoothCallbackMatcher(address=mac_address, connectable=True),
            BluetoothScanningMode.ACTIVE,
        )
    )
    entry.async_on_unload(coordinator.async_shutdown)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LionelConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)
        hass.services.async_remove(DOMAIN, SERVICE_RELOAD_INTEGRATION)

    return True


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once for the whole domain."""
    if hass.services.has_service(DOMAIN, SERVICE_RELOAD_INTEGRATION):
        return

    async def async_reload_integration(call: ServiceCall) -> None:
        """Reload one or all Lionel config entries."""
        entry_id = call.data.get("entry_id")
        if entry_id:
            if hass.config_entries.async_get_entry(entry_id) is None:
                raise ServiceValidationError(f"Unknown config entry: {entry_id}")
            entry_ids = [entry_id]
        else:
            entry_ids = list(hass.data.get(DOMAIN, {}))

        for target in entry_ids:
            _LOGGER.debug("Reloading Lionel config entry %s", target)
            await hass.config_entries.async_reload(target)

    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD_INTEGRATION, async_reload_integration
    )
