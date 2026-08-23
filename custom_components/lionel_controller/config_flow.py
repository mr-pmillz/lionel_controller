"""Config flow for the Lionel Train Controller integration."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_MAC_ADDRESS,
    CONF_SERVICE_UUID,
    DEFAULT_NAME,
    DEFAULT_SERVICE_UUID,
    DOMAIN,
    LIONCHIEF_SERVICE_UUID,
)

_LOGGER = logging.getLogger(__name__)

MAC_ADDRESS_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def _is_lionchief(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if the advertisement is from a LionChief locomotive."""
    target = LIONCHIEF_SERVICE_UUID.lower()
    return any(uuid.lower() == target for uuid in service_info.service_uuids)


def _default_name(service_info: BluetoothServiceInfoBleak) -> str:
    """Return a friendly name for a discovered locomotive."""
    if service_info.name and service_info.name != service_info.address:
        return service_info.name
    return f"Lionel Train {service_info.address.replace(':', '')[-6:]}"


class LionelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lionel Train Controller."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a locomotive discovered by Home Assistant's Bluetooth stack."""
        # Reject non-LionChief devices before claiming their unique ID, so an
        # unrelated device is never bound to this integration.
        if not _is_lionchief(discovery_info):
            return self.async_abort(reason="not_lionel_device")

        await self.async_set_unique_id(format_mac(discovery_info.address))
        self._abort_if_unique_id_configured()

        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": _default_name(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a discovered locomotive."""
        assert self._discovery is not None
        name = _default_name(self._discovery)

        if user_input is not None:
            return self.async_create_entry(
                title=name,
                data={
                    CONF_MAC_ADDRESS: self._discovery.address,
                    CONF_NAME: name,
                    CONF_SERVICE_UUID: DEFAULT_SERVICE_UUID,
                },
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": name,
                "address": self._discovery.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick from the locomotives Home Assistant can see."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(
                format_mac(address), raise_on_progress=False
            )
            self._abort_if_unique_id_configured()

            service_info = bluetooth.async_last_service_info(
                self.hass, address, connectable=True
            )
            name = _default_name(service_info) if service_info else DEFAULT_NAME
            return self.async_create_entry(
                title=name,
                data={
                    CONF_MAC_ADDRESS: address,
                    CONF_NAME: name,
                    CONF_SERVICE_UUID: DEFAULT_SERVICE_UUID,
                },
            )

        # Use Home Assistant's own scanner results. Creating a BleakScanner
        # here would fight the Bluetooth integration for the adapter and fail.
        configured = self._async_current_ids()
        devices = {
            service_info.address: f"{_default_name(service_info)} ({service_info.address})"
            for service_info in bluetooth.async_discovered_service_info(
                self.hass, connectable=True
            )
            if _is_lionchief(service_info)
            and format_mac(service_info.address) not in configured
        }

        if not devices:
            return await self.async_step_manual()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)}),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fall back to entering a MAC address by hand."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_MAC_ADDRESS].strip().replace("-", ":").upper()
            if not MAC_ADDRESS_PATTERN.match(address):
                errors[CONF_MAC_ADDRESS] = "invalid_mac"
            else:
                await self.async_set_unique_id(
                    format_mac(address), raise_on_progress=False
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_MAC_ADDRESS: address,
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_SERVICE_UUID: user_input[CONF_SERVICE_UUID],
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC_ADDRESS): str,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Optional(
                        CONF_SERVICE_UUID, default=DEFAULT_SERVICE_UUID
                    ): str,
                }
            ),
            errors=errors,
        )
