# Lionel Train Controller

A Home Assistant custom integration for controlling Lionel LionChief Bluetooth locomotives.

[![hacs][hacs-shield]][hacs-url]

> **About this fork.** This is a fork of [iamjoshk/lionel_controller](https://github.com/iamjoshk/lionel_controller),
> which was written as a GitHub Copilot exercise and archived. This fork fixes the
> bugs that prevented the integration from installing and operating, and brings it
> up to current Home Assistant API conventions. See [What this fork fixes](#what-this-fork-fixes).

## Requirements

- Home Assistant **2024.8.0** or newer (verified against 2026.8.3)
- A working [Bluetooth integration](https://www.home-assistant.io/integrations/bluetooth/) —
  either a local adapter or an [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)
- A Lionel LionChief Bluetooth locomotive

The integration declares `bluetooth_adapters` as a dependency, so Home Assistant sets
up its Bluetooth stack first and supplies a compatible `bleak`. Do not install `bleak`
yourself — a mismatched version breaks Home Assistant's Bluetooth support.

## Installation

### HACS

1. In Home Assistant, open **HACS**.
2. Click the three-dot menu and choose **Custom repositories**.
3. Add `https://github.com/mr-pmillz/lionel_controller` with type **Integration**.
4. Search for **Lionel Train Controller** and click **Download**.
5. Restart Home Assistant.

### Manual

1. Copy `custom_components/lionel_controller` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Setup

Power the locomotive on and place it within range of a Bluetooth adapter or proxy first —
it only advertises while powered.

### Automatic discovery

Home Assistant detects the locomotive by its LionChief service UUID and raises a
discovery notification. Go to **Settings → Devices & Services**, find the discovered
Lionel train, and click **Add**.

### Manual setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Lionel Train Controller**.
3. Pick your locomotive from the list of detected LionChief devices.

If no locomotive is detected, the flow falls back to a form where you can type the
Bluetooth address directly (format `FC:1F:C3:9F:A5:4A`). Find the address under
**Settings → Devices & Services → Bluetooth**, or with a Bluetooth scanner app.

## Entities

The integration creates one device per locomotive.

### Controls

| Entity | Type | Description |
| --- | --- | --- |
| Throttle | number | Speed, 0–100% |
| Master Volume | number | Overall volume, 0–7 |
| Horn / Bell / Speech / Engine Volume | number | Per-channel volume, 0–7 |
| Lights | switch | Locomotive lighting |
| Horn | switch | Horn sound |
| Bell | switch | Bell sound |
| Forward / Reverse | button | Set direction of travel |
| Stop | button | Set throttle to zero |
| Reconnect | button | Force a fresh Bluetooth connection |
| Disconnect | button | Drop the Bluetooth connection |
| Announcement (×7) | button | Conductor announcements |

### Diagnostics

| Entity | Type | Description |
| --- | --- | --- |
| Connection | binary_sensor | Whether a Bluetooth connection is open |
| Status | sensor | Most recent status frame, with decoded attributes |

## Dashboard

A ready-made dashboard view lives in [`dashboard/train-card.yaml`](dashboard/train-card.yaml):
status pills, speed presets, direction, bell/horn/lights, and the announcement
buttons.

It uses only Home Assistant's built-in cards — no custom card, HACS frontend
plugin, or `card_mod` styling. The blue-on-dark appearance comes from the default
dark theme.

To install it:

1. Check your entity IDs under **Developer Tools → States**. They come from the
   device name, so a locomotive named "Christmas Train" yields
   `switch.christmas_train_lights` and so on.
2. If your prefix differs, find and replace `christmas_train` in the file.
3. Open your dashboard, choose **Edit → ⋮ → Raw configuration editor**, and paste
   the block under `views:`.

The Slow / Medium / High presets set the throttle to 30, 60, and 100 percent.
Adjust those values in the YAML to suit your locomotive.

## Services

### `lionel_controller.reload_integration`

Reloads the integration to re-establish the Bluetooth connection.

| Field | Required | Description |
| --- | --- | --- |
| `entry_id` | no | Config entry to reload. Omit to reload every locomotive. |

## How connection handling works

The locomotive is only reachable while powered on, so the integration is built around
that rather than assuming a permanent connection:

- **Setup never fails because the locomotive is off.** The config entry loads and the
  entities are created regardless.
- **Entities are available whenever the locomotive is advertising**, not only when a
  GATT connection is already open. The connection is made lazily on first command.
- **Connections are established automatically** when the locomotive starts advertising,
  rate-limited to one attempt per 30 seconds so a constantly-advertising locomotive
  cannot cause a connect storm.
- **The Reconnect button is always enabled**, so a stalled connection can be retried
  even when everything else reports unavailable.

## What this fork fixes

The upstream integration could not be installed or operated. Three defects were
confirmed by reproducing them against Home Assistant 2026.8.3:

1. **Setup could never complete.** The config flow constructed its own `BleakScanner`
   and ran a discovery scan. Home Assistant owns the Bluetooth adapter, so this
   conflicts with its scanner and fails, leaving the flow stuck on `cannot_connect`.
   It now reads Home Assistant's own scan results via `async_discovered_service_info`.

2. **The first command deadlocked permanently.** `async_send_command` acquired
   `self._lock` and then awaited `_async_connect`, which acquired the same lock.
   `asyncio.Lock` is not reentrant, so the coroutine blocked forever and wedged the
   coordinator for the rest of the Home Assistant run. Locking is now expressed as an
   explicit contract: public methods acquire the lock, and `_locked` helpers assume it
   is already held.

3. **Every control was permanently unavailable.** Entity availability was tied to
   `coordinator.connected`, but the integration only connected while sending a command —
   which the UI would not let you send, because the entity was unavailable.
   Availability is now based on whether the locomotive is reachable.

Also fixed:

- `manifest.json` used the invalid key `bluetooth_discovery`, was missing the required
  `bluetooth_adapters` dependency, and declared `bleak>=0.20.0`, risking an upgrade that
  would break Home Assistant's Bluetooth stack. The manifest now passes `hassfest`.
- The Bluetooth matcher also matched the generic Device Information service
  (`0000180a-…`), which nearly every BLE device advertises, so unrelated devices
  triggered discovery flows. Discovery now matches only the LionChief service.
- `async_step_bluetooth` claimed a device's unique ID *before* checking whether it was
  a LionChief, so unrelated devices were bound to this integration.
- Setup logged "Successfully connected" even when the connection had failed.
- Entities registered their state-write callback in `__init__`, which can fire before
  the entity is added to Home Assistant.
- The `reload_integration` service closed over the first config entry, so with more than
  one locomotive it always reloaded the wrong one; it was also never removed on unload.
- `hacs.json` contained the invalid keys `domains` and `iot_class`.

## Protocol

- **Control service**: `e20a39f4-73f5-4bc4-a12f-17d1ad07a961`
- **Write characteristic**: `08590f7e-db05-467e-8757-72f6faeb13d4` (LionelCommand)
- **Notify characteristic**: `08590f7e-db05-467e-8757-72f6faeb14d3` (LionelData)

Command frames are `[0x00, command, *parameters]`. Throttle is encoded as `0x00`–`0x1F`
rather than a percentage. Status notifications arrive as
`[0x00, 0x81, 0x02, speed, direction, 0x03, 0x0C, flags]`, where `flags` bit 2 is the
lights and bit 1 is the bell.

## Troubleshooting

**The locomotive is not discovered.** It only advertises while powered on. Confirm it
appears under **Settings → Devices & Services → Bluetooth**. If Home Assistant runs in a
container or VM, make sure a Bluetooth adapter is passed through, or add an ESPHome
Bluetooth proxy.

**Entities are unavailable.** The locomotive is out of range or switched off. They
recover automatically once it advertises again.

**Commands are not getting through.** Press **Reconnect**. LionChief locomotives accept
only one Bluetooth connection at a time, so close the Lionel phone app first.

To capture detail for a bug report, add this to `configuration.yaml` and restart:

```yaml
logger:
  default: warning
  logs:
    custom_components.lionel_controller: debug
```

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements_test.txt
pytest
```

The test suite runs the integration inside a real Home Assistant instance and covers
the three regressions above. To validate the manifest the way Home Assistant's CI does:

```bash
python -m script.hassfest --integration-path /path/to/custom_components/lionel_controller
```

## Credits

- Protocol reverse engineering by [Property404](https://github.com/Property404/lionchief-controller)
- Original integration by [@iamjoshk](https://github.com/iamjoshk/lionel_controller)
- ESPHome reference implementation by [@iamjoshk](https://github.com/iamjoshk/home-assistant-collection/tree/main/ESPHome/LionelController)
- Additional protocol detail from [pedasmith's BluetoothDeviceController](https://github.com/pedasmith/BluetoothDeviceController/blob/main/BluetoothProtocolsDevices/Lionel_LionChief.cs)

[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
