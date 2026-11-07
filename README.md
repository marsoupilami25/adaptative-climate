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
    sync_modes: [cool, dry]   # optional, see "Fan and swing settings"
    max_temp: 23   # optional, see "Temperature range"
```

Each YAML entry is imported as a config entry when Home Assistant starts.
The name identifies the entry, so it must be unique. YAML wins over the UI:
a changed entry is updated, an entry removed from YAML is deleted, and
imported entries have no options in the UI. Entries created from the UI
are not affected.

The integration creates one `climate` entity. Each of its modes (heat, cool,
auto, dry, fan only) uses a source `climate` entity, set in the configuration.
The same source can serve several modes. A mode without a source is not shown.

Switching to a mode sets its source to the HVAC mode of the same name, after
turning off the source of the previous mode when it is a different entity.
The `heat_cool` mode is not supported yet.

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

### Temperature range

The minimum and maximum temperatures follow the sources: those of the
source of the current mode, or the widest range of the sources when the
entity is off. A radiator at 5-30 °C and an AC at 16-32 °C give 5-30 °C
in heat mode and 16-32 °C in cool mode.

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
