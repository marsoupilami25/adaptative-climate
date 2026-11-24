# Manual tests

A Home Assistant configuration to test the integration by hand: virtual
`climate` sources, and one dashboard per test case, with its scenarios. Each
scenario cites the rules of the spec it shows.

```text
tests/integration/manual/
  config/
    configuration.yaml             dev HA config, entities under test in YAML
    packages/sources_<case>.yaml   virtual sources of a case and their helpers
    dashboards/<case>.yaml         one dashboard per case
  link_config.sh                   links these files into an HA config folder
  reset_memory.sh                  forgets the memory of entities under test
```

## Setup

1. Link the config of the repo:

   ```bash
   tests/integration/manual/link_config.sh ~/ha-dev/config
   ```

   The script links `configuration.yaml`, the files of `packages/` and of
   `dashboards/` (one link per file: the manual tests of the card add theirs,
   see [tests/card/README.md](../../card/README.md#manual-tests)) and
   `custom_components/adaptative_climate`. An existing file is first renamed
   to `.bak`. It also downloads [UIX](https://github.com/Lint-Free-Technology/uix)
   (UI eXtension, the maintained successor of card-mod; version pinned in
   the script) into `custom_components/uix`: it colors the card of a source
   while it runs (below). A change made in the repo counts at the next restart (at the
   next refresh of the page for a dashboard).
2. Check, then start Home Assistant (the first time, add the UIX service:
   *Settings > Devices & services > Add integration > UI eXtension*, then
   refresh the page):

   ```bash
   cd ~/ha-dev && .venv/bin/hass --script check_config -c config
   ```
3. First start of a new config folder: the helpers start at their minimum
   (temperatures 0 °C, offsets −10), and the entities under test take their
   first targets from those sources (ENT-TGT-10). Press **Reset the sources**
   on every dashboard, stop Home Assistant, forget the memory of every entity
   (`tests/integration/manual/reset_memory.sh --all`), and start it again: the first targets
   are then taken from sources at 20 °C.

## Virtual sources

They are `climate` entities of the
[Template](https://www.home-assistant.io/integrations/template/) integration,
driven by helpers: nothing to install. Each case has its own sources (suffix
`_<case>`: `climate.heat_virtual_mono`, `input_select.mode_heat_mono`...), so
testing one case never moves another.

The card of a source, titled after it (*HEAT Virtual*), holds its helpers: they
play the remote of the device, so a change made there always applies. While
the source runs, its card takes the color of its mode (the colors of Home
Assistant: orange in heat, blue in cool...), with UIX; off, it is plain. Below, the
table *Shown by HEAT Virtual* gives what the source entity shows, as the
integration reads it: its modes, mode and action, temperature, targets, range
(min / max / step) and fan / swing with their options. The helpers:

| Helper | Effect |
|---|---|
| *Mode*, *Target* (*low*, *high*), *Fan*, *Swing* | what the source shows; changing them is acting on the device (its remote) |
| *Temperature* | its current temperature, in the cases without room sensor (mono, unique) |
| *Offset* | in the cases with a room sensor (bi, multi, monitor, manual): the source measures *Room temperature* plus its offset, so it heats or cools with the room; an offset makes a gap with the room sensor or between sources |
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

### Memory of the entities under test

To test a first start again (no stored data, ENT-DATA-1), delete the memory of
an entity: its mode, phase, targets and fan/swing memory, and what its sources
discovered and keep (one file, `.storage/adaptative_climate.<entry_id>`).

1. Press **Reset the sources** of its case: at the next start, the targets are
   taken from the sources as they show them (ENT-TGT-10). Taken from sources
   still at 0 °C, they end up at the minimum (7 / 9 for low / high).
2. Stop Home Assistant: while it runs, it writes its memory back (the script
   refuses).
3. Delete the memory, then start Home Assistant:

   ```bash
   tests/integration/manual/reset_memory.sh --list           # entries, with or without memory
   tests/integration/manual/reset_memory.sh bi heat_cool     # by title, "Adaptative " optional
   tests/integration/manual/reset_memory.sh --all
   tests/integration/manual/reset_memory.sh -c ~/other/config bi
   ```

The cases with a room sensor have a `sensor.room_sensor_<case>`, driven by
*Room temperature* and *Room sensor available*. Their sources measure the
room (*Room temperature* + *Offset*), even while the sensor is unavailable:
the room keeps its temperature, only the thermometer is gone.

The action of a source follows what it measures: in *heat*, `heating` below
its target, else `idle`; in *cool*, `cooling` above it; with low/high (in
*heat_cool* or *auto*), `heating` below low, `cooling` above high.

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
device). Every entity shares the short delays of the tests (anchor
`test_delays` in `configuration.yaml`): monitoring 15 s instead of 15 min,
confirmation of a mode 10 s, next try 30 s, removal confirmation 20 s. A
setting not applied is still reported after 30 s at least (MON-SRC-4).

Each view fits on one screen: the entity (thermostat; its monitoring card with
`binary_sensor.<name>_monitoring_sources` and `_monitoring_temperatures`, *OK*
or *Problem*; then its problems and attributes), its sources, then its
scenarios, in columns. *Tests multi-sources*
and *Tests manual* have their sources on a second view.

Each view defines its **Start**: **Reset the sources**, the state of the
entity under test, and the targets it needs. Each step says where it starts
from: "from **Start**", or "after N" when it goes on from step N; a step never
relies on another one without saying so. A step that depends on the memory of
the entity (a value it may already hold, a first discovery) says what to do
when that memory differs (another value, or the memory forgotten with
`reset_memory.sh`).

## When the behavior changes

A change of behavior updates the scenarios concerned (and adds one for the new
behavior): search `dashboards/` for the mode, option or rule touched. Then check
that the YAML loads (`check_config`, and a refresh of the dashboard).
