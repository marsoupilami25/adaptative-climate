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

The integration creates one `climate` entity. Each of its modes (heat, cool,
auto, dry, fan only) uses a source `climate` entity, set in the configuration.
The same source can serve several modes. A mode without a source is not shown.

Switching to a mode sets its source to the HVAC mode of the same name, after
turning off the source of the previous mode when it is a different entity.
The `heat_cool` mode is not supported yet.

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
