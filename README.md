# Adaptative Climate

Home Assistant custom integration for adaptative climate entities.

## Structure

```text
custom_components/
  adaptative_climate/
    __init__.py
    binary_sensor.py
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
    heat_offset: 2   # optional, see "Temperature offset"
    heat_external_sensor: number.heater_external_temperature   # optional, see "External sensor"
    cool_entity: climate.air_conditioner
    dry_entity: climate.air_conditioner
    temperature_sensor: sensor.living_room_temperature   # optional, see "Heat/cool mode"
    sync_modes: [cool, dry]   # optional, see "Fan and swing settings"
    max_temp: 23   # optional, see "Temperature range"
    min_gap: 2   # optional, see "Target temperature"
    min_phase_duration: 10   # optional, minutes, see "Heat/cool mode"
    monitoring_gap: 2   # optional, see "Monitoring"
    monitoring_duration: 15   # optional, minutes, see "Monitoring"
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

A source set elsewhere (remote, app) to a mode it does not serve here, such
as a heat source put in fan only, is ignored: the entity does not follow it
and the other sources keep running. It shows off when no other source runs.
The source and its mode appear in the `foreign_modes` attribute
(`{climate.pac: fan_only}`, empty otherwise) and a warning is logged, also at
startup. Turning the entity off, or switching it to a mode, still turns that
source off like any other.

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
| auto, source with low/high | none | heating setpoint | cooling setpoint |
| auto, other source | single target (none if its source has none) | none | none |
| dry | single target (none if its source has none) | none | none |
| fan only | none | none | none |

So the target of heat is the low target of heat/cool, and the one of cool is
the high target: going from heat to heat/cool reuses it. Auto works like
heat/cool when its source has low/high targets (even if it also has a single
target), with the same heating and cooling setpoints. Otherwise, auto and dry
share a single target of their own, when their source has a target
temperature. Fan only has no target, and neither have dry and auto on a
source without one (a dehumidifier without thermostat): the source gets no
target, a target changed on it is ignored, and a target set in that mode is
kept for the next one. While off, the entity shows both setpoints (low and
high) so they can be set before turning on; a single
`temperature` set then goes to the mode `turn_on` goes to.

The targets belong to the entity, not to the sources: switching mode keeps
them, and a source turned on elsewhere (remote control, app) gets its own
setpoint too. It is sent once the source shows its new mode, so a device
that first shows its own target for that mode gets the entity target instead.

The low target stays at least `min_gap` below the high one (1 degree at
least, also the default). Setting one moves the other: a heating setpoint
raised near the cooling one pushes it up, a cooling setpoint lowered near
the heating one pulls it down. In a `target_temp_low`/`target_temp_high`
call, the high target moves. When the source of the other target cannot
follow (range), the target just set gives way. A change made on a source has
the upper hand: it is kept, and only the other target moves.

Each source gets the target plus its offset (see "Temperature offset"),
rounded to its step and kept in its range (and in the `min_temp`/`max_temp`
limits). A setpoint that only goes to one
source (see "Heat/cool mode") is kept as that source gets it: a high target
of 14 °C for an AC whose minimum is 16 °C is 16 °C, also to decide when to
switch to it. When auto sends low/high to another source than heat/cool,
they go to two sources and are kept as they were given, like the single
target of the other modes.
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
set while off, in fan only, or in a mode whose source has none, is kept for
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
- A source started by the mode runs at least `min_phase_duration` minutes
  (10 by default, 0 to switch at once) before the mode switches to the other
  one, so close targets do not make short cycles. New targets set by the
  user switch at once.

A heat pump set as both heat and cool source switches its own mode. Fan and
swing settings are those remembered for heat and for cool. The mode needs
both sources: it is refused when one of them is unavailable or does not
offer its mode.

The room temperature comes from `temperature_sensor` when set (converted to
the unit of Home Assistant), else from the source in use. The entity shows
it in every mode.

Without `temperature_sensor`, the heat/cool mode follows the room
temperatures of both sources, which may not agree (each one reads near its
own device: warm near the heater, cool near the AC). It switches only when
both are below the low target, or both above the high one; when they
contradict each other, the running source is kept. A source without room
temperature leaves the other one to decide. When entering the mode, their
mean picks the closest target.

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

### Temperature offset

A source regulates with its own sensor, which may not read the room
temperature: a radiator reads warmer near itself. Each mode can have a
temperature offset (`heat_offset`, `cool_offset`, `heat_cool_offset`,
`auto_offset`, `dry_offset`, `fan_only_offset`, 0 by default, -10 to 10):
how much warmer than the room its source reads (negative: colder).

The targets of the entity are those of the room. The source gets the
target plus its offset: with `heat_offset: 2`, a target of 21 °C sends
23 °C to the heater. What the entity reads from the source is minus the
offset: the target it shows (22 °C when the heater is set to 24 °C on its
remote, which becomes the target of the entity, without being sent back),
the first targets, the room temperature when there is no
`temperature_sensor`, and the readings the heat/cool mode follows.

The offset belongs to the mode, not to the source: an AC serving cool and
dry can have an offset in cool only. Low/high targets get the offset of
their mode too.

The range of the entity is the range of the source minus its offset (a
heater at 5-30 °C with `heat_offset: 2` gives 3-28 °C). `min_temp` and
`max_temp` limit the target of the entity, before the offset: with
`max_temp: 25`, the heater can get 27 °C.

### External sensor

Some sources can regulate with an external temperature: a thermostatic
valve with an "external temperature" number entity, a thermostat
following a probe. Each mode can name that entity
(`heat_external_sensor`, `cool_external_sensor`... a `number` or an
`input_number`): it gets the temperature of `temperature_sensor`, which is
then required, so the source regulates with the room temperature. The
offset of that mode is ignored.

A new room temperature is written at once, then at most once a minute
(a change in the meantime waits, and the latest value is written): fine
for battery devices. The value is written again every 30 minutes, even
unchanged, since some devices forget it, and when Home Assistant starts.
It is converted to the unit of the target and rounded to its step.
Nothing is written while the room sensor is unavailable, to a target that
is unavailable, or out of the range of the target (logged as a warning).

### Monitoring

A source that does not read the room temperature keeps the room away from
the target. The integration creates a problem binary sensor
(`binary_sensor.<name>_monitoring`) that turns on when readings disagree:

- the room `temperature_sensor` and what a source reads,
- two sources (different entities) with each other.

Each reading is minus the offset of its mode (see "Temperature offset"): a
well set offset turns the problem off. An entity serving several modes
with the same offset is one reading; with different offsets, one reading
per offset, never compared together. A source that is unavailable or
reads no temperature is left out.

A gap is a problem when it is above `monitoring_gap` (2 degrees by
default) for `monitoring_duration` minutes (15 by default, 0: at once). A
gap that goes away starts from zero when it comes back, and after a
restart. The sensor is created only when there is something to compare: a
`temperature_sensor`, or at least two different source entities.

Its attributes are `max_gap` and `problems`, one per gap:

```yaml
problems:
  - type: sensor            # room sensor against a source
    gap: 3.5
    sensor_temperature: 23.0
    sources:
      - entity_id: climate.heater
        modes: [heat]
        temperature: 19.5   # minus the offset
  - type: sources           # two sources against each other
    gap: 4.5
    sources: [...]
```

A problem is logged once when it starts, as a warning, for example
`Living room: temperatures disagree for 15 min, above 2.0: climate.heater
(heat) reads 19.5, the room sensor 23.5: gap 4.0`, and at info level when
it ends (`temperatures agree again`).

To show it next to the thermostat card, use a dashboard badge, a tile
card, or a conditional card on `state: "on"`.

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
