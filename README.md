<p align="center">
  <img src="custom_components/adaptative_climate/brand/icon.png" alt="Adaptative Climate" width="128">
</p>

<h1 align="center">Adaptative Climate</h1>

<p align="center">
  <strong>One thermostat per room, whatever devices heat, cool or dry it.</strong>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.6%2B-41BDF5.svg?logo=homeassistant&logoColor=white" alt="Home Assistant 2026.6+">
  <a href="https://github.com/marsoupilami25/adaptative-climate/actions/workflows/tests.yml"><img src="https://github.com/marsoupilami25/adaptative-climate/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/marsoupilami25/adaptative-climate/actions/workflows/validate.yml"><img src="https://github.com/marsoupilami25/adaptative-climate/actions/workflows/validate.yml/badge.svg" alt="Validate"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"></a>
</p>

Adaptative Climate combines your `climate` entities (radiator, heat pump,
air conditioner, dehumidifier…) into a single thermostat. Each mode runs on
its own device: pick a mode, the right device starts and the others stop.
Targets, fan and swing follow you from one device to the other.

## ✨ Features

- 🔀 **One thermostat, several devices**: heat, cool, heat/cool, auto, dry
  and fan only, each on its own device. Only one runs at a time.
- 🌗 **Heat/cool from two devices**: a heater and an AC make one heat/cool
  mode. It heats below the low target and cools above the high one.
- 🎯 **Targets kept by the thermostat**: single or low/high, sent to each
  device on its own step and range.
- 🌡️ **Room temperature sensor**: one reference for the room, also written
  to devices with an external temperature input (TRV…).
- ↕️ **Offset per mode**: for a device that reads warmer or colder than the
  room.
- 🌀 **Fan and swing remembered per mode**, or shared between the modes you
  choose.
- 🎮 **The remote control wins**: a change made on a device (remote, app)
  is adopted, not overridden.
- 🛡️ **Robust**: what a device offers is remembered while it is unavailable
  and across restarts, and lost commands are sent again.
- 🩺 **Monitoring**: two problem sensors and an event to get notified.

## 💡 Example

A living room with a radiator and a split AC gives `climate.living_room`:

| Mode | Device |
|---|---|
| 🔥 Heat | `climate.radiator` |
| ❄️ Cool | `climate.air_conditioner` |
| 🌗 Heat/cool | the radiator or the AC, from the room temperature |
| 💧 Dry | `climate.air_conditioner` |

## 📦 Installation

### HACS

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marsoupilami25&repository=adaptative-climate&category=integration)

1. In HACS, open ⋮ → **Custom repositories** and add
   `https://github.com/marsoupilami25/adaptative-climate` as an
   **Integration**.
2. Download **Adaptative Climate**, then restart Home Assistant.

### Manual

Copy `custom_components/adaptative_climate` into the `custom_components`
folder of your configuration, then restart Home Assistant.

> [!NOTE]
> Requires Home Assistant 2026.6 or later.

## ⚙️ Configuration

### 🖱️ From the UI

[![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=adaptative_climate)

**Settings → Devices & services → Add integration → Adaptative Climate.**
Pick a device for each mode you want. Everything else is optional and can
be changed later with **Configure**.

### 📝 In YAML

```yaml
adaptative_climate:
  - name: Living room
    heat_entity: climate.radiator
    cool_entity: climate.air_conditioner
    dry_entity: climate.air_conditioner
    temperature_sensor: sensor.living_room_temperature
```

Entries are imported at startup and identified by their `name`. YAML wins:
a changed entry is updated, a removed one is deleted, and imported entries
have no options in the UI.

### 🔧 Options

| | Option | Default | Description |
|---|---|---|---|
| 🔀 | `heat_entity`, `cool_entity`, `heat_cool_entity`, `auto_entity`, `dry_entity`, `fan_only_entity` | | Device of each mode, at least one. With heat and cool but no `heat_cool_entity`, heat/cool uses both devices. |
| 🌡️ | `temperature_sensor` | | Room temperature. Without it, the readings of the devices are used. |
| ↕️ | `<mode>_offset` | 0 | How much warmer than the room the device of that mode reads (−10 to 10). |
| 📡 | `<mode>_external_sensor` | | `number` or `input_number` that receives the room temperature. Needs `temperature_sensor`. |
| 🌗 | `phase_hysteresis` | 1 °C | Heat/cool on two devices: margin beyond a target before switching between heating and cooling. |
| 🎯 | `min_temp`, `max_temp` | | Narrow the range of the devices. |
| 🎯 | `min_gap` | 1 °C | Smallest gap between the low and high targets. |
| 🌀 | `sync_modes` | | Modes that share their fan and swing settings. |
| 🌀 | `bi_source_sync` | off | Heat/cool on two devices: both share their fan and swing settings. |
| 🩺 | `monitoring_gap` | 2 °C | Largest temperature gap before it is a problem. |
| 🩺 | `monitoring_delay_timer` | 900 s | How long a problem lasts before it is reported. |

<details>
<summary>⏱️ Advanced timers</summary>

| Option | Default | Description |
|---|---|---|
| `settle_timer` | 12 s | After a device enters a mode, how long the values it shows are ignored. |
| `request_confirmation_timer` | 30 s | How long a device has to show the state asked. |
| `request_retry_timer` | 300 s | When the state asked is sent again. |
| `removal_confirmation_timer` | 60 s | How long a capability no longer shown by a device is kept. |
| `external_sensor_resend_timer` | 900 s | How often the room temperature is written again to the external sensors. |

</details>

## 🧩 Entities

| Entity | Description |
|---|---|
| 🌡️ `climate.<name>` | The thermostat. |
| 🔌 `binary_sensor.<name>_monitoring_sources` | On when a device does not respond or does not obey. |
| 📊 `binary_sensor.<name>_monitoring_temperatures` | On when the temperatures disagree (room sensor and devices). Set the offsets or check the sensor. |

Useful attributes of the thermostat:

- `active_entity_id`: the device running now.
- `phase`: `heat` or `cool`, for heat/cool on two devices.
- `unavailable_modes`: the modes that cannot be used now.
- `saved_targets`: the targets kept, also those the current mode does not
  show.

## 🔔 Notifications

Each problem fires an `adaptative_climate_problem` event when it starts and
when it ends:

```yaml
automation:
  - triggers:
      - trigger: event
        event_type: adaptative_climate_problem
        event_data:
          status: started
    actions:
      - action: notify.notify
        data:
          title: "{{ trigger.event.data.name }}"
          message: "{{ trigger.event.data.message }}"
```

## 📚 Documentation

- 📘 [Specification](documents/SPEC.md): the full behavior.
- 🏗️ [Architecture](documents/ARCHITECTURE.md)
- 🧪 [Tests](documents/TESTS.md), and how to run them in
  [dev/README.md](dev/README.md).

## 📄 License

[MIT](LICENSE)
