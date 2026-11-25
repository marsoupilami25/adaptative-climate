<p align="center">
  <img src="custom_components/adaptative_climate/brand/icon.png" alt="Adaptative Climate" width="128">
</p>

<h1 align="center">Adaptative Climate</h1>

<p align="center">
  <strong>One thermostat per room, whatever devices heat, cool or dry it.</strong>
</p>

<p align="center">
  <a href="https://github.com/marsoupilami25/adaptative-climate/releases/latest"><img src="https://img.shields.io/github/v/release/marsoupilami25/adaptative-climate?sort=semver&include_prereleases&label=version" alt="Version"></a>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.6%2B-41BDF5.svg?logo=homeassistant&logoColor=white" alt="Home Assistant 2026.6+">
  <a href="https://github.com/marsoupilami25/adaptative-climate/actions/workflows/tests.yml"><img src="https://github.com/marsoupilami25/adaptative-climate/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/marsoupilami25/adaptative-climate/actions/workflows/validate.yml"><img src="https://github.com/marsoupilami25/adaptative-climate/actions/workflows/validate.yml/badge.svg" alt="Validate"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"></a>
</p>

> [!WARNING]
> **Work in progress: not usable yet.** Adaptative Climate is under
> development. Its behavior and its configuration still change, with no
> migration from one version to the next. Do not install it on a Home
> Assistant you rely on.

Adaptative Climate combines your `climate` entities (radiator, heat pump,
air conditioner, dehumidifier…) into a single thermostat. Each mode runs on
its own device: pick a mode, the right device starts and the others stop.
Targets, fan and swing follow you from one device to the other. A dashboard
card, installed with it, shows what the thermostat does.

## Features

### Integration

- **One thermostat, several devices**: heat, cool, heat/cool, auto, dry
  and fan only, each on its own device. Only one runs at a time.
- **Heat/cool from two devices**: a heater and an AC make one heat/cool
  mode. It heats below the low target and cools above the high one.
- **Targets kept by the thermostat**: one target, or a low and a high
  one, sent to each device as it accepts them (its limits, its steps).
- **Room temperature sensor**: one reference for the room, also written
  to devices with an external temperature input (TRV…).
- **A correction per device**: for a device that reads warmer or colder
  than the room.
- **Fan and swing remembered per mode**, or shared between the modes you
  choose.
- **The remote control wins**: a change made on a device (remote, app)
  is adopted, not overridden.
- **Robust**: what a device offers is remembered while it is unavailable
  and across restarts, and lost commands are sent again.
- **Problems detected**: a device that does not respond or does not obey,
  temperatures that disagree. Two sensors show them, and an event lets you
  get notified.

### Dashboard card

The thermostat card of Home Assistant, with what Adaptative Climate knows:

- **The dial you know**: title, current temperature, targets, − and +
  buttons, ⋮ for the details, as on the thermostat card.
- **Heating or cooling, at a glance**: in heat/cool with a heater and an
  AC, the dial shows which target is in use. The marker of the low target
  fills with orange while the heater runs, the marker of the high target
  with blue while the AC runs.
- **The device that runs**, named under the dial, with a status icon when
  it needs attention:
  - red: the device is unavailable;
  - amber: another device runs a mode the thermostat does not manage.

  Its tooltip, or a press on a touch screen, says why.
- **A mode bar**: the current mode filled with its color; the tooltip of
  a button gives the device of its mode. A mode whose device is unavailable
  is greyed out: a press explains why, instead of asking for the mode.
- **Preset, fan and swing lists**, as a dropdown or a bar of icons. Each
  list shows once the thermostat has that setting, greyed out in a mode
  that does not offer it. The values get the icons of Home Assistant, even
  when a device names them its own way (*Quiet*, *Turbo*, *Level 2*…).
- **Problems in the header**: one indicator per problem sensor, green
  or red; or a single dot; or only the problems. A press opens the sensor.
- **Any size**: in a small card, the lists share rows so the dial keeps
  its size; with room, each list takes a full row.
- **A visual editor** for every option, and a YAML that gives the same.
- **English and French**; modes and values in the language of Home
  Assistant.

## Installation

### HACS

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marsoupilami25&repository=adaptative-climate&category=integration)

1. In HACS, open ⋮ → **Custom repositories** and add
   `https://github.com/marsoupilami25/adaptative-climate` as an
   **Integration**.
2. Download **Adaptative Climate**, then restart Home Assistant.

HACS installs the latest [release](https://github.com/marsoupilami25/adaptative-climate/releases):
the integration and its card. Nothing else to install for the card.

### Manual

Download `adaptative_climate.zip` from the latest
[release](https://github.com/marsoupilami25/adaptative-climate/releases),
unzip it into `custom_components/adaptative_climate` in your configuration
folder, then restart Home Assistant. A copy of the repository is not enough:
the card is built for each release only.

> [!NOTE]
> Requires Home Assistant 2026.6 or later.

## Integration

### How it works

You create one Adaptative Climate thermostat per room, and tell it which of
your devices runs each mode. For a living room with a radiator and a split
AC:

| Mode | Device |
|---|---|
| Heat | the radiator |
| Cool | the AC |
| Heat/cool | the radiator below the low target, the AC above the high one |
| Dry | the AC |

Then you only use the thermostat of the living room. Pick *Heat*: the
radiator starts, the AC stops. Set 21 °C: the radiator gets 21 °C. Your
devices keep working as before: a change made with the remote of the AC is
followed by the thermostat.

### What you get

Each thermostat you create is a device in Home Assistant, with three
entities. An entity is what Home Assistant shows and controls: a
thermostat, a sensor, a switch…

| Entity | What it is |
|---|---|
| `climate.living_room` | **The thermostat.** Use it as any thermostat: in a dashboard (with [its card](#add-it-to-a-dashboard)), in automations, by voice. |
| `binary_sensor.living_room_monitoring_sources` | **A problem sensor**, on when a device does not respond or does not obey. |
| `binary_sensor.living_room_monitoring_temperatures` | **A problem sensor**, on when the temperatures disagree: the room sensor and the devices. Set the corrections of the devices, or check the sensor. |

The thermostat also gives, for automations and templates (its attributes):

- `active_entity_id`: the device running now;
- `phase`: in heat/cool with two devices, `heat` while the heating device
  runs, `cool` while the cooling one runs;
- `unavailable_modes`: the modes that cannot be used now, their device
  being unavailable;
- `saved_targets`: the targets it keeps, also those of the modes not in use.

### Get notified of a problem

When a problem starts, and when it ends, the integration also fires an
`adaptative_climate_problem` event. An automation can send it to your
phone:

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

### Set it up

#### From the UI

[![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=adaptative_climate)

**Settings → Devices & services → Add integration → Adaptative Climate.**
Give it a name, and pick a device for each mode you want. Everything else
is optional, and can be changed later with **Configure**.

#### In YAML

The same thermostat, in `configuration.yaml`:

```yaml
adaptative_climate:
  - name: Living room
    heat_entity: climate.radiator
    cool_entity: climate.air_conditioner
    dry_entity: climate.air_conditioner
    temperature_sensor: sensor.living_room_temperature
```

The thermostats in YAML are created at startup, and known by their `name`.
The YAML stays their reference: a thermostat changed in it is updated, one
removed from it is deleted, and they have no **Configure** in the UI.

### Options

The same options in the UI and in YAML. Only the devices are required.

| Option | Default | Description |
|---|---|---|
| `heat_entity`, `cool_entity`, `heat_cool_entity`, `auto_entity`, `dry_entity`, `fan_only_entity` | | Device of each mode, at least one. With heat and cool but no `heat_cool_entity`, heat/cool uses both devices. |
| `temperature_sensor` | | Room temperature. Without it, the readings of the devices are used. |
| `<mode>_offset` | 0 | How much warmer than the room the device of that mode reads (−10 to 10). |
| `<mode>_external_sensor` | | `number` or `input_number` that receives the room temperature. Needs `temperature_sensor`. |
| `phase_hysteresis` | 1 °C | Heat/cool on two devices: margin beyond a target before switching between heating and cooling. |
| `min_temp`, `max_temp` | | Narrow the range of the devices. |
| `min_gap` | 1 °C | Smallest gap between the low and high targets. |
| `sync_modes` | | Modes that share their fan and swing settings. |
| `bi_source_sync` | off | Heat/cool on two devices: both share their fan and swing settings. |
| `monitoring_gap` | 2 °C | Largest temperature gap before it is a problem. |
| `monitoring_delay_timer` | 900 s | How long a problem lasts before it is reported. |

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

## Dashboard card

A card made for these thermostats. It is installed with the integration:
nothing to add in HACS, nor in the resources of the dashboards. It shows an
Adaptative Climate thermostat only.

### Add it to a dashboard

1. Edit a dashboard, **Add card**, search **Adaptative Climate**.
2. The card starts on your first Adaptative Climate thermostat, with the
   dial only.
3. In its editor, choose the thermostat, and add the rows you want under
   the dial (below). Change their order, their style, or remove them, as
   for the features of the thermostat card.

**Show code editor** gives the same configuration in YAML.

### What it shows

At the top, the **header**: the title, the indicators of the two problem
sensors (green or red; a press opens the sensor), and ⋮ for the details of
the thermostat. Then the **dial**, as on the thermostat card.

Under the dial, the **rows you choose**, each one once:

| Row | `type` | What it shows |
|---|---|---|
| Device line | `ac-device` | The device that runs, with an icon when it needs attention: red when the device is unavailable, amber when another device runs a mode the thermostat does not manage. Its tooltip, or a press, says why. |
| Modes | `ac-hvac-modes` | One button per mode, the current one in its color. The tooltip of a button gives the device of its mode. A mode whose device is unavailable is greyed out. |
| Presets | `ac-preset-modes` | The presets of the thermostat, when it has some. |
| Fan | `ac-fan-modes` | The fan speeds. |
| Swing | `ac-swing-modes` | The vertical swing. |
| Horizontal swing | `ac-swing-horizontal-modes` | The horizontal swing. |

A preset, fan or swing row shows once the thermostat has that setting. It
is greyed out in a mode that does not offer it, so the card keeps its size
from one mode to the other.

### Example in YAML

```yaml
type: custom:adaptative-climate-card
entity: climate.living_room
monitoring: compact
features:
  - type: ac-device
  - type: ac-hvac-modes
    hvac_modes: [heat, cool, heat_cool, "off"]
  - type: ac-fan-modes
    style: icons
  - type: ac-swing-modes
```

### Options

| Option | Default | Description |
|---|---|---|
| `entity` | required | The Adaptative Climate thermostat, `climate.<name>`. |
| `name` | the name of the thermostat | The title. |
| `show_current_as_primary` | `false` | The current temperature in large, the target under it. |
| `monitoring` | `always` | What the header shows of the two problem sensors: `always` (one indicator per sensor, green or red), `compact` (one dot for both), `errors` (only the sensors with a problem), `hidden`. |
| `features` | none | The rows under the dial, in their order. |

The options of the rows:

| Row | Option | Default | Description |
|---|---|---|---|
| `ac-hvac-modes` | `hvac_modes` | every mode of the thermostat, in its order | The modes shown, in this order. |
| `ac-preset-modes`, `ac-fan-modes`, `ac-swing-modes`, `ac-swing-horizontal-modes` | `style` | `dropdown` | `dropdown`: a list that opens. `icons`: a bar with one button per value. |

All the details: [card specification](documents/CARD_SPEC.md).

## Documentation

- The integration: [specification](documents/SPEC.md) (the full
  behavior), [architecture](documents/ARCHITECTURE.md),
  [tests](documents/TESTS.md) (how to run them in
  [tests/integration/README.md](tests/integration/README.md)).
- The card: [specification](documents/CARD_SPEC.md),
  [architecture](documents/CARD_ARCHITECTURE.md), [tests](documents/CARD_TESTS.md)
  (how to run them in [tests/card/README.md](tests/card/README.md)).
- [Development](dev/README.md): the tools to install, the dev
  environment, the build of the card, the release.

## License

[MIT](LICENSE)
