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
    min_temp: 7    # optional, default 7
    max_temp: 35   # optional, default 35
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

Fan, swing and horizontal swing come from the source of the current mode:
they are shown when that source has them, in any mode, and changes are sent
to it. A heat pump used for heating keeps its fan; a radiator shows none.
When the entity is off, none of them is shown.

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
