"""Verify the fixed lionel_controller integration on the user's HA version."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "lionel_controller"
MAC = "FC:1F:C3:9F:A5:4A"
LIONCHIEF_UUID = "e20a39f4-73f5-4bc4-a12f-17d1ad07a961"

ENTRY_DATA = {
    "mac_address": MAC,
    "name": "Lionel Train",
    "service_uuid": LIONCHIEF_UUID,
}

BT = "homeassistant.components.bluetooth"


def make_client():
    client = MagicMock()
    client.is_connected = True
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"PennaFlyer")
    client.disconnect = AsyncMock()
    return client


async def setup_entry(hass, *, device=None):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=MAC)
    entry.add_to_hass(hass)
    with patch(f"{BT}.async_ble_device_from_address", return_value=device), patch(
        f"{BT}.async_register_callback", return_value=lambda: None
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


# --------------------------------------------------------------------------
# The three original blockers
# --------------------------------------------------------------------------

async def test_no_deadlock_on_first_command(hass: HomeAssistant):
    """REGRESSION: sending a command while disconnected must not hang."""
    entry = await setup_entry(hass, device=None)
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    assert not coordinator.connected

    client = make_client()
    with patch(f"{BT}.async_ble_device_from_address", return_value=MagicMock()), patch(
        "custom_components.lionel_controller.coordinator.establish_connection",
        AsyncMock(return_value=client),
    ):
        result = await asyncio.wait_for(coordinator.async_set_speed(50), timeout=10)

    assert result is True, "command failed"
    assert coordinator.speed == 50
    client.write_gatt_char.assert_awaited()
    sent = bytes(client.write_gatt_char.await_args.args[1])
    print("\nthrottle 50% ->", sent.hex())
    # 50% of the locomotive's 0x00-0x1F throttle range rounds to 16.
    assert sent == bytes([0x00, 0x45, 16])


async def test_entities_available_when_loco_advertising(hass: HomeAssistant):
    """REGRESSION: controls must be usable when the loco is on but not yet connected."""
    entry = await setup_entry(hass, device=MagicMock())

    with patch(f"{BT}.async_ble_device_from_address", return_value=MagicMock()):
        for ent in hass.states.async_entity_ids():
            hass.states.async_set(ent, hass.states.get(ent).state)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        assert coordinator.available is True, "coordinator reports unavailable"

    unavailable = [
        e for e in hass.states.async_entity_ids()
        if hass.states.get(e).state == "unavailable"
    ]
    print("\nentities:", len(hass.states.async_entity_ids()), "unavailable:", len(unavailable))
    assert not unavailable, f"still unavailable: {unavailable}"


async def test_config_flow_uses_ha_bluetooth_not_own_scanner(hass: HomeAssistant):
    """REGRESSION: the flow must never construct its own BleakScanner."""
    import custom_components.lionel_controller.config_flow as cf

    assert not hasattr(cf, "BleakScanner"), "config_flow still imports BleakScanner"

    service_info = MagicMock()
    service_info.address = MAC
    service_info.name = "LionChief Penna Flyer"
    service_info.service_uuids = [LIONCHIEF_UUID]

    with patch(f"{BT}.async_discovered_service_info", return_value=[service_info]), patch(
        f"{BT}.async_last_service_info", return_value=service_info
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": MAC}
        )

    print("\nflow result:", result2["type"], result2.get("title"))
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"]["mac_address"] == MAC


# --------------------------------------------------------------------------
# Supporting behaviour
# --------------------------------------------------------------------------

async def test_manual_flow_when_nothing_discovered(hass: HomeAssistant):
    """With no locomotive advertising, the flow offers manual entry."""
    with patch(f"{BT}.async_discovered_service_info", return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["step_id"] == "manual"

        bad = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"mac_address": "nope", "name": "T", "service_uuid": LIONCHIEF_UUID}
        )
        assert bad["errors"] == {"mac_address": "invalid_mac"}

        good = await hass.config_entries.flow.async_configure(
            bad["flow_id"],
            {"mac_address": MAC.lower(), "name": "My Train", "service_uuid": LIONCHIEF_UUID},
        )
    print("\nmanual flow:", good["type"], good.get("data"))
    assert good["type"] is FlowResultType.CREATE_ENTRY
    assert good["data"]["mac_address"] == MAC


async def test_bluetooth_discovery_rejects_non_lionel(hass: HomeAssistant):
    """A non-LionChief device must be rejected before its unique_id is claimed."""
    other = MagicMock()
    other.address = "AA:BB:CC:DD:EE:FF"
    other.name = "Some Sensor"
    other.service_uuids = ["0000180a-0000-1000-8000-00805f9b34fb"]

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=other
    )
    print("\nnon-lionel discovery:", result["type"], result.get("reason"))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_lionel_device"


async def test_bluetooth_discovery_accepts_lionchief(hass: HomeAssistant):
    """A LionChief advertisement leads to a confirm step and an entry."""
    info = MagicMock()
    info.address = MAC
    info.name = "LionChief Penna Flyer"
    info.service_uuids = [LIONCHIEF_UUID]

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info
    )
    assert result["step_id"] == "bluetooth_confirm"
    created = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    print("\nBT discovery ->", created["type"], created.get("title"))
    assert created["type"] is FlowResultType.CREATE_ENTRY


async def test_unload_removes_service_and_disconnects(hass: HomeAssistant):
    """Unloading cleans up the service and closes the connection."""
    client = make_client()
    with patch(f"{BT}.async_ble_device_from_address", return_value=MagicMock()), patch(
        "custom_components.lionel_controller.coordinator.establish_connection",
        AsyncMock(return_value=client),
    ), patch(f"{BT}.async_register_callback", return_value=lambda: None):
        entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=MAC)
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert hass.services.has_service(DOMAIN, "reload_integration")
        assert entry.runtime_data.connected

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    print("\nservice removed:", not hass.services.has_service(DOMAIN, "reload_integration"))
    assert not hass.services.has_service(DOMAIN, "reload_integration")
    client.disconnect.assert_awaited()


async def test_setup_does_not_claim_success_when_offline(hass: HomeAssistant, caplog):
    """REGRESSION: setup must not log 'connected' when the loco is unreachable."""
    await setup_entry(hass, device=None)
    joined = caplog.text.lower()
    assert "successfully connected" not in joined
    assert "not reachable yet" in joined


async def test_notification_updates_state(hass: HomeAssistant):
    """A status frame from the locomotive updates speed, direction and lights."""
    entry = await setup_entry(hass, device=MagicMock())
    coordinator = entry.runtime_data
    # [0x00,0x81,0x02, speed=31, dir=fwd, 0x03, 0x0C, flags=lights|bell]
    coordinator._notification_handler(None, bytearray([0, 0x81, 2, 31, 1, 3, 0x0C, 0x06]))
    await hass.async_block_till_done()
    print("\nparsed:", coordinator.speed, coordinator.direction_forward,
          coordinator.lights_on, coordinator.bell_on)
    assert coordinator.speed == 100
    assert coordinator.direction_forward is True
    assert coordinator.lights_on is True
    assert coordinator.bell_on is True


async def test_volume_validation(hass: HomeAssistant):
    """Out-of-range volumes are rejected before any BLE traffic."""
    entry = await setup_entry(hass, device=MagicMock())
    with pytest.raises(ValueError):
        await entry.runtime_data.async_set_master_volume(99)
