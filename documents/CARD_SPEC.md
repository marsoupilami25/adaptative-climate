# Adaptative Climate card — Specification

Conventions:

- Rules are named `CARD-<SECTION>-<n>`. A rule is what the card **must** do.
- A rule states a requirement in one or two sentences. Its rationale, when
  useful, follows it in a **Why** block. The rule is complete without it.
- Words of the integration keep the meaning of its
  [glossary](SPEC.md#0-glossary). The card adds its own terms (§0).
- What is defined elsewhere is not repeated here: a link points to it.
- Mock-ups are wireframes. They fix where each part is and what it shows,
  not the exact drawing. The drawing follows Home Assistant
  ([CARD-LOOK-3](#card-look-3)).

## Table of contents

- [0. Terms](#0-terms)
- [1. General](#1-general)
- [2. Layout and look](#2-layout-and-look)
- [3. Phase](#3-phase)
- [4. Device line](#4-device-line)
- [5. Features](#5-features)
  - [5.1 Mode bar](#51-mode-bar)
  - [5.2 Lists](#52-lists)
- [6. Monitoring](#6-monitoring)
- [7. Missing data](#7-missing-data)
- [8. Configuration](#8-configuration)
- [9. Languages](#9-languages)

## 0. Terms

| Term | Meaning |
|---|---|
| **Card** | This dashboard card. It shows one [AC entity](SPEC.md#0-glossary). |
| **Thermostat card** | The thermostat card of Home Assistant. The card is built on it. |
| **Header** | The top of the card: title, monitoring indicators, ⋮ button. |
| **Feature** | A row under the dial, chosen and ordered in the configuration ([§8](#8-configuration)): the device line, the mode bar or a list. |
| **Dial** | The round control of the card: the arc, its handles, and the numbers in its center. |
| **Handle** | A point of the dial the user drags to set a target. With two targets, the **low handle** sets low and the **high handle** sets high. |
| **Monitoring sensors** | The two [monitoring sensors](SPEC.md#41-monitoring-sensors) of the entry of the AC entity. |

## 1. General

The integration provides the card ([ENT-CARD-1](SPEC.md#ent-card-1)).

- **CARD-GEN-1**<a id="card-gen-1"></a> The card shows an AC entity only.
  Another entity gives an error message in the card.
- **CARD-GEN-2**<a id="card-gen-2"></a> When the entity does not exist, the
  card says so.
- **CARD-GEN-3**<a id="card-gen-3"></a> The card needs Home Assistant 2026.6
  or later ([ENT-HA-3](SPEC.md#ent-ha-3)).
- **CARD-GEN-4**<a id="card-gen-4"></a> The card bases what it shows and
  how it reacts on the state of the AC entity, of its monitoring sensors and
  of its source entities. It does not duplicate the logic of the integration.

  > **Why:** the entity is the model, the card the view and the controller.
  > The card stays valid when the integration changes.

- **CARD-GEN-5**<a id="card-gen-5"></a> Each user action calls a standard
  service of the AC entity: `climate.set_hvac_mode`,
  `climate.set_temperature`, `climate.set_preset_mode`,
  `climate.set_fan_mode`, `climate.set_swing_mode` or
  `climate.set_swing_horizontal_mode`.

## 2. Layout and look

A mono-source `heat`, with a radiator, and all the features, in the order
the editor proposes them ([CARD-CONF-4](#card-conf-4)). Lowercase is a mode not
selected, capitals the selected one. `*` is the icon of the current mode,
`◇` the icon of a list.

```text
┌────────────────────────────────────────────┐
│ (✓) (✓)          Living room             ⋮ │  ① header
├────────────────────────────────────────────┤
│                 ╭─────────╮                │
│            ╭────╯ Heating ╰────╮           │
│            │      21.5 °C      │           │  ② dial
│            │     ⌂ 20.3 °C     │           │
│            ╰──╮  (−)    (+)  ╭─╯           │
│               ╰──────────○───╯             │
├────────────────────────────────────────────┤
│          * Radiator living room            │  ③ features: ac-device
│  off │ HEAT │ cool │ h/c │ auto │ dry      │     ac-hvac-modes
│  ◇ Eco            ▾ │  ◇ Auto           ▾  │     ac-preset-modes, ac-fan-modes
│  ◇ Off            ▾ │  ◇ Off            ▾  │     ac-swing-modes, ac-swing-horizontal-modes
└────────────────────────────────────────────┘
```

- **CARD-LOOK-1**<a id="card-look-1"></a> From top to bottom, the card shows
  the header, the dial, then the features in the order of the configuration.
- **CARD-LOOK-2**<a id="card-look-2"></a> The device line keeps its height
  when it is empty. Another feature with nothing to show takes no space.

  > **Why:** the dial does not jump when a device starts or stops.

- **CARD-LOOK-3**<a id="card-look-3"></a> The card uses the colors, fonts
  and icons of the Home Assistant theme, light and dark. A mode has the
  color and the icon Home Assistant gives it.
- **CARD-LOOK-4**<a id="card-look-4"></a> List features in `dropdown` style
  that follow each other form a **group**.
- **CARD-LOOK-5**<a id="card-look-5"></a> When the card has room in height,
  each list of a group takes a full row.
- **CARD-LOOK-6**<a id="card-look-6"></a> When it has not, or when its height
  is automatic, a group is packed two per row:

  | Lists in the group | Rows |
  |---|---|
  | 1 | one row with 1 list |
  | 2 | one row with 2 lists |
  | 3 | a row with 1 list, then a row with 2 lists |
  | 4 | two rows with 2 lists each |

  > **Why:** the dial keeps its size in a small card.

- **CARD-LOOK-7**<a id="card-look-7"></a> When the card is too narrow for two
  lists side by side, each list takes a full row, whatever the height.

- **CARD-DIAL-1**<a id="card-dial-1"></a> The header and the dial look and
  work as on the thermostat card: title, dial, and ⋮ button that opens the
  details of the entity. This spec only says what differs.

  > **Why:** users already know them.

- **CARD-DIAL-2**<a id="card-dial-2"></a> In a mode without a target (for
  example `fan_only`), the state in the center of the dial is smaller than
  on the thermostat card, centered, and stays inside the circle.

  > **Why:** on the thermostat card, a long state ("Fan only" in French:
  > "Ventilation uniquement") fills the dial.

## 3. Phase

This section applies when the AC entity runs a
[bi-source](SPEC.md#0-glossary) `heat_cool`. The current phase is the
[`phase` attribute](SPEC.md#22-attributes-of-the-ac-entity).

The dial in phase `cool`. `●` is an inverted handle: its center in its
color, its ring white. `○` is a handle as on the thermostat card: its ring in
its color, its center white.

```text
                 ╭─────────────●─╮       ● high handle: inverted, cool color
            ╭────╯   Cooling     ╰────╮
            │    19 °C  ·  24 °C      │
            │   ⌂ 25.1 °C             │
            ╰──╮  (−)    (+)       ╭──╯
               ╰──○────────────────╯     ○ low handle: as on the thermostat card
```

- **CARD-PHASE-1**<a id="card-phase-1"></a> The handle of the current phase
  is inverted: its center has the color of the phase, its ring is white. It is
  the low handle for `heat`, the high handle for `cool`.

  > **Why:** the two targets drive two devices. The user sees at a glance
  > which one runs.

- **CARD-PHASE-2**<a id="card-phase-2"></a> The handle of the other phase
  looks as on the thermostat card.
- **CARD-PHASE-3**<a id="card-phase-3"></a> When `phase` is `None`, no handle
  is inverted.

The phase changes nothing else: the user sets both targets as on the
thermostat card. The integration decides what to do with them.

## 4. Device line

The device line is the feature `ac-device`. It names the device that runs. A device is named by the name
of its source entity.

`*` is the icon of the current mode, `§` the status icon.

```text
normal       │          * Radiator living room            │
unavailable  │          * Radiator living room §          │  error color, § = sync alert
off          │                                            │  empty, same height
foreign      │          * Radiator living room §          │  warning color, § = remote control
                                               └─ tooltip: "Air conditioner runs dry · not managed"
```

- **CARD-DEV-1**<a id="card-dev-1"></a> The device line shows the icon of
  the current mode, then the name of the device of the
  [active source](SPEC.md#0-glossary) (`active_entity_id`).
- **CARD-DEV-2**<a id="card-dev-2"></a> The device line stays on one line. A
  name too long for it ends with an ellipsis.
- **CARD-DEV-3**<a id="card-dev-3"></a> The line ends with a status icon
  when something needs attention. The name and the status icon take its
  color. The mode icon keeps the color of the mode.

  | Reason | Status icon | Color |
  |---|---|---|
  | The source entity of the active source is `unavailable`. | sync alert (`mdi:sync-alert`), as for the sources in the monitoring ([CARD-MON-3](#card-mon-3)) | error (`--error-color`, red) |
  | A device runs a [foreign](SPEC.md#0-glossary) mode (`foreign_modes`). | remote control (`mdi:remote`) | warning (`--warning-color`, amber) |

  > **Why:** red when the current mode cannot run, amber when a device runs
  > outside the integration ([ENT-STATE-5](SPEC.md#1321-state-machine)).
  > Red matches the monitoring indicators ([§6](#6-monitoring)).

- **CARD-DEV-4**<a id="card-dev-4"></a> When both reasons hold, the line
  shows the unavailable one.
- **CARD-DEV-5**<a id="card-dev-5"></a> The tooltip of the status icon gives
  each reason on its own line: "<device> unavailable", or "<device> runs
  <mode> · not managed".
- **CARD-DEV-6**<a id="card-dev-6"></a> Pressing the status icon shows the
  same text.

  > **Why:** a touch screen has no tooltip.

- **CARD-DEV-7**<a id="card-dev-7"></a> Without an active source, the line
  shows only the status icon, when there is a reason for it.

## 5. Features

The features of the card replace those of the thermostat card. The device
line is in [§4](#4-device-line).

### 5.1 Mode bar

The mode bar is the feature `ac-hvac-modes`.

Capitals: the current mode. `( )`: a mode in `unavailable_modes`.

```text
┌──────┬──────┬──────┬──────┬──────┬──────┐
│ off  │ HEAT │ cool │ h/c  │(auto)│ dry  │
└──────┴──────┴──────┴──────┴──────┴──────┘
          └─ tooltip: "Heat · Radiator living room"
```

- **CARD-MODE-1**<a id="card-mode-1"></a> The mode bar has one button per
  mode, with the icon of the mode. Pressing a button sets that mode.
- **CARD-MODE-2**<a id="card-mode-2"></a> The modes are those of the
  `hvac_modes` option of the feature, in its order. Without it, they are
  those of the `hvac_modes` attribute, in its order. A mode the AC entity
  does not list is not shown.
- **CARD-MODE-3**<a id="card-mode-3"></a> The button of the current mode is
  filled with the color of the mode.
- **CARD-MODE-4**<a id="card-mode-4"></a> The button of a mode in
  `unavailable_modes` is greyed out. Pressing it does not ask for the mode: a
  bubble says that the device of the mode is not available.

  > **Why:** the entity tells that it would refuse the mode
  > ([ENT-STATE-4](SPEC.md#1321-state-machine)). The bubble says why, where a
  > refused request would only leave an error in the logs.

- **CARD-MODE-5**<a id="card-mode-5"></a> The tooltip of a mode button gives
  the mode and its device (`mode_entity_ids`). For a bi-source `heat_cool`,
  it gives both phase devices.

### 5.2 Lists

The lists are the features `ac-preset-modes`, `ac-fan-modes`,
`ac-swing-modes` and `ac-swing-horizontal-modes`.

In `dropdown` style, a closed list, then an open one. `◇` is the icon of the
list:

```text
┌──────────────────────┐     ┌──────────────────────┐
│  ◇ Auto            ▾ │     │  ◇ Auto            ▴ │
└──────────────────────┘     ├──────────────────────┤
                             │  ✓ Auto              │
                             │    Low               │
                             │    Medium            │
                             │    High              │
                             └──────────────────────┘
```

In `icons` style:

```text
┌──────┬──────┬──────┬──────┐
│ AUTO │ low  │ med. │ high │
└──────┴──────┴──────┴──────┘
```

- **CARD-LIST-1**<a id="card-list-1"></a> A list shows when the AC entity
  declares its setting ([ENT-FAN-2](SPEC.md#1346-fan-and-swing)). It is
  greyed out when the current mode offers no option for it.

  > **Why:** the entity keeps the setting in every mode once discovered. The
  > card keeps the same size from one mode to another.

- **CARD-LIST-2**<a id="card-list-2"></a> In `dropdown` style, a closed list
  shows the icon of the list and the current value. Its name is in its
  tooltip.
- **CARD-LIST-3**<a id="card-list-3"></a> In `dropdown` style, pressing a list
  opens its options, in the order of the AC entity, the current one checked.
  Choosing an option sets it.
- **CARD-LIST-4**<a id="card-list-4"></a> In `icons` style, a list is a bar
  with one button per option, in the order of the AC entity. The button of
  the current value is filled. Pressing a button sets that option.
- **CARD-LIST-5**<a id="card-list-5"></a> A greyed list
  ([CARD-LIST-1](#card-list-1)) is faded, as a mode not available
  ([CARD-MODE-4](#card-mode-4)). It shows:
  - the "off" icon of the list when it has one (`fan-off` for the fan,
    `arrow-oscillating-off` for the swings), else its icon;
  - "—" as value, and no arrow: it does not open;
  - in its tooltip, that the current mode does not offer it.
- **CARD-LIST-6**<a id="card-list-6"></a> The icon of a value is the one Home
  Assistant gives to that value for a climate entity. The match ignores the
  case, and knows common synonyms ("quiet", "turbo", "max"...) and numbers
  ("1", "level 2"...).
- **CARD-LIST-7**<a id="card-list-7"></a> A value without an icon shows its
  label only. In `icons` style, when a value has no icon, the whole bar
  shows the labels.

  > **Why:** devices name their values their own way. A bar of identical
  > icons cannot be read.

## 6. Monitoring

The header shows the [monitoring sensors](#0-terms) on its left. `✓` is an
indicator in green, `!` and `T` in red, `●` the dot of `compact`.

```text
always       │ (✓) (✓)          Living room            ⋮ │  no problem
             │ (!) (✓)          Living room            ⋮ │  the devices have a problem
compact      │ ●                Living room            ⋮ │  green, or red with a problem
errors       │ (T)              Living room            ⋮ │  only the temperatures have a problem
hidden       │                  Living room            ⋮ │
```

- **CARD-MON-1**<a id="card-mon-1"></a> The `monitoring` option sets what
  the header shows:

  | Value | Shows |
  |---|---|
  | `always` | one indicator per monitoring sensor, always |
  | `compact` | one dot for both sensors |
  | `errors` | one indicator per sensor that is on, from the left |
  | `hidden` | nothing |

  > **Why:** `always` tells that the monitoring works. `compact` and
  > `errors` save room on a narrow card.

- **CARD-MON-2**<a id="card-mon-2"></a> An indicator is green when its
  sensor is off, red when it is on.
- **CARD-MON-3**<a id="card-mon-3"></a> Each sensor has its own icons:

  | Sensor | Off | On |
  |---|---|---|
  | sources | two arrows in a circle (`sync`) | the same, with an alert (`sync-alert`) |
  | temperatures | thermometer with a check (`thermometer-check`) | thermometer with an alert (`thermometer-alert`) |

- **CARD-MON-4**<a id="card-mon-4"></a> The dot of `compact` is green when
  both sensors are off, red when one is on. Its tooltip names the problems.
- **CARD-MON-5**<a id="card-mon-5"></a> Pressing an indicator opens the
  details of its sensor in Home Assistant. Pressing the dot opens the sensor
  that is on, the sources first, else the sources.

  > **Why:** the `problems` attribute of the sensor says what is wrong
  > ([MON-SENS-2](SPEC.md#41-monitoring-sensors)).

## 7. Missing data

The AC entity `unavailable`, with a sources problem:

```text
┌────────────────────────────────────────────┐
│ (!)              Living room             ⋮ │  indicator still shown
├────────────────────────────────────────────┤
│        dial as on the thermostat card      │
│                "Unavailable"               │
├────────────────────────────────────────────┤
│                                            │  device line empty
├────────────────────────────────────────────┤
│  off │ heat │ cool │ h/c │ auto │ dry      │  greyed
└────────────────────────────────────────────┘
```

- **CARD-MISS-1**<a id="card-miss-1"></a> When the AC entity is
  `unavailable`, the dial looks as on the thermostat card, and the mode bar
  is greyed out. The monitoring indicators still show.

  > **Why:** the monitoring sensors stay available
  > ([MON-SENS-4](SPEC.md#41-monitoring-sensors)) and say why.

- **CARD-MISS-2**<a id="card-miss-2"></a> When an attribute is missing or
  `None`, what it feeds is not shown.

## 8. Configuration

- **CARD-CONF-1**<a id="card-conf-1"></a> The card has these options:

  | Option | Required | Default | Meaning |
  |---|---|---|---|
  | `entity` | yes | | The AC entity. |
  | `name` | no | the name of the entity | The title. |
  | `show_current_as_primary` | no | `false` | As on the thermostat card: the current temperature in large, the target below. |
  | `monitoring` | no | `always` | What the header shows of the monitoring: `always`, `compact`, `errors` or `hidden` ([§6](#6-monitoring)). |
  | `features` | no | none | The features, in their order. |

- **CARD-CONF-2**<a id="card-conf-2"></a> A feature is given by its `type`,
  with these options:

  | `type` | Option | Default | Meaning |
  |---|---|---|---|
  | `ac-device` | | | The device line ([§4](#4-device-line)). |
  | `ac-hvac-modes` | `hvac_modes` | all, in the order of the AC entity | The modes shown, in their order ([§5.1](#51-mode-bar)). |
  | `ac-preset-modes`, `ac-fan-modes`, `ac-swing-modes`, `ac-swing-horizontal-modes` | `style` | `dropdown` | `dropdown` or `icons` ([§5.2](#52-lists)). |

- **CARD-CONF-3**<a id="card-conf-3"></a> The card is listed in "Add card".
  It starts with the first AC entity found, and no feature, as the thermostat
  card.
- **CARD-CONF-4**<a id="card-conf-4"></a> A visual editor sets every option.
  It adds, removes and orders the features, and sets their options, as for
  the thermostat card. It proposes the features in this order: `ac-device`,
  `ac-hvac-modes`, `ac-preset-modes`, `ac-fan-modes`, `ac-swing-modes`,
  `ac-swing-horizontal-modes`. Each feature can be added once.
- **CARD-CONF-5**<a id="card-conf-5"></a> The editor and the YAML give the
  same configuration.
- **CARD-CONF-6**<a id="card-conf-6"></a> An option with a wrong value gives
  an error message in the card.

## 9. Languages

- **CARD-LANG-1**<a id="card-lang-1"></a> The card uses the language of the
  Home Assistant user.
- **CARD-LANG-2**<a id="card-lang-2"></a> The texts of the card exist in
  English and French. Other languages get English.
- **CARD-LANG-3**<a id="card-lang-3"></a> Modes, actions and options use the
  texts of Home Assistant and of the integration.
