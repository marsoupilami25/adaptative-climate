# Adaptative Climate

Home Assistant custom integration for adaptative climate entities.

## Structure

```text
custom_components/
  adaptative_climate/
    __init__.py
    climate.py
    config_flow.py
    const.py
    coordinator.py
    manifest.json
    strings.json
    translations/
      en.json
      fr.json
```

## Installation

Copy `custom_components/adaptative_climate` into the `custom_components`
directory of your Home Assistant configuration, then restart Home Assistant.

After restart, add the integration from:

```text
Settings > Devices & services > Add integration > Adaptative Climate
```

Or declare the entities in `configuration.yaml`:

```yaml
adaptative_climate:
  - name: Living room
    heat_entity: climate.heater
    cool_entity: climate.air_conditioner
    dry_entity: climate.air_conditioner
    temperature_sensor: sensor.living_room_temperature   # optional, see "Heat/cool mode"
    sync_modes: [cool, dry]   # optional, see "Fan and swing settings"
    max_temp: 23   # optional, see "Temperature range"
    min_gap: 2   # optional, see "Target temperature"
```

Each YAML entry is imported as a config entry when Home Assistant starts.
The name identifies the entry, so it must be unique. YAML wins over the UI:
a changed entry is updated, an entry removed from YAML is deleted, and
imported entries have no options in the UI. Entries created from the UI
are not affected.

The integration creates one `climate` entity. Each of its modes (heat, cool,
heat/cool, auto, dry, fan only) uses a source `climate` entity, set in the
configuration (`heat_cool_entity` for heat/cool). The same source can serve
several modes. A mode without a source is not shown, except heat/cool (see
"Heat/cool mode").

Switching to a mode sets its source to the HVAC mode of the same name, after
turning off the source of the previous mode when it is a different entity.

A source must offer the modes it serves. The configuration checks it, except
for a source that is still starting or unavailable, so it is checked again
whenever a source becomes usable. A mode its source does not offer stays
listed, appears in the `unavailable_modes` attribute (like a mode whose source
is unavailable) and raises a Repairs issue, removed once the source offers it.
Switching to that mode is refused before anything is turned off.

### Fan and swing settings

Fan, swing and horizontal swing come from the source of the current mode:
they are shown when that source has them, in any mode, with the options of
that source, and changes are sent to it. A heat pump used for heating keeps
its fan; a radiator shows none. When the entity is off, none of them is shown.

Each mode remembers its settings and sends them back to its source when the
entity switches to that mode, so a mode finds the settings it was left with.
A change made on the source itself (remote control, app) while the mode is
on is remembered too. The first time a mode is used, it keeps the settings
the source already has. The settings are kept across restarts.

`sync_modes` lists modes that share their settings: a fan speed chosen in
`cool` is used in `dry` too. A shared value must be offered by every
synchronized source that has the setting (a radiator without fan does not
count). A value only some of them offer, such as a `turbo` speed, can still
be chosen, but it is not remembered: the mode gets the shared value back
next time. Modes outside `sync_modes` keep their own settings. A listed mode
without a source is ignored.

Values are compared without case: `Low` on one source and `low` on another
are the same value, and each source receives it as it spells it. Other names
are not matched (`1` is not `low`).

### Target temperature

The entity keeps two setpoints, like the thermostats of Z-Wave and Matter:
a heating one (the low target) and a cooling one (the high target). They are
exposed according to the mode:

| Mode | `temperature` | `target_temp_low` | `target_temp_high` |
|---|---|---|---|
| heat | heating setpoint | none | none |
| cool | cooling setpoint | none | none |
| heat/cool | none | heating setpoint | cooling setpoint |
| auto, dry... | single target | none | none |

So the target of heat is the low target of heat/cool, and the one of cool is
the high target: going from heat to heat/cool reuses it. The other modes
(auto, dry) have a single target of their own. While off, the entity shows
both setpoints (low and high) so they can be set before turning on; a single
`temperature` set then goes to the mode `turn_on` goes to.

The targets belong to the entity, not to the sources: switching mode keeps
them, and a source turned on elsewhere (remote control, app) gets its own
setpoint too. It is sent once the source shows its new mode, so a device
that first shows its own target for that mode gets the entity target instead.

The low target stays at least `min_gap` below the high one (empty or 0: it
may equal it, not exceed it). Setting one moves the other: a heating setpoint
raised above the cooling one pulls it up, a cooling setpoint lowered below
the heating one pulls it down. In a `target_temp_low`/`target_temp_high`
call, the high target moves. When the source of the other target cannot
follow (range), the target just set gives way. A change made on a source is
not checked: the source has the upper hand.

Each source gets the target rounded to its step and kept in its range (and
in the `min_temp`/`max_temp` limits). A setpoint that only goes to one
source (see "Heat/cool mode") is kept as that source gets it: a high target
of 14 °C for an AC whose minimum is 16 °C is 16 °C, also to decide when to
switch to it. The single target of the other modes is kept as it was given.
The entity shows the target of the active source (except right after
entering a mode, see below).

A target changed on the active source (remote control, app) becomes the
target of the entity: the user took over from the source, which has the
upper hand, even outside the limits of the entity (they apply again to the
next mode).

Except right after the source enters a mode: some devices report their own
target for the new mode a few seconds after the mode itself. Until the
source shows the target sent to it, or for 12 seconds at most, the targets
it shows are ignored and the entity shows its own target. If the source
showed another target during those 12 seconds, it gets the entity target
again at their end; if it showed nothing, nothing is sent. Then the source
is followed. A source already at the target when entering
gets nothing, so nothing confirms it: its targets are ignored for the full
12 seconds (a change made on the remote control then is overridden).

While the entity is off, the targets of the sources are ignored. A target
set while off, or in a mode whose source has none (fan only), is kept for
the next mode. The targets are kept across restarts. The first heating
setpoint comes from the heat source, the cooling one from the cool source
(a `heat_cool_entity` with low/high targets comes first), else 1 degree
around the single target, which comes from a source, else the middle of
the range.

### Heat/cool mode

With a `heat_cool_entity`, the heat/cool mode works like the other modes: its
source gets the low/high targets (or the single target if it has no low/high
targets).

Without one, but with heat and cool sources, the heat/cool mode uses them:
it runs one of them at a time, chosen from the room temperature.

- Below the low target, the heat source heats to the low target.
- Above the high target, the cool source cools to the high target.
- In between, the running source is kept. When entering the mode, the source
  of the closest target starts. Without room temperature, the heat or cool
  source already running is kept, else heat starts.

A heat pump set as both heat and cool source switches its own mode. Fan and
swing settings are those remembered for heat and for cool. The mode needs
both sources: it is refused when one of them is unavailable or does not
offer its mode.

The room temperature comes from `temperature_sensor` when set (converted to
the unit of Home Assistant), else from the source in use. The entity shows
it in every mode.

The source has the upper hand: when a source is turned off or set to
another mode elsewhere (remote control, app), the entity leaves heat/cool
and follows the source. After switching source itself, the entity waits up
to 12 seconds for the source to show its new mode before judging it.

### Temperature range

The minimum and maximum temperatures follow the sources: those of the
source of the current mode, or the widest range of the sources when the
entity is off. A radiator at 5-30 °C and an AC at 16-32 °C give 5-30 °C
in heat mode and 16-32 °C in cool mode. The heat/cool mode using the heat
and cool sources has the widest range of both (5-32 °C); each target is
still limited to the range of the source it goes to.

`min_temp` and `max_temp` are optional limits, empty by default. They can
only narrow the range of the source, never widen it: `max_temp: 23` keeps
heating at 23 °C or below. A limit outside the range of the current source
is ignored. When a source gives no range, the Home Assistant defaults
(7-35 °C) apply.

## Development

Tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component),
which ships the Home Assistant core test helpers. They need Python 3.14.

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest --cov
```

When the entity state changes on purpose, update the snapshots and review
the diff in `tests/snapshots/`:

```bash
.venv/bin/pytest --snapshot-update
```

To test against a new Home Assistant release, bump
`pytest-homeassistant-custom-component` in `requirements_test.txt`.
