"""Bluetooth connection coordinator for the Lionel Train Controller integration."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo

from .const import (
    CMD_ANNOUNCEMENT,
    CMD_BELL,
    CMD_DIRECTION,
    CMD_DISCONNECT,
    CMD_HORN,
    CMD_LIGHTS,
    CMD_MASTER_VOLUME,
    CMD_SMOKE,
    CMD_SOUND_VOLUME,
    CMD_SPEED,
    CONNECT_MAX_ATTEMPTS,
    DEVICE_INFO_CHARACTERISTICS,
    DOMAIN,
    NOTIFY_CHARACTERISTIC_UUID,
    RECONNECT_COOLDOWN,
    SEND_MAX_ATTEMPTS,
    SOUND_SOURCE_BELL,
    SOUND_SOURCE_ENGINE,
    SOUND_SOURCE_HORN,
    SOUND_SOURCE_SPEECH,
    SPEED_STEPS,
    VOLUME_MAX,
    VOLUME_MIN,
    WRITE_CHARACTERISTIC_UUID,
    build_simple_command,
)

_LOGGER = logging.getLogger(__name__)


class LionelTrainCoordinator:
    """Own the BLE connection to a single LionChief locomotive.

    Locking contract: ``_lock`` serialises every BLE operation. Methods
    suffixed ``_locked`` assume the caller already holds it and must never
    re-acquire it -- ``asyncio.Lock`` is not reentrant.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        mac_address: str,
        name: str,
        service_uuid: str,
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.mac_address = mac_address
        self.name = name
        self.service_uuid = service_uuid

        self._client: BleakClientWithServiceCache | None = None
        self._connected = False
        self._lock = asyncio.Lock()
        self._update_callbacks: set[Callable[[], None]] = set()
        self._connect_task: asyncio.Task | None = None
        self._last_connect_attempt = 0.0

        # Control state
        self._speed = 0
        self._direction_forward = True
        self._lights_on = True
        self._horn_on = False
        self._bell_on = False
        self._smoke_on = False

        self._master_volume = 5
        self._horn_volume = 5
        self._bell_volume = 5
        self._speech_volume = 5
        self._engine_volume = 5

        # Device information read over GATT
        self._device_details: dict[str, str] = {}
        self._last_notification_hex: str | None = None

    # ------------------------------------------------------------------
    # State exposed to entities
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Return True if a GATT connection is currently open."""
        return (
            self._connected
            and self._client is not None
            and self._client.is_connected
        )

    @property
    def available(self) -> bool:
        """Return True if the locomotive can be reached.

        Entities must not require a live GATT connection: the integration
        connects lazily, so gating availability on ``connected`` alone would
        leave every control permanently disabled with no way to trigger the
        connection that would enable it.
        """
        if self.connected:
            return True
        return self.ble_device is not None

    @property
    def ble_device(self):
        """Return the BLEDevice from Home Assistant's scanner, if advertising."""
        return bluetooth.async_ble_device_from_address(
            self.hass, self.mac_address, connectable=True
        )

    @property
    def speed(self) -> int:
        """Return current speed (0-100)."""
        return self._speed

    @property
    def direction_forward(self) -> bool:
        """Return True if direction is forward."""
        return self._direction_forward

    @property
    def lights_on(self) -> bool:
        """Return True if lights are on."""
        return self._lights_on

    @property
    def horn_on(self) -> bool:
        """Return True if horn is on."""
        return self._horn_on

    @property
    def bell_on(self) -> bool:
        """Return True if bell is on."""
        return self._bell_on

    @property
    def smoke_on(self) -> bool:
        """Return True if smoke unit is on."""
        return self._smoke_on

    @property
    def master_volume(self) -> int:
        """Return master volume (0-7)."""
        return self._master_volume

    @property
    def horn_volume(self) -> int:
        """Return horn volume (0-7)."""
        return self._horn_volume

    @property
    def bell_volume(self) -> int:
        """Return bell volume (0-7)."""
        return self._bell_volume

    @property
    def speech_volume(self) -> int:
        """Return speech volume (0-7)."""
        return self._speech_volume

    @property
    def engine_volume(self) -> int:
        """Return engine volume (0-7)."""
        return self._engine_volume

    @property
    def last_notification_hex(self) -> str | None:
        """Return the last notification hex string."""
        return self._last_notification_hex

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        info = DeviceInfo(
            identifiers={(DOMAIN, self.mac_address)},
            connections={(CONNECTION_BLUETOOTH, self.mac_address)},
            name=self.name,
            manufacturer=self._device_details.get("manufacturer") or "Lionel",
            model=self._device_details.get("model") or "LionChief Locomotive",
        )
        if sw_version := self._device_details.get("sw_version"):
            info["sw_version"] = sw_version
        if hw_version := self._device_details.get("hw_version"):
            info["hw_version"] = hw_version
        if serial_number := self._device_details.get("serial_number"):
            info["serial_number"] = serial_number
        return info

    # ------------------------------------------------------------------
    # Entity update plumbing
    # ------------------------------------------------------------------

    def add_update_callback(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register a state-change listener and return an unsubscribe callable."""
        self._update_callbacks.add(update_callback)

        def _remove() -> None:
            self._update_callbacks.discard(update_callback)

        return _remove

    @callback
    def _notify_state_change(self) -> None:
        """Notify all registered listeners of a state change."""
        for update_callback in list(self._update_callbacks):
            try:
                update_callback()
            except Exception:
                # A misbehaving listener must not break BLE handling.
                _LOGGER.exception("Error in Lionel state update callback")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_setup(self) -> bool:
        """Try an initial connection. Return True if it succeeded."""
        if self.ble_device is None:
            _LOGGER.debug(
                "Locomotive %s is not advertising yet; will connect when it appears",
                self.mac_address,
            )
            return False
        try:
            await self.async_connect()
        except BleakError as err:
            _LOGGER.debug("Initial connection to %s failed: %s", self.mac_address, err)
            return False
        return True

    async def async_shutdown(self) -> None:
        """Disconnect and stop all background work."""
        if self._connect_task is not None:
            self._connect_task.cancel()
            self._connect_task = None
        async with self._lock:
            await self._async_disconnect_locked()

    @callback
    def async_on_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """React to the locomotive advertising.

        Availability flips as soon as the locomotive is powered on, and a
        background connection is started so the controls respond immediately.
        """
        self._notify_state_change()

        if self.connected or self._connect_task is not None:
            return
        if time.monotonic() - self._last_connect_attempt < RECONNECT_COOLDOWN:
            return

        self._connect_task = self.hass.async_create_task(
            self._async_background_connect()
        )

    async def _async_background_connect(self) -> None:
        """Connect opportunistically after the locomotive starts advertising."""
        try:
            await self.async_connect()
        except BleakError as err:
            _LOGGER.debug("Background connect to %s failed: %s", self.mac_address, err)
        finally:
            self._connect_task = None
            self._notify_state_change()

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    async def async_connect(self) -> None:
        """Connect to the locomotive, acquiring the BLE lock."""
        async with self._lock:
            await self._async_connect_locked()

    async def _async_connect_locked(self) -> None:
        """Connect to the locomotive. Caller must hold ``self._lock``."""
        if self.connected:
            return

        self._last_connect_attempt = time.monotonic()

        ble_device = self.ble_device
        if ble_device is None:
            raise BleakError(
                f"Locomotive {self.mac_address} is not in range or not powered on"
            )

        _LOGGER.debug("Establishing connection to %s", self.mac_address)
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self.name,
            disconnected_callback=self._async_on_disconnected,
            max_attempts=CONNECT_MAX_ATTEMPTS,
        )
        self._connected = True

        await self._async_read_device_info_locked()

        try:
            await self._client.start_notify(
                NOTIFY_CHARACTERISTIC_UUID, self._notification_handler
            )
            _LOGGER.debug("Subscribed to notifications on %s", NOTIFY_CHARACTERISTIC_UUID)
        except BleakError as err:
            _LOGGER.debug("Notifications unavailable on %s: %s", self.mac_address, err)

        _LOGGER.info("Connected to Lionel locomotive at %s", self.mac_address)
        self._notify_state_change()

    @callback
    def _async_on_disconnected(self, _client: BleakClientWithServiceCache) -> None:
        """Handle the locomotive dropping the connection."""
        _LOGGER.debug("Locomotive %s disconnected", self.mac_address)
        self._connected = False
        self._notify_state_change()

    async def _async_disconnect_locked(self) -> None:
        """Close the GATT connection. Caller must hold ``self._lock``."""
        client = self._client
        self._client = None
        self._connected = False
        if client is None:
            return
        try:
            await client.disconnect()
        except BleakError as err:
            _LOGGER.debug("Error disconnecting from %s: %s", self.mac_address, err)

    async def async_force_reconnect(self) -> bool:
        """Drop any existing connection and establish a fresh one."""
        _LOGGER.debug("Force reconnecting to %s", self.mac_address)
        async with self._lock:
            await self._async_disconnect_locked()
            self._last_connect_attempt = 0.0
            try:
                await self._async_connect_locked()
            except BleakError as err:
                _LOGGER.warning("Reconnect to %s failed: %s", self.mac_address, err)
                return False
        self._notify_state_change()
        return True

    async def _async_read_device_info_locked(self) -> None:
        """Read the standard Device Information characteristics."""
        for char_uuid, attr_name in DEVICE_INFO_CHARACTERISTICS.items():
            try:
                raw = await self._client.read_gatt_char(char_uuid)
            except (BleakError, EOFError) as err:
                _LOGGER.debug("Could not read %s: %s", char_uuid, err)
                continue
            if value := raw.decode("utf-8", errors="ignore").strip("\x00").strip():
                self._device_details[attr_name] = value

    def _notification_handler(self, _sender, data: bytearray) -> None:
        """Handle a status notification from the locomotive."""
        self._last_notification_hex = data.hex()
        _LOGGER.debug("Notification from %s: %s", self.mac_address, self._last_notification_hex)

        # Status frame: [0x00, 0x81, 0x02, speed, direction, 0x03, 0x0C, flags]
        if len(data) >= 8 and data[0] == 0x00 and data[1] == 0x81 and data[2] == 0x02:
            self._speed = round(data[3] / SPEED_STEPS * 100)
            self._direction_forward = data[4] == 0x01
            flags = data[7]
            self._lights_on = bool(flags & 0x04)
            self._bell_on = bool(flags & 0x02)
            _LOGGER.debug(
                "Status: speed=%d%% forward=%s lights=%s bell=%s",
                self._speed,
                self._direction_forward,
                self._lights_on,
                self._bell_on,
            )

        self._notify_state_change()

    # ------------------------------------------------------------------
    # Command sending
    # ------------------------------------------------------------------

    async def async_send_command(self, command_data: list[int]) -> bool:
        """Send a command, connecting first if necessary."""
        async with self._lock:
            return await self._async_send_command_locked(command_data)

    async def _async_send_command_locked(self, command_data: list[int]) -> bool:
        """Send a command. Caller must hold ``self._lock``."""
        payload = bytearray(command_data)
        hex_string = payload.hex()

        for attempt in range(1, SEND_MAX_ATTEMPTS + 1):
            if not self.connected:
                try:
                    await self._async_connect_locked()
                except BleakError as err:
                    _LOGGER.debug(
                        "Connect before command failed (attempt %d/%d): %s",
                        attempt,
                        SEND_MAX_ATTEMPTS,
                        err,
                    )
                    if attempt == SEND_MAX_ATTEMPTS:
                        _LOGGER.error(
                            "Could not reach locomotive %s to send %s",
                            self.mac_address,
                            hex_string,
                        )
                        return False
                    await asyncio.sleep(attempt * 0.5)
                    continue

            try:
                await self._client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, payload)
            except (BleakError, EOFError) as err:
                _LOGGER.debug(
                    "Command %s failed (attempt %d/%d): %s",
                    hex_string,
                    attempt,
                    SEND_MAX_ATTEMPTS,
                    err,
                )
                await self._async_disconnect_locked()
                if attempt == SEND_MAX_ATTEMPTS:
                    _LOGGER.error(
                        "Failed to send %s to %s after %d attempts",
                        hex_string,
                        self.mac_address,
                        SEND_MAX_ATTEMPTS,
                    )
                    self._notify_state_change()
                    return False
                await asyncio.sleep(attempt * 0.5)
                continue

            _LOGGER.debug("Sent %s to %s", hex_string, self.mac_address)
            self._last_notification_hex = hex_string
            self._notify_state_change()
            return True

        return False

    # ------------------------------------------------------------------
    # High level controls
    # ------------------------------------------------------------------

    async def async_set_speed(self, speed: int) -> bool:
        """Set train speed (0-100)."""
        if not 0 <= speed <= 100:
            raise ValueError("Speed must be between 0 and 100")
        hex_speed = round(speed / 100 * SPEED_STEPS)
        if await self.async_send_command(build_simple_command(CMD_SPEED, [hex_speed])):
            self._speed = speed
            self._notify_state_change()
            return True
        return False

    async def async_set_direction(self, forward: bool) -> bool:
        """Set train direction."""
        command = build_simple_command(CMD_DIRECTION, [0x01 if forward else 0x02])
        if await self.async_send_command(command):
            self._direction_forward = forward
            self._notify_state_change()
            return True
        return False

    async def async_set_lights(self, on: bool) -> bool:
        """Set train lights."""
        if await self.async_send_command(build_simple_command(CMD_LIGHTS, [int(on)])):
            self._lights_on = on
            self._notify_state_change()
            return True
        return False

    async def async_set_horn(self, on: bool) -> bool:
        """Set train horn."""
        if await self.async_send_command(build_simple_command(CMD_HORN, [int(on)])):
            self._horn_on = on
            self._notify_state_change()
            return True
        return False

    async def async_set_bell(self, on: bool) -> bool:
        """Set train bell."""
        if await self.async_send_command(build_simple_command(CMD_BELL, [int(on)])):
            self._bell_on = on
            self._notify_state_change()
            return True
        return False

    async def async_set_smoke(self, on: bool) -> bool:
        """Set the smoke unit on or off."""
        if await self.async_send_command(build_simple_command(CMD_SMOKE, [int(on)])):
            self._smoke_on = on
            self._notify_state_change()
            return True
        return False

    async def async_play_announcement(self, announcement_code: int) -> bool:
        """Play an announcement sound."""
        return await self.async_send_command(
            build_simple_command(CMD_ANNOUNCEMENT, [announcement_code, 0x00])
        )

    async def async_disconnect(self) -> bool:
        """Ask the locomotive to drop the Bluetooth link."""
        result = await self.async_send_command(
            build_simple_command(CMD_DISCONNECT, [0x00, 0x00])
        )
        async with self._lock:
            await self._async_disconnect_locked()
        self._notify_state_change()
        return result

    async def async_set_master_volume(self, volume: int) -> bool:
        """Set master volume (0-7)."""
        self._validate_volume(volume)
        command = build_simple_command(CMD_MASTER_VOLUME, [volume])
        if await self.async_send_command(command):
            self._master_volume = volume
            self._notify_state_change()
            return True
        return False

    async def async_set_sound_volume(self, sound_source: int, volume: int) -> bool:
        """Set the volume for one sound source."""
        self._validate_volume(volume)
        command = build_simple_command(CMD_SOUND_VOLUME, [sound_source, volume])
        if not await self.async_send_command(command):
            return False

        if sound_source == SOUND_SOURCE_HORN:
            self._horn_volume = volume
        elif sound_source == SOUND_SOURCE_BELL:
            self._bell_volume = volume
        elif sound_source == SOUND_SOURCE_SPEECH:
            self._speech_volume = volume
        elif sound_source == SOUND_SOURCE_ENGINE:
            self._engine_volume = volume

        self._notify_state_change()
        return True

    @staticmethod
    def _validate_volume(volume: int) -> None:
        """Raise if the volume is outside the supported range."""
        if not VOLUME_MIN <= volume <= VOLUME_MAX:
            raise ValueError(f"Volume must be between {VOLUME_MIN} and {VOLUME_MAX}")
