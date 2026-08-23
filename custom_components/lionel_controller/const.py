"""Constants for the Lionel Train Controller integration."""
from __future__ import annotations

DOMAIN = "lionel_controller"

# Service UUIDs
LIONCHIEF_SERVICE_UUID = "e20a39f4-73f5-4bc4-a12f-17d1ad07a961"
DEFAULT_SERVICE_UUID = LIONCHIEF_SERVICE_UUID

# LionChief characteristic UUIDs
WRITE_CHARACTERISTIC_UUID = "08590f7e-db05-467e-8757-72f6faeb13d4"  # LionelCommand
NOTIFY_CHARACTERISTIC_UUID = "08590f7e-db05-467e-8757-72f6faeb14d3"  # LionelData

# Standard Device Information characteristics, mapped to device registry fields
MODEL_NUMBER_CHAR_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER_CHAR_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
HARDWARE_REVISION_CHAR_UUID = "00002a27-0000-1000-8000-00805f9b34fb"
SOFTWARE_REVISION_CHAR_UUID = "00002a28-0000-1000-8000-00805f9b34fb"
MANUFACTURER_NAME_CHAR_UUID = "00002a29-0000-1000-8000-00805f9b34fb"

DEVICE_INFO_CHARACTERISTICS = {
    MODEL_NUMBER_CHAR_UUID: "model",
    SERIAL_NUMBER_CHAR_UUID: "serial_number",
    HARDWARE_REVISION_CHAR_UUID: "hw_version",
    SOFTWARE_REVISION_CHAR_UUID: "sw_version",
    MANUFACTURER_NAME_CHAR_UUID: "manufacturer",
}

# Command codes (second byte of every frame)
CMD_SOUND_VOLUME = 0x44
CMD_SPEED = 0x45
CMD_DIRECTION = 0x46
CMD_BELL = 0x47
CMD_HORN = 0x48
CMD_DISCONNECT = 0x4B
CMD_MASTER_VOLUME = 0x4C
CMD_ANNOUNCEMENT = 0x4D
CMD_LIGHTS = 0x51
CMD_SMOKE = 0x52

# Direction values
DIRECTION_FORWARD = 0x01
DIRECTION_REVERSE = 0x02

# Sound sources for per-channel volume control
SOUND_SOURCE_HORN = 0x01
SOUND_SOURCE_BELL = 0x02
SOUND_SOURCE_SPEECH = 0x03
SOUND_SOURCE_ENGINE = 0x04

# Volume range supported by the locomotive
VOLUME_MIN = 0
VOLUME_MAX = 7

# The locomotive encodes throttle as 0x00-0x1F rather than a percentage.
SPEED_STEPS = 31

# Configuration keys
CONF_MAC_ADDRESS = "mac_address"
CONF_SERVICE_UUID = "service_uuid"

# Services
SERVICE_RELOAD_INTEGRATION = "reload_integration"

# Defaults
DEFAULT_NAME = "Lionel Train"

# Connection tuning
CONNECT_MAX_ATTEMPTS = 3
SEND_MAX_ATTEMPTS = 3
# Seconds to wait before another opportunistic connect after a failed attempt,
# so a locomotive that advertises constantly does not cause a connect storm.
RECONNECT_COOLDOWN = 30.0

# Announcement sounds, keyed by the label shown in the UI
ANNOUNCEMENTS = {
    "Random": {"code": 0x00},
    "Ready to Roll": {"code": 0x01},
    "Hey There": {"code": 0x02},
    "Squeaky": {"code": 0x03},
    "Water and Fire": {"code": 0x04},
    "Fastest Freight": {"code": 0x05},
    "Penna Flyer": {"code": 0x06},
}


def build_simple_command(command_code: int, parameters: list[int] | None = None) -> list[int]:
    """Build a LionChief command frame.

    Frames are ``[0x00, command, *parameters]``. The locomotive accepts these
    without a trailing checksum, which is what the reference implementations use.
    """
    return [0x00, command_code, *(parameters or [])]
