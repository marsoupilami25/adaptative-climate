# Manual tests

A Home Assistant configuration to test the integration by hand: virtual
`climate` sources, and one dashboard per test case, with its scenarios. Each
scenario cites the rules of the spec it shows.

```text
dev/manual/
  config/
    configuration.yaml             dev HA config, entities under test in YAML
    packages/sources_<case>.yaml   virtual sources of a case and their helpers
    dashboards/<case>.yaml         one dashboard per case
  link_config.sh                   links these files into an HA config folder
```

## Setup

1. Link the config of the repo:

   ```bash
   dev/manual/link_config.sh ~/ha-dev/config
   ```

   The script links `configuration.yaml`, `packages/`, `dashboards/` and
   `custom_components/adaptative_climate`. An existing file is first renamed
   to `.bak`. A change made in the repo counts at the next restart (at the
   next refresh of the page for a dashboard).
2. Check, then start Home Assistant:

   ```bash
   cd ~/ha-dev && .venv/bin/hass --script check_config -c config
   ```

## Virtual sources

They are `climate` entities of the
[Template](https://www.home-assistant.io/integrations/template/) integration,
driven by helpers: nothing to install. Each case has its own sources (suffix
`_<case>`: `climate.heat_virtual_mono`, `input_select.mode_heat_mono`...), so
testing one case never moves another.

The card of a source, titled after it (*HEAT Virtual*), holds its helpers: they
play the remote of the device, so a change made there always applies. Below, the
table *Shown by HEAT Virtual* gives what the source entity shows, as the
integration reads it: its modes, mode and action, temperature, targets, range
(min / max / step) and fan / swing with their options. The helpers:

| Helper | Effect |
|---|---|
| *Mode*, *Target* (*low*, *high*), *Fan*, *Swing* | what the source shows; changing them is acting on the device (its remote) |
| *Temperature* | its current temperature |
| *Available* | off: the source is `unavailable` |
| *Unknown* | on: the source is `unknown` |
| *Obeys the mode* | off: the mode requests are received but not applied |
| *Delay before obeying* | seconds before a mode asked is applied |
| *Applies settings* | off: target, fan and swing received but not applied |
| *Offers ...* | off: the source offers nothing but `off` (a served mode lost) |
| *Fan on*, *Swing on* | off: the source no longer has that setting (empty list) |
| *Fan without ...* | on: one fan option leaves the list |

The switches go back to their initial value at each restart. The range
(`min`/`max`) and the step of a source are fixed: a change of range is tested
in the automated tests. **Reset the sources** resets everything for its case;
it does not touch the memory of the entities under test.

The cases with a room sensor have a `sensor.room_sensor_<case>`, driven by
*Room temperature* and *Room sensor available*.

## Test cases

| Dashboard | Entities under test | Sources |
|---|---|---|
| *Tests mono-mode* | one per kind of mode: HEAT (with `max_temp`), COOL (step 1, fan, swing), DEHUM (no target), FAN_ONLY, AUTO, HEAT_COOL (low/high), OFFSET (offset 2 in heat and dry), TRV (external sensor) | one source per entity |
| *Tests bi-source* | BI: `heat_cool` on a radiator and an AC unit, room sensor | RADIATOR (also offers `fan_only`: a foreign mode), AIRCON |
| *Tests multi-sources* | MULTI: one mode per source, `sync_modes` heat/cool/dry, options written differently per source | HEAT, COOL, DRY, FAN_ONLY, AUTO, room sensor |
| *Tests single source* | ALL: every mode on one source | ALL |
| *Tests monitoring* | MONITOR (short delays) and GHOST (a source that does not exist) | RADIATOR, AIRCON, room sensor |
| *Tests manual* | *Adaptative Manual*, created from the UI | HEAT, COOL, DRY, FAN_ONLY, AUTO, ALL, room sensor, external temperature |

The scenarios name the cards by their titles: *Adaptative HEAT* is the entity
under test (what the user does), *HEAT Virtual* its source (what happens on the
device). The delays of the entities are short for the tests (monitoring 30 s to
1 min instead of 15 min): see `configuration.yaml`.

Each view fits on one screen: the entity (thermostat, then its lights and
attributes), its sources, then its scenarios, in columns. *Tests multi-sources*
and *Tests manual* have their sources on a second view.

Start from **Reset the sources** before a case. The scenarios of a view follow
each other: one can rely on the previous ones (a mode already discovered, for
instance).

## When the behavior changes

A change of behavior updates the scenarios concerned (and adds one for the new
behavior): search `dashboards/` for the mode, option or rule touched. Then check
that the YAML loads (`check_config`, and a refresh of the dashboard).
