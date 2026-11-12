# Adaptative Climate — Specification

Status: **draft**. Baseline written from the README and the code, then
amended. The code will follow the spec once agreed.

Conventions:

- Part I rules are named `<SCOPE>-<SECTION>-<n>` (`SRC-DATA-3`,
  `ENT-INIT-1`...), Part II rules keep their old names (`G-1`, `S-3`...),
  so we can refer to them. A rule is what the integration **must** do.
- ❓ **Q-n**: open question, to be decided. Current behavior is described.
- ⚠ marks a current behavior I believe is a bug or a hole.
- ✅ **resolved**: a question closed by a decision.
- Diagrams are Mermaid (rendered by GitHub and the VS Code Markdown preview
  with the Mermaid extension).

# Part I — New spec

Filled step by step, on request only.

## Table of contents

- [0. Glossary](#0-glossary-new)
- [1. Overall behavior](#1-overall-behavior-new)
  - [1.1 Introduction](#11-introduction)
    - [1.1.1 Overview](#111-overview)
    - [1.1.2 Events exchanged](#112-events-exchanged)
  - [1.2 Source behavior](#12-source-behavior)
    - [1.2.1 Events](#121-events)
    - [1.2.2 Stored data management](#122-stored-data-management)
    - [1.2.3 State management](#123-state-management)
      - [1.2.3.1 State machine](#1231-state-machine)
      - [1.2.3.2 UNDISCOVERED state](#1232-undiscovered-state)
      - [1.2.3.3 OFF state](#1233-off-state)
      - [1.2.3.4 ON(m) state](#1234-onm-state)
      - [1.2.3.5 UNUSABLE state](#1235-unusable-state)
    - [1.2.4 Request confirmation](#124-request-confirmation)
    - [1.2.5 Settings request](#125-settings-request)
  - [1.3 Entity behavior](#13-entity-behavior)
    - [1.3.1 Events](#131-events)
    - [1.3.2 State management](#132-state-management)
      - [1.3.2.1 State machine](#1321-state-machine)
      - [1.3.2.2 INIT state](#1322-init-state)
      - [1.3.2.3 OFF state](#1323-off-state)
      - [1.3.2.4 ON(m) state](#1324-onm-state)
      - [1.3.2.5 WAITING(m) state](#1325-waitingm-state)
      - [1.3.2.6 NO_SOURCE state](#1326-no_source-state)
    - [1.3.3 Mode management](#133-mode-management)
      - [1.3.3.1 Mono-source and bi-source modes](#1331-mono-source-and-bi-source-modes)
      - [1.3.3.2 Bi-source mode: phase management](#1332-bi-source-mode-phase-management)
        - [1.3.3.2.1 Phase management](#13321-phase-management)
        - [1.3.3.2.2 Wanted phase](#13322-wanted-phase)
    - [1.3.4 Capabilities management](#134-capabilities-management)
      - [1.3.4.1 Principle](#1341-principle)
      - [1.3.4.2 Modes offered](#1342-modes-offered)
      - [1.3.4.3 Temperature targets used by each mode](#1343-temperature-targets-used-by-each-mode)
      - [1.3.4.4 Step](#1344-step)
      - [1.3.4.5 Range](#1345-range)
      - [1.3.4.6 Fan and swing](#1346-fan-and-swing)
    - [1.3.5 Settings management](#135-settings-management)
      - [1.3.5.1 Reference temperature](#1351-reference-temperature)
      - [1.3.5.2 External sensors](#1352-external-sensors)
- [2. Configuration](#2-configuration-new)
  - [2.1 Modes](#21-modes)
  - [2.2 Temperature sensor](#22-temperature-sensor)
  - [2.3 Timers and durations](#23-timers-and-durations)
  - [2.4 Monitoring](#24-monitoring)
  - [2.5 Temperature limits](#25-temperature-limits)
  - [2.6 Fan and swing](#26-fan-and-swing)
- [3. Monitoring](#3-monitoring-new)

<a id="0-glossary-new"></a>

## 0. Glossary

| Term | Meaning |
|---|---|
| **Entity** | The Adaptative Climate `climate` entity (one per config entry). |
| **Source entity** | A `climate` entity of Home Assistant configured for a mode (`<mode>_entity`). One source entity can serve several modes. |
| **Source** | The local object that follows one source entity: its stored data (§1.2.2) and its state machine (§1.2.3.1). One per source entity. |
| **Reference temperature** | The temperature the entity regulates on: the temperature sensor (`temperature_sensor`) when set, else the current temperatures of the sources, minus the offset of their mode (§2.2). |
| **Takeover** | A change made directly on a source entity (remote, app) that the entity follows: the source wins. |
| **Source mode** | The HVAC mode sent to a source: the mode, or the **phase** (`heat` / `cool`) of a bi-source mode (§1.3.3.1). |
| **Served modes** | The modes of the entity a source entity is configured for. Known by the entity only. |
| **Usable** | A source entity that exists in Home Assistant and whose state is not `unavailable` / `unknown`. |
| **Capability** | A capability attribute of a source entity (Home Assistant `capability_attributes` of `climate`), or `supported_features`, kept by the source (§1.2.2). Managed: `hvac_modes` (per source); `supported_features`, `min_temp`, `max_temp`, `target_temp_step`, `fan_modes`, `swing_modes`, `swing_horizontal_modes` (per source and mode). Not managed for now: `min_humidity`, `max_humidity`, `target_humidity_step`, `preset_modes`. |
| **Request** | The entity asks a source entity for a mode (or `off`). |

Diagram notation: UML state diagrams, transitions written
`event [guard] / activity`.

<a id="1-overall-behavior-new"></a>

## 1. Overall behavior

### 1.1 Introduction

#### 1.1.1 Overview

```mermaid
flowchart LR
    U["User<br/>(card, automations)"]
    T["Temperature sensor<br/>(temperature_sensor)"]
    subgraph INT["Adaptative Climate integration (one config entry)"]
        AC["AC entity<br/>climate.living_room"]
        S1["Source<br/>climate.heater"]
        S2["Source<br/>climate.ac"]
    end
    subgraph HA["Home Assistant climate entities"]
        E1["Source entity<br/>climate.heater"]
        E2["Source entity<br/>climate.ac"]
    end
    U -- "mode, targets, fan/swing" --> AC
    T -- "TStAC events" --> AC
    AC -- "ACtS_request(r)" --> S1
    AC -- "ACtS_request(r)" --> S2
    S1 -- "source events, data" --> AC
    S2 -- "source events, data" --> AC
    S1 -- "StSE events (service calls)" --> E1
    S2 -- "StSE events (service calls)" --> E2
    E1 -- "SEtS events (state changes)" --> S1
    E2 -- "SEtS events (state changes)" --> S2
```

- **AC entity**: the Adaptative Climate `climate` entity seen by the user.
  It decides the mode and drives its sources (§1.3).
- **Source**: one local object per source entity (§1.2). It follows its
  source entity, stores its data, and carries out the requests of the AC
  entity. The AC entity never talks to a source entity directly.
- **Source entity**: a `climate` entity of Home Assistant (heater, AC,
  heat pump...), configured for one or more modes of the AC entity.
- **Temperature sensor**: the optional sensor giving the reference temperature (`temperature_sensor`,
  §2.2).

#### 1.1.2 Events exchanged

Between the user and the AC entity:

| Event | Direction | Meaning |
|---|---|---|
| `UtAC_set_mode(m)` | user → AC entity | The user asks for the mode `m` (`off` included): card, `set_hvac_mode`, `turn_on` (last mode), `turn_off`. |
| `UtAC_set_settings(s)` | user → AC entity | The user sets settings `s`: targets (`set_temperature`), fan, swing, horizontal swing. |

Between the temperature sensor and the AC entity:

| Event | Direction | Meaning |
|---|---|---|
| `TStAC_temperature(t)` | temperature sensor → AC entity | The temperature sensor has a new valid value `t` (converted to the unit of Home Assistant). |

Between the AC entity and a source:

| Event | Direction | Meaning |
|---|---|---|
| `ACtS_request(r)` | AC entity → source | Put the source entity in `r` (an HVAC mode, or `off`). |
| `ACtS_settings(s)` | AC entity → source | Settings `s` (targets, fan/swing) for the source entity (§1.2.5). |
| `StAC_settings(s)` | source → AC entity | Settings `s` changed on the source entity (takeover), outside a request confirmation and `SETTLE(m)` (§1.2.5). |
| `StAC_temperature(t)` | source → AC entity | The current temperature `t` of the source entity changed (§1.2.3.1). |
| `StAC_undiscovered` | source → AC entity | The source enters `UNDISCOVERED`. |
| `StAC_off` | source → AC entity | The source enters `OFF`. |
| `StAC_on(m)` | source → AC entity | The source enters `ON(m)`. |
| `StAC_unusable` | source → AC entity | The source enters `UNUSABLE`. |
| `StAC_usable` | source → AC entity | The source leaves `UNUSABLE` (it goes back to its stored state, which the AC entity already knows). |
| data | AC entity reads the source | The stored data of the source (capabilities), read when needed, whatever the state of the source. |

Between a source and its source entity:

| Event | Direction | Meaning |
|---|---|---|
| `StSE_set_hvac_mode(r)` | source → source entity | Service call `climate.set_hvac_mode` carrying out a request. |
| `StSE_set_temperature(t)`, `StSE_set_fan_mode(f)`, `StSE_set_swing_mode(w)`, `StSE_set_swing_horizontal_mode(h)` | source → source entity | Service calls carrying out a settings request (§1.2.5). |
| `SEtS_off`, `SEtS_on(m)`, `SEtS_unavailable`, `SEtS_unknown`, `SEtS_attributes` | source entity → source | Changes of the source entity (§1.2.1). |

Settings (targets, fan/swing): §1.2.5.

### 1.2 Source behavior

A source has four functions:

- **stored data management** (§1.2.2): permanent, it does not depend on
  the state of the source;
- **state management** (§1.2.3): the state machine of the source. Its
  state is a **local** state, kept in sync with the source entity; it is
  not the state of the source entity itself;
- **request confirmation** (§1.2.4): confirmation, retries and settle time
  of a request, in parallel with the state machine;
- **settings request** (§1.2.5): targets and fan/swing settings sent to
  the source entity.

#### 1.2.1 Events

| Event | Meaning |
|---|---|
| `start` | The config entry is set up (HA start, entry reload). |
| `restored` | The first restore of the stored data is done (§1.2.2). |
| `data_available` | The data of a source becomes available: restored or read at start (SRC-DATA-4), or read later (SRC-DATA-6). |
| `SEtS_off` | The source entity changed to `off`. |
| `SEtS_on(m)` | The source entity changed to the HVAC mode `m`. |
| `SEtS_unavailable` | The source entity changed to `unavailable`, or was removed from Home Assistant. |
| `SEtS_unknown` | The source entity changed to `unknown`. |
| `SEtS_attributes` | Only attributes of the source entity changed (its state stays the same). |
| `ACtS_request(r)` | The entity asks the source entity for `r` (an HVAC mode, or `off`). |
| `ACtS_settings(s)` | The entity gives the settings `s` (targets, fan/swing) for the source entity (§1.2.5). |

#### 1.2.2 Stored data management

##### 1.2.2.1 Stored data

Stored data of a source, saved across restarts:

| Data | Kept per | Content |
|---|---|---|
| State | source | The last usable state: `OFF` or `ON(m)`. Never `UNDISCOVERED` / `UNUSABLE`. Written by the mode management. |
| `hvac_modes` | source | The HVAC modes of the source entity. The same whatever its mode. |
| Mode capabilities | (source, mode) | `supported_features`, `min_temp`, `max_temp`, `target_temp_step`, `fan_modes`, `swing_modes`, `swing_horizontal_modes`, as last read **while the source entity was in that mode**. |
| `low_high_seen` | (source, mode) | The source entity has shown numeric `target_temp_low` / `target_temp_high` once while in that mode. Never cleared. |

- **SRC-DATA-1** The mode capabilities are **discovered** as the modes are
  used: those of a mode are read only while the source entity runs in it
  (source state `ON(m)`). A mode of `hvac_modes` with no stored
  capabilities (never run) gets the Home Assistant defaults:

  | Capability | Default |
  |---|---|
  | `supported_features` | 0: no target, no fan, no swing |
  | `min_temp` / `max_temp` | 7 °C / 35 °C, converted to the unit of Home Assistant |
  | `target_temp_step` | none |
  | `fan_modes`, `swing_modes`, `swing_horizontal_modes` | none |
  | `low_high_seen` | no |

- **SRC-DATA-2** Nothing is read for `off` (useless).
- **SRC-DATA-3** The data is **available** once `hvac_modes` is known
  (restored or read). Mode capabilities may still be missing: Home
  Assistant defaults (SRC-DATA-1).
- What the entity does with a mode not discovered yet: ENT-CAP-3 to ENT-CAP-6
  (§1.3).

##### 1.2.2.2 Restore (at `start`):

```mermaid
flowchart TD
    S[start] --> A{stored data?}
    A -- yes --> R[restore it / data_available]
    A -- no --> B{source entity usable?}
    B -- yes --> C[read it, state := OFF, save / data_available]
    B -- no --> D[data not available]
    R --> E[raise restored]
    C --> E
    D --> E
```

- **SRC-DATA-4** At `start`, the stored data is read. 
  - Without stored data, the
  source entity is read (`hvac_modes`, and the mode capabilities if it
  runs in a mode), and the stored state is set to `OFF`: the source was
  never used, so it starts from a clean state (its entry turns the
  source entity off if it runs, SRC-STATE-2).
  - If it cannot be read (not usable), the data is not
  available. 
  - Data restored or read raises `data_available`. The end of
  this first restore raises `restored`.
- **SRC-DATA-5** A stored value that is not valid (corrupted) is dropped; the
  other stored data is restored.

##### 1.2.2.3 Update (on each change of the source entity):

- **SRC-DATA-6** On every change of a usable source entity (`SEtS_off`,
  `SEtS_on(m)`, `SEtS_attributes`):
  - data not available yet → it is read and saved: data available
    (`data_available`);
  - `hvac_modes` is read again;
  - if the source entity runs in a mode `m`, the capabilities of `m`
    are read again;
  - each value read is compared with the stored one:
    - no change → nothing; 
    - a new or updated value that removes nothing (a first value, a new number, a list with more items) → stored and saved at once; 
    - a value no longer shown (attribute missing or `None`), or a list that lost items (`fan_modes` without `turbo`) → removal confirmation (below).
- **SRC-DATA-7** A source entity that is not usable is not read: the stored
  data stays as it is.
- **SRC-DATA-8** `low_high_seen` of mode `m` is set when numeric low/high
  values are shown while the source entity runs in `m`. It is never
  removed.
- **SRC-DATA-9** Only the configured source entities keep their data: a
  source entity removed from the configuration loses it.

`change` in this diagram: `SEtS_off`, `SEtS_on(m)` or `SEtS_attributes`.

**Removal confirmation** (one per value no longer shown or list that lost
items: `hvac_modes`, or a capability of a mode):

```mermaid
stateDiagram-v2
    direction LR
    state "KEPT" as K
    state "CONFIRMING<br/>(capability_rem_confirmation)" as C
    [*] --> K
    K --> C : change [value no longer shown] / start timer
    C --> C : change [value still not shown] / nothing
    C --> K : change [value shown again] / cancel timer, update if new value
    C --> K : source entity leaves the mode [mode capability] / cancel timer
    C --> K : SEtS_unavailable, SEtS_unknown / cancel timer
    C --> K : timeout / remove it, save
```

- **SRC-DATA-10** A value no longer shown, or a list that lost items, is kept
  as it is for `capability_rem_confirmation` (§2.3, 60 s by default). The
  timer is cancelled when the full value is shown again; other changes of
  the source entity (current temperature...) let it run. At the end of the
  timer, the value is removed (or replaced by the shorter list now shown)
  and the data is saved.
- **SRC-DATA-11** A capability of mode `m` is only judged while the source
  entity runs in `m`: the source entity leaving `m` cancels its timer.
  The source entity becoming not usable cancels every timer (SRC-DATA-7).

#### 1.2.3 State management

##### 1.2.3.1 State machine

```mermaid
stateDiagram-v2
    direction TB
    state "UNDISCOVERED" as UNDISCOVERED
    state "OFF<br/>entry / check source entity" as OFF
    state "ON(m)<br/>entry / check source entity" as ON
    state "UNUSABLE" as UNUS
    state first <<choice>>
    state stored <<choice>>
    state back <<choice>>

    [*] --> first : restored
    first --> UNDISCOVERED : [data not available] / StAC_undiscovered
    first --> UNUS : [data available, source entity not usable] / StAC_unusable
    first --> stored : [data available, source entity usable]
    stored --> OFF : [stored state OFF] / StAC_off
    stored --> ON : [stored state ON(m)] / StAC_on(m)

    UNDISCOVERED --> OFF : data_available / StAC_off

    OFF --> ON : SEtS_on(m) / StAC_on(m)
    ON --> OFF : SEtS_off / StAC_off
    ON --> ON : SEtS_on(m2) / StAC_on(m2)
    OFF --> UNUS : SEtS_unavailable, SEtS_unknown / StAC_unusable
    ON --> UNUS : SEtS_unavailable, SEtS_unknown / StAC_unusable

    OFF --> ON : ACtS_request(m)
    ON --> ON : ACtS_request(m2)
    ON --> OFF : ACtS_request(off)

    UNUS --> UNUS : ACtS_request(r) / store r
    UNUS --> back : SEtS_off, SEtS_on(m) / StAC_usable
    back --> OFF : [stored state OFF]
    back --> ON : [stored state ON(m)] / send the kept settings again (SETTLE(m), §1.2.4)
```

"check source entity" (entry of `OFF` and `ON(m)`): if the source entity
does not show the state (`off`, or `m`), the state is sent to it and the
request confirmation starts (§1.2.4).

- **SRC-STATE-1** After `start`, the source waits for the end of the first
  restore (`restored`), then:
  - data not available → `UNDISCOVERED`, reported to the entity;
  - data available and source entity not usable → `UNUSABLE`,
    reported to the entity;
  - data available and source entity usable → the stored state (`OFF`
    when the data was read from the source entity, SRC-DATA-4), reported to
    the entity (`OFF` or `ON(m)`).
- **SRC-STATE-2** On entry of `OFF` or `ON(m)`, however it is entered (request,
  restore, back from `UNUSABLE`), the state is compared with the source
  entity: if it differs, the state is sent to the source entity and the
  request confirmation starts (§1.2.4). Entered from a change of the
  source entity, it is the same: nothing is sent.
- **SRC-STATE-3** In `OFF` or `ON(m)`, a request from the entity 
  - moves the state
  at once to the state asked (`ON(m)` or `OFF`); 
  - its entry sends it
  (SRC-STATE-2). 
  - `ON(m)` → `ON(m2)` is a new entry. 
  - No `StAC_` event is sent:
  the entity asked for it. A `StAC_off` / `StAC_on(m)` always means a
  change made on the source entity, never the result of a request.
- **SRC-STATE-4** In `UNUSABLE`, a request from the entity is stored as the
  stored state; nothing is sent.
- **SRC-STATE-5** In `OFF` or `ON(m)`, a change of the source entity
  (`SEtS_off`, `SEtS_on(m)`) moves the state, and the new state is reported to the entity.
  During a request confirmation, these changes are handled by the
  confirmation (§1.2.4) and do not reach the state machine.
- **SRC-STATE-6** In `OFF` or `ON(m)`, `SEtS_unavailable` or `SEtS_unknown` always moves the source to
  `UNUSABLE`, even during a request confirmation, which ends (the state
  asked stays the stored state, sent again on return: SRC-STATE-7). Reported to
  the entity.
- **SRC-STATE-7** In `UNUSABLE`, the source entity back (`SEtS_off` or
  `SEtS_on(m)`) moves the source to its **stored** state, not to the state
  shown.
  - The entry of that state sends it if needed (SRC-STATE-2).
  - When the stored state is `ON(m)`, the source always goes through
    `SETTLE(m)` (§1.2.4), even if the source entity already shows `m`: it
    sends its kept settings, ignores during `settle_timer` the values the
    device reports while reconnecting, and sends them again at the end if
    needed (SRC-SET-5).
  - The entity gets only `StAC_usable`: the stored state is the one it
    already knows.
- **SRC-STATE-8** In `UNDISCOVERED`, no request is made (the entity refuses the mode
  before). When the data becomes available, the source goes to `OFF`,
  reported to the entity; its entry turns the source entity off if it
  runs (SRC-STATE-2).
- **SRC-STATE-9** Every change of state is saved as the stored state (except
  `UNDISCOVERED` / `UNUSABLE`, which keep the last usable one).
- **SRC-STATE-10** Resynchronization: at start, and when the source entity comes
  back from unavailable, **Home Assistant wins**: the stored state is sent
  to the source entity (SRC-STATE-2, SRC-STATE-7), whatever was changed on the device
  meanwhile. At start, everything is resynchronized (several sources left
  on would give odd effects); after unavailability, there was a problem,
  so everything is resynchronized when it ends. The source entity has the
  upper hand (takeover) only in nominal operation: `OFF` / `ON(m)`,
  outside a request confirmation (SRC-STATE-5).

- **SRC-STATE-11** In `OFF` or `ON(m)`, a change of the current
  temperature of the source entity (`current_temperature`, in
  `SEtS_attributes`) is reported to the entity: `StAC_temperature(t)`, as
  read (the entity removes the offset of the mode, §2.2).

##### 1.2.3.2 UNDISCOVERED state

The data of the source is not available.

- The first usable change of the source entity makes the data available
  (SRC-DATA-6): `data_available` moves the source to `OFF` (SRC-STATE-8).
- **SRC-UNDISC-1** The source offers nothing: no capability (the entity does
  not count it for the step, uses Home Assistant default ranges 7–35 °C,
  no options), no HVAC mode (its modes are not judged as offered or not).

##### 1.2.3.3 OFF state

The source entity is off.

- Settings: see §1.2.5.

##### 1.2.3.4 ON(m) state

The source entity runs in `m`, any HVAC mode other than `off`.

- **SRC-ON-1** The source does not know which modes the entity uses it for:
  `ON(m)` is just the HVAC mode of the source entity. Whether `m` is a mode
  the source serves here (or a foreign mode) is decided by the entity.
- Settings: see §1.2.5.

##### 1.2.3.5 UNUSABLE state

The source entity is not usable (`unavailable`, `unknown`, or missing in
Home Assistant), but the data of the source is available.

- The stored data stays as it is (SRC-DATA-7): the entity keeps reading the
  capabilities of the source as they were when it was last usable.

#### 1.2.4 Request confirmation

Runs in parallel with the state machine of §1.2.3.1. `send(r)` is the
entry check of `OFF` / `ON(m)` sending `r` to the source entity (SRC-STATE-2).
It works the same way to turn a source entity on in a mode (`r` = `m`)
and to turn it off (`r` = `off`).

`monitoring up` raises the problem "source out of sync" of this source
(MON-GEN-1); `monitoring down` clears it (nothing to do if it is not raised).

```mermaid
stateDiagram-v2
    direction LR
    state "IDLE" as I
    state "CONFIRMING(r)<br/>confirm timer: request_confirmation_timer" as C
    state "RETRY_WAIT(r)<br/>retry timer: request_retry_timer" as W
    state "SETTLE(m)<br/>settle timer: settle_timer" as S
    [*] --> I
    I --> C : send(r) / StSE_set_hvac_mode(r), start confirm timer
    I --> S : back from UNUSABLE in ON(m), source entity already in m / start settle timer
    C --> S : SEtS_on(m) [r = m shown] / cancel confirm timer, monitoring down, start settle timer
    C --> I : SEtS_off [r = off] / cancel confirm timer, monitoring down
    C --> C : SEtS_off, SEtS_on(m) [r not shown] / ignored
    C --> C : StSE_set_hvac_mode failed / log
    C --> W : confirm timeout / monitoring up, start retry timer
    C --> C : send(r2) / monitoring down, StSE_set_hvac_mode(r2), r := r2, restart confirm timer
    C --> I : SEtS_unavailable, SEtS_unknown / cancel confirm timer, monitoring down
    W --> C : retry timeout / StSE_set_hvac_mode(r), start confirm timer
    W --> S : SEtS_on(m) [r = m shown] / cancel retry timer, monitoring down, start settle timer
    W --> I : SEtS_off [r = off] / cancel retry timer, monitoring down
    W --> I : SEtS_off, SEtS_on(m) [r not shown] / cancel retry timer, monitoring down, followed (SRC-STATE-5)
    W --> C : send(r2) / cancel retry timer, monitoring down, StSE_set_hvac_mode(r2), r := r2, start confirm timer
    W --> I : SEtS_unavailable, SEtS_unknown / cancel retry timer, monitoring down
    S --> I : settle timeout (settings: §1.2.5)
    S --> I : SEtS_attributes [settings sent shown] / cancel settle timer
    S --> I : SEtS_off, SEtS_on(m2) / cancel settle timer, followed (SRC-STATE-5)
    S --> C : send(r2) / cancel settle timer, StSE_set_hvac_mode(r2), r := r2, start confirm timer
    S --> I : SEtS_unavailable, SEtS_unknown / cancel settle timer
```

- **SRC-REQ-1** During the confirmation, the changes of the source entity
  that do not show `r` are ignored: a device may still show its previous
  mode, or go through `off`, before showing the mode asked. Cloud devices
  may take a while. Exception: `SEtS_unavailable` / `SEtS_unknown` ends the confirmation
  (SRC-STATE-6).
- **SRC-REQ-2** The source entity showing `r` ends the confirmation: the
  source is in the state asked. When `r` is a mode (`ON(m)`), the source
  enters `SETTLE(m)`: the settings (targets, fan/swing) are sent and, for
  `settle_timer` (§2.3, 12 s by default), the settings shown by the source
  entity are ignored
  (§1.2.5, SRC-SET-5).
- **SRC-REQ-3** `SETTLE(m)` 
  - ends 
    - at the end of the settle timer, 
    - or earlier
  when the source entity shows the settings sent. 
  - It also stops (settle
  timer cancelled) 
    - when the source leaves `m`: a change of the source
  entity (`SEtS_off`, `SEtS_on(m2)`, followed: SRC-STATE-5), 
    - a new request
  (a new confirmation starts), 
    - or `SEtS_unavailable` / `SEtS_unknown`.
- **SRC-REQ-4** The call to the source entity fails: the error is logged;
  the confirmation goes on until its timeout (SRC-REQ-6).
- **SRC-REQ-5** A new send (new request) during the confirmation or the
  retry wait replaces the previous one: the state confirmed becomes the
  new one (`r := r2`), and a new confirmation starts.
- **SRC-REQ-6** Timeout of the confirmation while the source entity does not
  show `r` (call failed, or the device did not follow): the monitoring
  reports the source entity out of sync (MON-GEN-1), and the source waits
  `request_retry_timer` (§2.3, 5 min by default: retry wait).
- **SRC-REQ-7** At the end of the retry wait, `r` is sent again and a new
  confirmation (`request_confirmation_timer`, §2.3, 30 s by default) starts, with
  the same behavior. This goes on every `request_retry_timer` as long as the
  source entity does not show `r`.
- **SRC-REQ-8** The confirmation and the retries stop only when the source
  entity shows `r`, or when the source leaves the state that started them
  (new request: SRC-REQ-5; `SEtS_unavailable` / `SEtS_unknown`: SRC-STATE-6; change of the source entity
  during the retry wait: SRC-REQ-9).
- **SRC-REQ-9** During the retry wait, the source entity is master: a change
  of the source entity to another state than `r` (remote, app) stops the
  retries and is followed as a takeover (SRC-STATE-5): the state moves and is
  reported to the entity.
- **SRC-REQ-10** When the settle time applies. `SETTLE(m)` protects the
  settings Home Assistant has just **pushed**: right after entering a
  mode, some devices report their own stored value for that mode a few
  seconds later, which must not be taken for a takeover.
  - Settle: after a request confirmed by the source entity (Home
    Assistant asked for the mode and pushes its settings).
  - Settle: when the source comes back from `UNUSABLE` in `ON(m)`
    (resynchronization, Home Assistant wins and pushes its settings,
    SRC-STATE-7).
  - No settle: on a mode change made on the device (`SEtS_on(m)` outside
    a confirmation). The source wins: nothing is pushed, the settings of
    the device are adopted (SRC-SET-10), and the values it reports in the
    next seconds are adopted too.

#### 1.2.5 Settings request

Settings `s`: any of the targets (`temperature`, or `target_temp_low` and
`target_temp_high`, already computed by the entity: offset (§2.2), step,
range),
`fan_mode`, `swing_mode`, `swing_horizontal_mode`. Each one is sent with
its own service call (`StSE_set_temperature`, `StSE_set_fan_mode`,
`StSE_set_swing_mode`, `StSE_set_swing_horizontal_mode`). The settle time
comes from the request confirmation (`SETTLE(m)`, §1.2.4).

```mermaid
stateDiagram-v2
    direction LR
    state "STEADY<br/>resync timer 30 min" as St
    state "RETRY<br/>send retry timer 5 s" as R
    [*] --> St : start / start resync timer
    St --> St : ACtS_settings(s) / keep s
    St --> St : mode change (ACtS_request, SEtS_off, SEtS_on(m2)) / withdraw kept settings
    St --> St : ACtS_settings(s) [ON(m), no confirmation, not shown] / StSE_set_*(s)
    St --> St : enter SETTLE(m) (§1.2.4) / StSE_set_*(kept settings not shown)
    St --> St : SEtS_attributes [in SETTLE, other settings shown] / ignored, remember it
    St --> St : SEtS_attributes [ON(m), no confirmation, not in SETTLE, a setting changed] / keep it, StAC_settings(changed)
    St --> St : SEtS_on(m) followed (takeover, SRC-STATE-5) / keep the settings shown, StAC_settings(all)
    St --> St : settle timeout [other settings were shown] / StSE_set_*(kept settings)
    St --> St : resync timeout [ON(m), no confirmation, settings not shown] / StSE_set_*(s), restart resync timer
    St --> St : resync timeout [otherwise] / restart resync timer
    St --> R : StSE_set_* failed / start send retry timer
    R --> St : send retry timeout / StSE_set_*(latest s), log a warning if it fails
```

- **SRC-SET-1** The source keeps the last settings received
  (`ACtS_settings(s)`) for its current mode: settings depend on the mode.
  - When the mode of the source changes (`ACtS_request(r)` for another
  state, or a change of the source entity followed: `SEtS_off`,
  `SEtS_on(m2)`), the kept settings are **withdrawn**. 
  - After a request,
  the entity sends the settings of the new mode (`ACtS_settings(s)`).
  - In `UNUSABLE`, they are kept, unless a request for another state is
  received: the state asked is stored (SRC-STATE-4) and the kept settings are
  withdrawn, as for any mode change.
- **SRC-SET-2** In `ON(m)` outside a request confirmation, a settings request
  is sent to the source entity at once, except the settings it already
  shows. Low and high targets go together.
- **SRC-SET-3** In `OFF`, `UNDISCOVERED`, `UNUSABLE`, and during a request
  confirmation (`CONFIRMING`, `RETRY_WAIT`), nothing is sent: the
  settings are kept, and sent when the source enters `SETTLE(m)`.
- **SRC-SET-4** Fan and swing values are matched to the options of the source
  entity in that mode ignoring case, and sent as the source entity spells
  them. A value it does not offer is not sent.
- **SRC-SET-5** On entry of `SETTLE(m)` (§1.2.4), the kept settings the
  source entity does not show are sent. During `SETTLE(m)`, the settings
  shown by the source entity are ignored (a device may report its own
  values for the mode a few seconds later). 
- **SET-x** At the end of the settle
  timer, if the source entity showed other settings meanwhile, the kept
  settings are sent again; if it showed nothing, nothing is sent. Known
  limitation: a source entity already at the settings gets nothing, so
  nothing ends `SETTLE(m)` early: its settings are ignored for the full
  `settle_timer`.
- **SRC-SET-6** Retry on error: a call that fails is tried again **once**,
  5 s later, with the settings of that time. If it fails again, a warning
  is logged. Only a call error triggers it, not a source entity that
  accepts the call without applying the setting.
- **SRC-SET-7** Resync: the resync timer runs all the time (started at
  `start`, restarted at each timeout). Every 30 minutes, the settings the source entity does
  not show (compared with those sent) are sent again (a command lost by
  the device, a device back to its own value without telling).
- **SRC-SET-8** Monitoring: a setting sent and not shown by the source entity
  is a problem (MON-GEN-2). Not judged during `SETTLE(m)` or a request
  confirmation.
- **SRC-SET-9** Setting not applied (the source entity accepts the call, or
  fails, and its value **does not change**): the source keeps the setting
  received from the entity, which stays the reference (Home Assistant wins). It is sent
  again (SRC-SET-6, SRC-SET-7) and the monitoring reports it (MON-GEN-2). Nothing is
  sent to the entity: its setting is unchanged.
- **SRC-SET-10** Takeover (a value of the source entity **changes** to another
  value than the one sent: remote, app): in `ON(m)`, outside a request
  confirmation and `SETTLE(m)`, the source keeps the new value as its
  setting and sends `StAC_settings(s)` (the settings changed) to the
  entity, which adopts them. During a confirmation or `SETTLE(m)`, such
  changes are ignored (SRC-REQ-1, SRC-SET-5). After a mode change made on the
  source entity (`SEtS_on(m)` followed, SRC-STATE-5), the source sends its
  current settings at once (`StAC_settings(s)`, the settings shown by the
  source entity in `m`): the entity adopts them (the source wins).
- How the entity computes the targets (offsets, steps, ranges) and
  remembers fan/swing per mode: to be specified (Part II §4, §5).

### 1.3 Entity behavior

The AC entity has four functions:

- **state management** (§1.3.2): its own state machine, which drives the
  sources;
- **mode management** (§1.3.3): mono-source and bi-source modes, and the
  phases of a bi-source mode;
- **capabilities management** (§1.3.4): its capabilities, from those of
  its sources;
- **settings management** (§1.3.5): targets and fan/swing settings.

#### 1.3.1 Events

| Event | Direction | Meaning |
|---|---|---|
| `UtAC_set_mode(m)` | user → AC entity | The user asks for the mode `m` (`off` included): card, `set_hvac_mode`, `turn_on` (last mode), `turn_off`. |
| `UtAC_set_settings(s)` | user → AC entity | The user sets settings `s`: targets (`set_temperature`), fan, swing, horizontal swing. |
| `TStAC_temperature(t)` | temperature sensor → AC entity | See §1.1.2. |
| `StAC_undiscovered`, `StAC_off`, `StAC_on(m)`, `StAC_unusable`, `StAC_usable`, `StAC_settings(s)`, `StAC_temperature(t)` | source → AC entity | See §1.1.2. Each one comes from one source. |
| `ACtS_request(r)`, `ACtS_settings(s)` | AC entity → source | See §1.1.2. |

Words used below:

- **source of `m`**: the source configured for the mode `m` of the
  entity;
- **active source**: the source of the current mode;
- **available source**: a source in `OFF` or `ON(x)` (not `UNDISCOVERED`, not
  `UNUSABLE`);
- **served / foreign**: `StAC_on(x)` from a source `S` is **served** when
  `S` is the source of the mode `x` of the entity, **foreign** otherwise
  (a heater set to `fan_only` on its remote).

#### 1.3.2 State management

##### 1.3.2.1 State machine

Activities on the transitions:

| Activity | What is sent |
|---|---|
| `apply(m)` | To the source of `m`: `ACtS_request(m)` (the phase for a bi-source mode) and `ACtS_settings(s)` (the settings of `m`, §1.3.5).<br> To every other source not `OFF` (`UNUSABLE` included): `ACtS_request(off)`. |
| `apply(off)` | To every source not `OFF` (`UNUSABLE` included): `ACtS_request(off)`. |
| `follow(S)` | Takeover by `S` in a **served** mode only. To every source not `OFF` other than `S` (`UNUSABLE` included): `ACtS_request(off)`. Nothing to `S`. |

```mermaid
stateDiagram-v2
    direction TB
    state "INIT<br/>shown unavailable" as INIT
    state "NO_SOURCE<br/>shown unavailable" as NOSRC
    state start_choice <<choice>>

    [*] --> INIT : start
    INIT --> start_choice : every source has reported its first state
    start_choice --> NOSRC : [every source UNUSABLE]
    start_choice --> OPER : [otherwise]
    NOSRC --> OPER : a source becomes usable
    OPER --> NOSRC : StAC_unusable [every source UNUSABLE]

    state OPER {
        state "OFF<br/>shown off" as OFF
        state "ON(m)<br/>shown m" as ON
        state "WAITING(m)<br/>shown unknown" as WAIT
        state resume <<choice>>

        [*] --> resume
        resume --> OFF : [stored mode off, or none, or source of m UNDISCOVERED] / apply(off)
        resume --> ON : [stored mode m, source of m available] / apply(m)
        resume --> WAIT : [stored mode m, source of m UNUSABLE] / apply(m)

        OFF --> ON : UtAC_set_mode(m) [source of m available] / apply(m)
        OFF --> ON : StAC_on(m) from S [served] / follow(S)
        OFF --> OFF : StAC_on(x) [foreign] / log

        ON --> OFF : UtAC_set_mode(off) / apply(off)
        ON --> OFF : StAC_off from the active source
        ON --> OFF : StAC_on(x) from the active source [foreign] / log
        ON --> ON : StAC_on(x) from another source [foreign] / log
        ON --> ON : UtAC_set_mode(m2) [source of m2 available] / apply(m2)
        ON --> ON : StAC_on(m2) from S [served] / follow(S)
        ON --> WAIT : StAC_unusable from one source of the mode [mono-source, or both sources UNUSABLE]

        WAIT --> ON : StAC_usable from one source of the mode (bi-source: from either phase source)
        WAIT --> ON : UtAC_set_mode(m2) [source of m2 available] / apply(m2)
        WAIT --> ON : StAC_on(m2) from S [served] / follow(S)
        WAIT --> OFF : UtAC_set_mode(off) / apply(off)
        WAIT --> WAIT : StAC_on(x) [foreign] / log
    }
```

- **ENT-STATE-1** The entity stores its mode (`off` or `m`), saved across
  restarts. `INIT` and `NO_SOURCE` keep it.
- **ENT-STATE-2** **A change asked by the user** (`UtAC_set_mode`) is sent to
  the sources (`apply`). **A change coming from a source** (`StAC_`) is
  followed, and nothing is sent to that source: the source wins
  (takeover). The other sources are still turned off (`follow`).
- **ENT-STATE-3** A user mode change goes to the mode asked if its source is
  available (`OFF` or `ON`). `off` is always accepted. Otherwise it is
  refused with an error.
- **ENT-STATE-4** A source mode change:
  - `StAC_on(x)` **served**: takeover, the entity goes to `ON(x)` and
    turns the other sources off (`follow`);
  - `StAC_on(x)` **foreign** from the currently active source (it left
    its mode for a foreign one): the entity goes `OFF`; nothing is sent
    to any source (the source keeps running);
  - `StAC_on(x)` **foreign** from any other source: nothing happens
    (logged, listed in the `foreign_modes` attribute);
  - `StAC_off` from the active source: the entity goes `OFF`.
- **ENT-STATE-5** Main states: `INIT`, `OPER` (sub-states `OFF`, `ON(m)`,
  `WAITING(m)`) and `NO_SOURCE`. Entering `OPER` goes through the choice
  `resume`. `every source UNUSABLE` leaves `OPER` for `NO_SOURCE`, whatever
  the sub-state, and wins over the other transitions.
- **ENT-STATE-6** Bi-source mode (`heat_cool` with the heat and cool
  sources): `ON(heat_cool)` has phase sub-states (§1.3.3.2); "source of
  `m` available" means at least one of the two sources usable
  (ENT-TYPE-9).

##### 1.3.2.2 INIT state

- **ENT-INIT-1** At `start`, the entity waits until every source has reported
  its first state (`StAC_undiscovered`, `StAC_off`, `StAC_on(m)` or
  `StAC_unusable`, SRC-STATE-1); a source in `UNDISCOVERED` counts. It then goes
  to its stored mode if it can, else `OFF` (choice `resume`), and
  resynchronizes the sources (`apply`).
- **ENT-INIT-2** Stored mode `m` whose source is `UNDISCOVERED`: `OFF`. The source
  is seen for the first time; a stored mode whose source is unknown only
  happens after a configuration change with persistent data, which is not
  recommended.
- **ENT-INIT-3** Shows: the entity is **unavailable** (no mode, no action, no
  target, no setting).

##### 1.3.2.3 OFF state

Every source is asked to be off.

- **ENT-OFF-1** Shows: the entity is available; `hvac_mode` `off`;
  `hvac_action` `off`. Capabilities and settings shown: §1.3.4, §1.3.5.

##### 1.3.2.4 ON(m) state

The source of `m` runs `m`; every other source is asked to be off.

- **ENT-ON-1** Shows: the entity is available; `hvac_mode` `m`;
  `hvac_action` read from the active source (the phase source for
  a bi-source mode). Capabilities and settings shown: those of `m`
  (§1.3.4, §1.3.5).

##### 1.3.2.5 WAITING(m) state

The source of the current mode `m` is `UNUSABLE`; the mode is kept.

- Entered on `StAC_unusable` from the active source.
- Left when the source is back (`StAC_usable` → `ON(m)`: the source
  resynchronizes itself, SRC-STATE-7; its settings are kept, SRC-SET-1), when the
  user asks for another mode, or on a takeover by another source.
- **ENT-WAIT-1** Shows: the entity is available; `hvac_mode` unknown
  (`None`); `hvac_action` unknown (`None`). Capabilities and settings
  shown: those of `m`, as last known (§1.3.4, §1.3.5). The
  `source_unavailable` sensor tells which source is away.

##### 1.3.2.6 NO_SOURCE state

Every source is `UNUSABLE`.

- **ENT-NOSRC-1** Shows: the entity is **unavailable** (no mode, no action, no
  target, no setting). The stored mode is kept for the return.

- Left as soon as a source becomes available (choice `resume`): stored
  mode `off` → `OFF`; source of `m` available → `ON(m)`; otherwise
  `WAITING(m)`. The sources are resynchronized (`apply`).
- **ENT-NOSRC-2** No user event in `NO_SOURCE` (nor in `INIT`): Home
  Assistant does not call a service on an unavailable entity (the call
  is skipped without error, also from an automation).

#### 1.3.3 Mode management

##### 1.3.3.1 Mono-source and bi-source modes

The sources of the modes are configured in §2.1. From that configuration,
each mode is mono-source or bi-source. The following table describes the possible options from the configuration:

| Mode | Configuration | Type | Sources |
|---|---|---|---|
| `heat`, `cool`, `auto`, `dry`, `fan_only` | `<mode>_entity` set | mono-source | its source |
| `heat_cool` | `heat_cool_entity` set | mono-source | its source |
| `heat_cool` | no `heat_cool_entity`, `heat_entity` and `cool_entity` set | **bi-source** | the heat source (phase `heat`) and the cool source (phase `cool`) |
| any | no source | not offered | — |

When `heat_cool` is bi-source (no `heat_cool_entity`), it uses the heat
and cool sources, one per phase:

```mermaid
flowchart LR
    H[heat] --> R["heat source<br/>(heat_entity)"]
    C[cool] --> AC["cool source<br/>(cool_entity)"]
    HC["heat_cool (bi-source)"] -. phase heat .-> R
    HC -. phase cool .-> AC
```

Otherwise (`heat_cool_entity` declared), `heat_cool` is mono-source and
uses its own source, like the other modes.

- **ENT-TYPE-1** Each mode has at most one source entity of its own. A
  source entity can serve several modes.
- **ENT-TYPE-2** At least one mode has a source.
- **ENT-TYPE-3** A source cannot be an Adaptative Climate entity (calls
  would loop).
- **ENT-TYPE-4** A source entity that is loaded and usable must offer the
  mode it serves (`hvac_modes`); a source entity unavailable or unknown
  is not checked (it is checked again when it becomes usable).
- **ENT-TYPE-5** A configuration change reloads the entry.
- **ENT-TYPE-6** Whether a mode is mono-source or bi-source is set by the
  **configuration only** (§2.1): it never changes while running, only
  when the configuration changes (the entry is reloaded). The same mode
  can be either, depending on the configuration (today only `heat_cool`).
- **ENT-TYPE-7** Mono-source mode `m`: the source mode is `m`; the active
  source is the source of `m`.
- **ENT-TYPE-8** Bi-source mode: two sources, one per **phase** (`heat`,
  `cool`); one runs at a time (§1.3.3.2). The source mode is the phase; the
  active source is the source of the phase. Both sources can be the same
  entity (a heat pump switches its own mode).
- **ENT-TYPE-9** A bi-source mode is available as long as at least one of
  its two sources is usable, and both sources offer their phase
  (ENT-HVAC-3). Otherwise, a user request for it is refused
  (ENT-STATE-3).
- **ENT-TYPE-10** In `ON(heat_cool)` bi-source, a mode change made on one
  of the two phase sources (`StAC_on(x)`, `x` = `heat` or `cool`) is a
  takeover: the source wins, and the entity leaves `heat_cool` for the
  **mono-source** mode `x` (`ON(x)`). Examples:
  - phase `heat`, the AC (cool source) is set to `cool` on its remote →
    `ON(cool)`;
  - phase `heat`, a heat pump serving both is set to `cool` on its
    remote → `ON(cool)`;
  - phase `cool`, the radiator (heat source) is turned on in `heat` →
    `ON(heat)`.

  Setting the phase source to the mode it already runs (radiator set to
  `heat` in phase `heat`) changes nothing on the source entity: no event,
  the entity stays `heat_cool`.

##### 1.3.3.2 Bi-source mode: phase management

###### 1.3.3.2.1 Phase management

When `heat_cool` is bi-source, `ON(heat_cool)` has two sub-states. Both
are written with the current phase `p` (`heat` or `cool`):

- `PHASE(p)`: the source of `p` is usable and runs `p`;
- `WAITING_PHASE(p)`: the source of `p` is `UNUSABLE`. The phase `p` is
  kept, and its source gets the request when it comes back (SRC-STATE-4),
  like `WAITING(m)` for a mode.

`p'` is the other phase (`cool` when `p` is `heat`, and the reverse).

The entity chooses the phase from the reference temperature and the targets
(see `wanted` below).

Entering a phase `p` is written `apply(p)`:

- the source of `p` is asked to run `p`, with the settings of that phase
  (`ACtS_request(p)`, `ACtS_settings`);
- every other source that is not off is asked to turn off
  (`ACtS_request(off)`), the source of the other phase included. Except
  when both phases use the same entity (a heat pump): it just switches
  from one mode to the other.

```mermaid
stateDiagram-v2
    direction LR
    state "PHASE(p)" as P
    state "WAITING_PHASE(p)" as W
    state entering <<choice>>
    [*] --> entering : enter ON(heat_cool) / p := wanted(entering)
    entering --> P : [source of p usable] / apply(p)
    entering --> W : [source of p UNUSABLE] / apply(p)
    P --> P : new reading [wanted = p', source of p' usable] / p := p', apply(p)
    P --> P : UtAC_set_settings(targets) [wanted without hysteresis = p', source of p' usable] / p := p', apply(p)
    P --> W : StAC_unusable from the source of p
    W --> P : StAC_usable from the source of p
    W --> P : new reading [wanted = p', source of p' usable] / p := p', apply(p)
    W --> P : UtAC_set_settings(targets) [wanted without hysteresis = p', source of p' usable] / p := p', apply(p)
```

Leaving: both phase sources `UNUSABLE` → `WAITING(heat_cool)` (ENT-PHASE-6);
a change made on a phase source → takeover (ENT-PHASE-4).

"new reading": a new value of the reference, local high or local low
temperature (§1.3.3.2.2): `TStAC_temperature`, or `StAC_temperature` from
the heat or cool source.

- **ENT-PHASE-1** The phase is stored with the mode, and saved across
  restarts.
- **ENT-PHASE-2** The phase is checked on every new reading, and on every
  change of the targets by the user (`wanted`, below). A change of the
  targets by the user ignores the hysteresis (`phase_hysteresis` = 0): the
  user asked for it, the phase follows at once.
- **ENT-PHASE-3** A phase switch is an `apply` of the new phase: its
  source gets the request (confirmed by the source, §1.2.4), the other
  phase source is turned off (confirmed by the source, §1.2.4).
- **ENT-PHASE-4** Leaving the phase from a source (phase source turned off
  or set to another served mode elsewhere) follows the state machine
  (ENT-STATE-4, ENT-TYPE-10).
- **ENT-PHASE-5** A phase switch follows the request confirmation of the
  sources (§1.2.4): the new phase source confirms its mode (retries,
  monitoring, settle time), the other one confirms `off`. The entity does
  not wait nor judge anything meanwhile: a source sends no `StAC_` event
  for a request it confirms (SRC-STATE-3).
- **ENT-PHASE-6** One phase source `UNUSABLE`:
  - the entity stays in `ON(heat_cool)`, in `WAITING_PHASE(p)` if it is the
    source of the current phase;
  - the phase is kept, and its source gets the request when it comes back
    (SRC-STATE-4);
  - the other phase can still start if the temperatures ask for it, and
    if its source is usable.
- **ENT-PHASE-7** Both phase sources `UNUSABLE`: the entity goes to
  `WAITING(heat_cool)` (§1.3.2). It goes back to `ON(heat_cool)` as soon
  as one of them is usable again.
- **ENT-PHASE-8** The entity switches to the other phase only if the
  source of that phase is usable.

###### 1.3.3.2.2 Wanted phase

Phase choice (`wanted`). It uses three temperatures:

- the **reference temperature** (§1.3.5.1);
- the **local high temperature**: the temperature that must be above the
  high target to switch to `cool`;
- the **local low temperature**: the temperature that must be below the
  low target to switch to `heat`.

| Temperatures available (§1.3.5.1) | Local high temperature | Local low temperature |
|---|---|---|
| `temperature_sensor` with a valid value | the sensor | the sensor |
| no valid sensor, both source temperatures | the **lowest** of the two | the **highest** of the two |
| no valid sensor, one source temperature | that one | that one |
| none | none | none |

Hysteresis `h`:

- on a new reading: `h` = `phase_hysteresis` (§2.2);
- on a change of the targets by the user: `h` = 0 ("wanted without
  hysteresis", ENT-PHASE-2).

```mermaid
flowchart TD
    D{entering heat_cool?}
    D -- yes --> F{reference temperature known?}
    F -- yes --> G[phase of the target closest to the reference temperature]
    F -- no --> I[heat or cool source already running, else HEAT]
    D -- no --> L{low target above the high target?}
    L -- yes --> KEEP[phase kept]
    L -- no --> P{current phase}
    P -- HEAT --> B{"local high temperature known<br/>and above high target + h?"}
    B -- yes --> K[COOL]
    B -- no --> H[HEAT: kept]
    P -- COOL --> C{"local low temperature known<br/>and below low target − h?"}
    C -- yes --> H2[HEAT]
    C -- no --> K2[COOL: kept]
```

- **ENT-WANT-1** Entering `heat_cool`: the phase is the one of the target
  closest to the reference temperature. Without reference temperature:
  the heat or cool source already running, else `heat`.
- **ENT-WANT-2** Local high and low temperatures: see the table above.
- **ENT-WANT-3** Switching phase (after entering):
  - in phase `heat`, the phase switches to `cool` when the local high
    temperature is above the high target plus `h`;
  - in phase `cool`, the phase switches to `heat` when the local low
    temperature is below the low target minus `h`;
  - otherwise the phase is kept. This covers: a temperature in between,
    an unknown local temperature, and the low target above the high one
    (after a takeover).
> **Note — why the lowest and the highest:** each source reads near its
> own device, so the two may disagree. Switching to `cool` only when even
> the lowest one is above the high target (and to `heat` only when even
> the highest one is below the low target) means the two sources agree.
> When they contradict each other, the phase is kept: no oscillation.

> **Note — why the hysteresis:** with close targets, or a temperature
> near a target, the phase would switch back and forth (short cycles).
> This wears the compressors and wastes energy. A change of the targets
> by the user is not concerned: the phase follows at once (`h` = 0).

#### 1.3.4 Capabilities management

Capabilities of the modes and temperatures (§1.3.4.1 to §1.3.4.5), then of fan and swing (§1.3.4.6).

##### 1.3.4.1 Principle

- **ENT-CAP-1** The entity builds its own capabilities (modes, range, step,
  targets, options) from the capabilities of its sources (§1.2.2).
  - It uses them whatever the state of the sources.
  - A source in `UNUSABLE` keeps the capabilities it showed last.
- **ENT-CAP-2** The capabilities of a mode `m` come from the source of `m`,
  as it showed them while running in `m`.
  - They are stored per source and per mode (SRC-DATA-1).
  - For a bi-source `heat_cool`, they come from the heat source running in
    `heat`, and from the cool source running in `cool`.

> **Note:** the entity does not need to handle a capability that
> disappears for a while (a device that hides an attribute while it
> restarts, or in some states): the source keeps it until its removal is
> confirmed (SRC-DATA-10, SRC-DATA-11). The entity always reads stable
> capabilities.

A mode is **not discovered yet** when its source has never run in it
(SRC-DATA-1):

- **ENT-CAP-3** The mode is offered as soon as its source offers it (in its
  `hvac_modes`). The entity can switch to it, even if it was never
  discovered.
- **ENT-CAP-4** Until its first activation, the mode has no capability.
  - The entity shows no target and no fan/swing for it.
  - Its range is the Home Assistant default range, 7–35 °C.
  - The targets and fan/swing settings the user sets for it meanwhile are
    kept, but not sent.
- **ENT-CAP-5** When the mode is activated for the first time, the entity
  only sends the mode.
  - No target and no fan/swing setting is sent: the entity does not know
    yet what the source accepts in that mode.
  - The entity never uses the capabilities of another mode to decide what
    to send.
- **ENT-CAP-6** At the first update of the source in that mode, the
  capabilities of the mode are discovered (SRC-DATA-6).
  - The kept targets and fan/swing settings are then sent, within these
    capabilities (range, step, options).
  - Until then, the source runs with its own settings. This happens
    during the settle time.

##### 1.3.4.2 Modes offered

- **ENT-HVAC-1** The entity offers `off` and every configured mode
  (§1.3.3.1).
  - `heat_cool` is offered when it is configured, mono-source or
    bi-source.
  - The list comes from the configuration. It does not change while
    running, so the card always shows the same modes.
- **ENT-HVAC-2** A mode can be in the list without being available. A
  mono-source mode is not available when:
  - its source is `UNDISCOVERED` or `UNUSABLE`;
  - or its source does not offer it (in the `hvac_modes` it showed last,
    §1.2.2).
- **ENT-HVAC-3** A bi-source mode is not available when:
  - **both** sources are `UNDISCOVERED` or `UNUSABLE` (one usable source is
    enough, ENT-PHASE-6);
  - or one of the sources does not offer its phase.
- **ENT-HVAC-4** A mode that is not available:
  - stays in the list;
  - is listed in the `unavailable_modes` attribute;
  - is refused when the user asks for it (ENT-STATE-3).
- **ENT-HVAC-5** When a source does not offer the mode it serves:
  - a warning is logged, and a Repairs issue
    (`<entry>_<mode>_not_supported`) is raised;
  - the issue is removed when the source offers the mode again, and when
    the entry unloads;
  - a source never seen is not judged.

##### 1.3.4.3 Temperature targets used by each mode

The entity keeps three temperature targets:

- **low**: the heating setpoint;
- **high**: the cooling setpoint;
- **T**: the single temperature target.

Each mode uses some of them. It shows them either in the single target
attribute (`temperature`), or in the low/high attributes
(`target_temp_low`, `target_temp_high`).

| Mode | Temperature targets used | Shown as |
|---|---|---|
| `heat` | low | `temperature` |
| `cool` | high | `temperature` |
| `heat_cool` bi-source | low, high | `target_temp_low`, `target_temp_high` |
| `heat_cool` mono-source, source with low/high | low, high | `target_temp_low`, `target_temp_high` |
| `heat_cool` mono-source, source with a single temperature target | T | `temperature` |
| `auto`, source with low/high | low, high | `target_temp_low`, `target_temp_high` |
| `auto`, source with a single temperature target | T | `temperature` |
| `dry`, source with a single temperature target | T | `temperature` |
| `auto` or `dry`, source without temperature target | none | nothing |
| `fan_only` | none | nothing |

- **ENT-FEAT-1** What a mode uses depends on what its source supports in
  that mode. The source is in one of three cases:
  - **with low/high**: the source uses two setpoints, `target_temp_low`
    and `target_temp_high` (ENT-FEAT-2);
  - **with a single temperature target**: the source uses one setpoint,
    `temperature`. It declares the feature `TARGET_TEMPERATURE`, and is
    not "with low/high";
  - **without target**: the source has no temperature setpoint at all, for example a
    dehumidifier in `dry`. It declares neither `TARGET_TEMPERATURE` nor
    `TARGET_TEMPERATURE_RANGE`. The entity then shows no temperature target in that
    mode, and sends none.
- **ENT-FEAT-2** A source is "with low/high" in the mode `m` when it
  declares the feature `TARGET_TEMPERATURE_RANGE`.
  - If it declares only `TARGET_TEMPERATURE_RANGE`, that is enough.
  - If it also declares `TARGET_TEMPERATURE`, one more condition is
    needed: it offers the `heat_cool` mode, or it has already shown
    numeric low/high values while running in `m` (`low_high_seen`,
    SRC-DATA-8).
  - Why: some sources declare both features but only use the single
    temperature target. For example, a template climate with only `set_temperature`.

> **Note — known limitation:** if the device behind a source entity is
> replaced, and the entity id stays the same, the source keeps its
> `low_high_seen`. Only deleting the entry clears it.

- **ENT-FEAT-3** Features declared by the entity:
  - it always declares `TURN_ON` and `TURN_OFF`;
  - it declares `TARGET_TEMPERATURE` when at least one configured mode
    shows a single temperature target (`temperature`);
  - it declares `TARGET_TEMPERATURE_RANGE` when at least one configured
    mode shows low/high;
  - these features do not change with the current mode;
  - the other features of the sources (presets, humidity) are not
    exposed.

##### 1.3.4.4 Step

- **ENT-STEP-1** The entity has one step (`target_temp_step`). It is
  computed from the steps of all the sources, in all their discovered
  modes.
  - The step of the entity is the largest value that divides every step
    of the sources exactly.
  - Examples: steps 0.5 and 1 give 0.5. Steps 0.5 and 0.2 give 0.1.
  - A source without step counts as 0.5 °C (1 °F), as the Home Assistant
    card does.
  - If no step is known yet, the step is 0.5 °C (1 °F).
- **ENT-STEP-2** The step does not change with the state or the mode. So a
  target keeps the same value when the mode changes.

##### 1.3.4.5 Range

- **ENT-RANGE-1** The range of a mode comes from its source.
  - It is the `min_temp` / `max_temp` of the source in that mode, minus the
    offset of the mode (§2.2).
  - For a bi-source `heat_cool`, it is the widest range of the two phases:
    the lowest minimum and the highest maximum.
  - For a mode not discovered yet, it is 7–35 °C (ENT-CAP-4).
- **ENT-RANGE-2** The range shown by the entity:
  - in `ON(m)` and `WAITING(m)`: the range of `m`;
  - in `OFF`: the widest range of all the modes.
- **ENT-RANGE-3** The limits `min_temp` / `max_temp` (§2.5):
  - they can only narrow the range, never widen it;
  - a limit outside the range is ignored;
  - they apply to the reference temperature, before the offset.
- **ENT-RANGE-4** When the entity sends a temperature target to the source
  of a mode, it first brings it into the range of that mode
  (ENT-RANGE-1, ENT-RANGE-3). A value below the minimum is sent as the
  minimum, and a value above the maximum is sent as the maximum. The
  value kept by the entity does not change.
- **ENT-RANGE-5** The entity keeps each temperature target within the
  widest range of all the modes that use it (§1.3.4.3). For example, the
  low target is used by `heat`, and by `heat_cool` and `auto` when their
  source has low/high: the low target can take any value that at least
  one of these modes accepts.
- **ENT-RANGE-6** This way, a value is not lost because one mode cannot
  reach it. For example, with a radiator at 5–30 °C for `heat` and a heat
  pump at 18–30 °C for `heat_cool`, a low target of 14 °C is kept at
  14 °C. The radiator gets 14 °C, and the heat pump gets 18 °C.

##### 1.3.4.6 Fan and swing

The three settings `fan_mode`, `swing_mode` and `swing_horizontal_mode` are
handled the same way. This section only covers their options; the values
kept for each mode are part of the settings (§1.3.5).

- **ENT-FAN-1** The options of a mode for a setting are the options its
  source showed while running in that mode (`fan_modes`, `swing_modes`,
  `swing_horizontal_modes`), when it declares the matching feature in
  that mode.
  - For a bi-source `heat_cool`, they are the options of the source of
    the current phase.
  - A mode not discovered yet has no option (ENT-CAP-4).
- **ENT-FAN-2** The entity declares the features `FAN_MODE`, `SWING_MODE`
  and `SWING_HORIZONTAL_MODE` as soon as at least one configured mode has
  options for that setting. These features do not change with the mode,
  so the card keeps the same size.
- **ENT-FAN-3** The options shown by the entity depend on its state:
  - in `ON(m)` and `WAITING(m)`, it shows the options of `m` (in
    `WAITING(m)`, the ones known last);
  - in `ON(heat_cool)` bi-source, it shows the options of the current
    phase, or the options shared by the two phases when `bi_source_sync`
    is on (ENT-FAN-8);
  - in `OFF`, it shows the options shared by the synchronized modes when
    **every** configured mode is in `sync_modes` (ENT-FAN-6); otherwise,
    it shows none (it does not show the options of the mode `turn_on`
    would start).
- **ENT-FAN-4** When the current mode has no option for a setting, the
  entity shows none for it, and refuses a user request for that setting
  with a clear error.
- **ENT-FAN-5** Values are compared without taking the case into account:
  `Low` and `low` are the same value. Each source gets the value written
  as it writes it. Other names are not matched: `1` is not `low`.
- **ENT-FAN-6** The options shared by the synchronized modes (`sync_modes`,
  §2.6) are the options offered by **all** of them, without taking the
  case into account. They are written as the first synchronized mode
  writes them, in mode order.
- **ENT-FAN-7** Configuration errors of `sync_modes`, each one reported by
  a warning and a Repairs issue, removed once the cause is gone:
  - a synchronized mode whose source does not have a setting at all (a
    radiator without fan): that mode is ignored for that setting, so that
    the others still share their options;
  - `heat_cool` listed while it is bi-source: it is ignored in
    `sync_modes`. A bi-source `heat_cool` is synchronized with
    `bi_source_sync` instead (ENT-FAN-8). `heat_cool` always stays in the
    list of choices of `sync_modes`.
- **ENT-FAN-8** `bi_source_sync` (§2.6) synchronizes the two phases of a
  bi-source `heat_cool`, with the same principle as `sync_modes`:
  - the options shown in `ON(heat_cool)` are the options offered by both
    phase sources (the heat source in `heat`, the cool source in `cool`),
    without taking the case into account;
  - a phase source that does not have a setting at all is reported like
    in ENT-FAN-7, and ignored for that setting.

#### 1.3.5 Settings management

- **ENT-SET-1** `UtAC_set_settings(s)`: the settings are kept by the entity
  for the current mode (for `next_mode` when off).
  - In `ON(m)`, they are sent to the active source (`ACtS_settings(s)`).
  - In `WAITING(m)` and `WAITING_PHASE(p)`, they are sent too: the source
    is `UNUSABLE` and keeps them (SRC-SET-1), then sends them when it
    comes back (SRC-STATE-7).
- **ENT-SET-2** `StAC_settings(s)` from the active source (takeover of a
  setting, or of the mode: SRC-SET-10): the entity adopts them.
- The settings kept per mode, the targets (offsets, steps, ranges, gap)
  and fan/swing memory: to be specified (Part II §4, §5).

##### 1.3.5.1 Reference temperature

The temperature the entity regulates on, and shows as its current
temperature.

```mermaid
flowchart TD
    S{temperature_sensor configured<br/>and its value valid?} -- yes --> V[value of the sensor<br/>converted to the unit of Home Assistant]
    S -- no --> B{bi-source heat_cool?}
    B -- yes --> BR{readings of the heat and cool sources}
    BR -- both --> M[mean of the two readings − their offset]
    BR -- one --> O[that reading − its offset]
    BR -- none --> N
    B -- no --> A{reading of the active source,<br/>in OFF of the last used source,<br/>else of the first usable source?}
    A -- yes --> R[that reading − offset of its mode]
    A -- no --> N[no reference temperature]
```

- **ENT-REF-1** With `temperature_sensor` (§2.2), the reference
  temperature is its value (`TStAC_temperature`), converted to the unit of
  Home Assistant. A value that is not a valid number (`unavailable`,
  `unknown`, text, infinite) is ignored.
- **ENT-REF-2** Without `temperature_sensor`, or while it has no valid
  value, the reference temperature is the current temperature
  (`StAC_temperature`) minus the offset of its mode (§2.2) of:
  - the active source, in `ON(m)` and `WAITING(m)`;
  - the **last used source** in `OFF`: the active source of the last
    `ON(m)`;
  - in `OFF` without last used source (none since start: it is not
    saved across restarts), the **first usable source**, in mode order;
  - in `ON(heat_cool)` and `WAITING(heat_cool)` **bi-source**, from the
    readings of the heat and cool sources (each one minus the offset of
    its mode):
    - both readings available: their **mean**;
    - only one (the other source `UNUSABLE`, or without current
      temperature): that one;
    - none: no reference temperature (ENT-REF-3).
- **ENT-REF-3** No reference temperature (no valid sensor value, and no
  reading from that source: unusable, or no `current_temperature`): the
  entity shows no current temperature
  (`None`). The users of the reference temperature handle its absence
  (for the phase choice: ENT-WANT-1, ENT-WANT-3).
- **ENT-REF-4** The entity shows the reference temperature as its
  `current_temperature`, in every sub-state of `OPER` (in `INIT` and
  `NO_SOURCE` the entity is unavailable).
- **ENT-REF-5** A reading of a source is always taken minus the offset of
  the mode it serves (§2.2): a well set offset makes the source read the
  reference temperature.
- **ENT-REF-6** Bi-source mode without valid sensor:
  - the entity shows the reference temperature, the mean of the two
    source temperatures; it is also used when entering `heat_cool`
    (ENT-WANT-1);
  - to switch phase, the entity uses the local high and low temperatures
    instead (the lowest and the highest of the two, ENT-WANT-2), so that
    two sources that disagree do not make the phase oscillate
    (§1.3.3.2.2).

##### 1.3.5.2 External sensors

- **ENT-EXT-1** For each mode with `<mode>_external_sensor` (§2.2), the
  entity writes the value of the temperature sensor to that entity **on
  every `TStAC_temperature` event**, whatever the state of the entity and
  of the source (even off, even when the mode is not the current one).
- **ENT-EXT-2** The value is converted to the unit of the external sensor
  entity and rounded to its step. It is not written when the external
  sensor entity is unavailable, or when the value is out of its range
  (warning logged). A write error is logged.
- **ENT-EXT-3** The offset of a mode with an external sensor is 0: its
  source regulates on the reference temperature.
- **ENT-EXT-4** While the temperature sensor has a valid value, that value
  is written again every `external_sensor_resend` (§2.3, 900 s by default),
  even unchanged: some devices (thermostatic valves) go back to their own
  sensor when the external temperature is not updated for a while.
- **ENT-EXT-5** Temperature sensor without valid value (`unavailable`,
  `unknown`, `None`, not a number): nothing is written, and the periodic
  rewrite stops, so that the device does not regulate on a stale value: a
  device that watches the updates goes back to its own sensor. Writing
  resumes with the next valid value. The monitoring reports the sensor
  (MON-GEN-6). An external sensor entity cannot be made invalid from Home
  Assistant (a `number` only takes a number in its range).

<a id="2-configuration-new"></a>

## 2. Configuration

### 2.1 Modes

| Option | Type | Default | Effect |
|---|---|---|---|
| `heat_entity` | `climate.*` | none | Source entity of the `heat` mode. |
| `cool_entity` | `climate.*` | none | Source entity of the `cool` mode. |
| `heat_cool_entity` | `climate.*` | none | Source entity of the `heat_cool` mode (mono-source). |
| `auto_entity` | `climate.*` | none | Source entity of the `auto` mode. |
| `dry_entity` | `climate.*` | none | Source entity of the `dry` mode. |
| `fan_only_entity` | `climate.*` | none | Source entity of the `fan_only` mode. |

Declaring `heat_entity` and `cool_entity` gives a **bi-source**
`heat_cool` mode, unless `heat_cool_entity` is also declared: `heat_cool`
is then mono-source, with that source (§1.3.3.1).

### 2.2 Temperature sensor

| Option | Type | Default | Effect |
|---|---|---|---|
| `temperature_sensor` | `sensor.*` | none | Reference temperature: sent to the entity as `TStAC_temperature` (§1.1.2), converted to the unit of Home Assistant. Without it, the readings of the sources are used. |
| `heat_offset` | °C (unit of Home Assistant), -10 to 10 | 0 | Offset of the source of the `heat` mode. |
| `cool_offset` | °C (unit of Home Assistant), -10 to 10 | 0 | Offset of the source of the `cool` mode. |
| `heat_cool_offset` | °C (unit of Home Assistant), -10 to 10 | 0 | Offset of the source of the `heat_cool` mode. |
| `auto_offset` | °C (unit of Home Assistant), -10 to 10 | 0 | Offset of the source of the `auto` mode. |
| `dry_offset` | °C (unit of Home Assistant), -10 to 10 | 0 | Offset of the source of the `dry` mode. |
| `fan_only_offset` | °C (unit of Home Assistant), -10 to 10 | 0 | Offset of the source of the `fan_only` mode. |
| `heat_external_sensor` | `number.*` / `input_number.*` | none | External temperature input of the source of the `heat` mode (§1.3.5.2). Needs `temperature_sensor`. |
| `cool_external_sensor` | `number.*` / `input_number.*` | none | External temperature input of the source of the `cool` mode (§1.3.5.2). Needs `temperature_sensor`. |
| `heat_cool_external_sensor` | `number.*` / `input_number.*` | none | External temperature input of the source of the `heat_cool` mode (§1.3.5.2). Needs `temperature_sensor`. |
| `auto_external_sensor` | `number.*` / `input_number.*` | none | External temperature input of the source of the `auto` mode (§1.3.5.2). Needs `temperature_sensor`. |
| `dry_external_sensor` | `number.*` / `input_number.*` | none | External temperature input of the source of the `dry` mode (§1.3.5.2). Needs `temperature_sensor`. |
| `fan_only_external_sensor` | `number.*` / `input_number.*` | none | External temperature input of the source of the `fan_only` mode (§1.3.5.2). Needs `temperature_sensor`. |
| `phase_hysteresis` | °C (unit of Home Assistant), ≥ 0 | 1 | Bi-source mode: margin beyond a target before the phase switches (ENT-WANT-3), to avoid short cycles. 0: switch as soon as the target is passed. |

Offset (`<mode>_offset`): how much warmer than the reference temperature
the source of that mode reads (negative: colder). A reading of that
source minus the offset is a reference temperature; a target sent to it
is the target plus the offset. The offset belongs to the mode, not to the
source entity: an entity serving two modes can have two offsets. An
external sensor forces it to 0 (§1.3.5.2).

External sensor (`<mode>_external_sensor`): some source devices can
regulate with an external temperature (a thermostatic valve with an
"external temperature" number entity, a thermostat following a probe).
That entity gets the reference temperature, so the source regulates on
it. It needs `temperature_sensor` (a configuration without it is
refused), and the offset of that mode is then 0.

### 2.3 Timers and durations

| Option | Type / range | Default | Effect |
|---|---|---|---|
| `capability_rem_confirmation` | seconds, ≥ 0 | 60 | How long a capability no longer shown by a source entity is kept before it is removed (SRC-DATA-10). 0: removed at once. |
| `request_confirmation_timer` | seconds, > 0 | 30 | How long a source waits for its source entity to show the state asked before the monitoring reports it out of sync (§1.2.4). |
| `settle_timer` | seconds, > 0 | 12 | After the source entity enters a mode asked, how long the settings it shows are ignored (§1.2.4, §1.2.5). 12 s by default: integrations that poll their device usually refresh right after a command, then at most every 10 s (Home Assistant debounce of refresh requests); a value reported late by the device arrives within that time, plus a margin. |
| `external_sensor_resend` | seconds, > 0 | 900 | How often the value of the temperature sensor is written again to the external sensors, even unchanged (ENT-EXT-4). 15 min by default: a margin for devices that need an update at least every 30 min, without loading battery devices. |
| `request_retry_timer` | seconds, ≥ `request_confirmation_timer` | 300 | How long a source waits, after a request confirmation timed out, before sending the state asked again (§1.2.4). |

- **CFG-TIMER-1** `request_retry_timer` must be greater than or equal to
  `request_confirmation_timer`: a configuration that breaks it is refused.

### 2.4 Monitoring

| Option | Type / range | Default | Effect |
|---|---|---|---|
| `monitoring_gap` | °C (unit of Home Assistant), > 0 | 2 | Largest gap between two temperature readings before it is a problem (MON-GEN-3). |
| `monitoring_duration` | seconds, ≥ 0 | 900 | How long a problem lasts before the monitoring reports it (MON-GEN-2; 30 s at least for a setting not shown). 0: at once. |

### 2.5 Temperature limits

| Option | Type | Default | Effect |
|---|---|---|---|
| `min_temp` | °C (unit of Home Assistant) | none | Lowest temperature of the entity: narrows the range of the sources (ENT-RANGE-3). |
| `max_temp` | °C (unit of Home Assistant) | none | Highest temperature of the entity: narrows the range of the sources (ENT-RANGE-3). |

- **CFG-LIM-1** `min_temp` must be lower than `max_temp`: a configuration
  that breaks it is refused.

### 2.6 Fan and swing

| Option | Type | Default | Effect |
|---|---|---|---|
| `sync_modes` | list of modes | empty | The modes listed share their fan and swing values: a fan speed chosen in one of them is used in the others (ENT-FAN-6). A mode listed without a source is ignored; a bi-source `heat_cool` listed is reported (ENT-FAN-7). |
| `bi_source_sync` | boolean | off | Bi-source `heat_cool` only: its two phases share their fan and swing values, and show the options offered by both (ENT-FAN-8). |

<a id="3-monitoring-new"></a>

## 3. Monitoring

| Problem | Up (raised) | Down (cleared) |
|---|---|---|
| Setting not shown (per source and setting, MON-GEN-2) | the source entity in `ON(m)` shows another setting (target, fan, swing) than the one sent, outside the settle time and the request confirmation, for `monitoring_duration` (§2.4, 900 s by default, 30 s at least) | the source entity shows the setting sent |
| Temperature gap: sensor vs source (per reading, MON-GEN-3) | the temperature sensor and a source reading differ by more than `monitoring_gap`, for `monitoring_duration` (§2.4) | the gap is back below `monitoring_gap` |
| Temperature gap: source vs source (per pair of readings, MON-GEN-3) | two readings of different source entities differ by more than `monitoring_gap`, for `monitoring_duration` | the gap is back below `monitoring_gap` |
| Temperature sensor without valid value (MON-GEN-6) | `temperature_sensor` is configured and has no valid value (`unavailable`, `unknown`, not a number) for `monitoring_duration` (§2.4) | the sensor has a valid value again |
| Source out of sync (per source) | timeout of a request confirmation: the source entity does not show the state asked after `request_confirmation_timer` (SRC-REQ-6) | the source entity shows the state asked; or the retries stop: new request, `SEtS_unavailable` / `SEtS_unknown`, change of the source entity during the retry wait (SRC-REQ-8) |

- **MON-GEN-1** Source out of sync: up at the first timeout of a request
  confirmation (§1.2.4), and stays up during the retries (every `request_retry_timer`).
  Down on every exit of the confirmation or the retry wait: the source
  entity shows the state asked, a new request (a new confirmation
  starts; up again at its timeout if needed), `SEtS_unavailable` / `SEtS_unknown`, or a change
  of the source entity during the retry wait (followed as a takeover).

- **MON-GEN-2** Setting not shown: the source entity shows another setting
  (target, fan, swing) than the one sent to it (§1.2.5), which is not a
  takeover. Up after `monitoring_duration` (30 s at least: a device may
  take that long to show it); down when the source entity shows the
  setting sent.
- **MON-GEN-3** Temperature gaps: a source that does not read the
  reference temperature keeps the room away from the target. Compared:
  the temperature sensor (`TStAC_temperature`) with each source reading,
  and the readings of two **different** source entities with each other.
  Up when a gap stays above `monitoring_gap` for `monitoring_duration`;
  down when it is back below.
- **MON-GEN-4** Readings compared:
  - each source gives one reading: its current temperature
    (`StAC_temperature`) minus the offset of its mode (§2.2). A well set
    offset clears the problem;
  - a source entity serving two modes (an AC for `cool` and `dry`) gives
    one reading if both modes have the same offset. With different
    offsets, it gives one reading per offset; these readings come from the
    same thermometer, so they are not compared with each other (only with
    the sensor and the other source entities);
  - a source `UNUSABLE`, or without current temperature, gives no
    reading.
- **MON-GEN-5** The readings of sources that are `OFF` are compared too.
- **MON-GEN-6** Temperature sensor without valid value: up when
  `temperature_sensor` (§2.2) has no valid value for `monitoring_duration`;
  down as soon as it has one again. Meanwhile the external sensors are not
  written (ENT-EXT-5) and the reference temperature comes from the
  sources (ENT-REF-2).
---

# Part II — Old spec

Elements are removed from here as they move to Part I: what is left is
still to be specified.

## Table of contents (old)

- [1. Overall behavior](#1-overall-behavior-1)
  - [1.1 Principles](#11-principles)
  - [1.6 Restart and reload](#16-restart-and-reload)
  - [1.7 Open questions — overall](#17-open-questions--overall)
- [2. Managed entities](#2-managed-entities)
  - [2.1 Configuration](#21-configuration)
  - [2.2 Entities created per entry](#22-entities-created-per-entry)
  - [2.3 Climate entity](#23-climate-entity)
  - [2.4 Binary sensors](#24-binary-sensors)
  - [2.5 Other outputs](#25-other-outputs)
- [3. Management of sources](#3-management-of-sources)
  - [3.7 Active source away](#37-active-source-away)
  - [3.8 Commands and errors](#38-commands-and-errors)
- [4. Temperature management](#4-temperature-management)
  - [4.1 The three targets](#41-the-three-targets)
  - [4.2 Which target each mode uses](#42-which-target-each-mode-uses)
  - [4.3 Step](#43-step)
  - [4.5 Offset](#45-offset)
  - [4.6 First targets](#46-first-targets)
  - [4.7 Setting targets (user)](#47-setting-targets-user)
  - [4.9 Following the active source](#49-following-the-active-source)
  - [4.10 What the entity shows](#410-what-the-entity-shows)
- [5. Fan / swing management](#5-fan--swing-management)
  - [5.1 What is shown](#51-what-is-shown)
  - [5.2 Memory](#52-memory)
- [6. Monitoring](#6-monitoring)
  - [6.3 Problem lifecycle](#63-problem-lifecycle)
  - [6.4 Target gap sensor](#64-target-gap-sensor)
  - [6.5 Source unavailable sensor](#65-source-unavailable-sensor)
- [7. Trash (what goes nowhere)](#7-trash-what-goes-nowhere)
- [8. Open questions index](#8-open-questions-index)

## 1. Overall behavior

### 1.1 Principles

- **G-4 — Targets and settings belong to the entity.** Switching mode keeps
  them; the source of the new mode receives them.
- **G-12** One mode change at a time (lock), phase switches included.

### 1.6 Restart and reload

What is saved in the restore data of the climate entity:

| Data | Saved | Restored as |
|---|---|---|
| Targets (single, low, high) | ✅ | Kept, then the gap is applied. |
| Fan/swing memory per mode (or `sync`) | ✅ | Kept, configured modes only. |
| `last_on_mode` (target of `turn_on`) | ❌ | Lost → first configured mode. ❓ Q-1 |
| Monitoring problem timers | ❌ | Lost: durations restart from zero. |

- **G-15** A reload of the entry (options flow, YAML change) is a restart.
  A stored mode no longer configured → `off`. (Mode and phase saved,
  restart: Part I ENT-STATE-1, §1.3.2.2.)

### 1.7 Open questions — overall

- ❓ **Q-1** `last_on_mode` is not saved: after a restart, `turn_on` goes
  to the first configured mode, and while off the entity shows the targets
  of that first mode (when it has no low/high). Save it?

---

## 2. Managed entities

### 2.1 Configuration

| Option | Type / range | Default | Effect |
|---|---|---|---|
| `name` | string, unique | — | Entry title, entity name; identifies YAML entries. |
| `min_gap` | ≥ 1 | 1 | Gap between low and high targets. |

- **E-1 Validation** (UI and YAML): YAML names unique. (Mode sources:
  Part I §1.3.3.1; external sensors: Part I §2.2; limits: Part I §2.5.)

### 2.2 Entities created per entry

```mermaid
flowchart LR
    subgraph Entry["Config entry 'Living room'"]
        C[climate.living_room]
        M[binary_sensor.living_room_monitoring<br/>device_class problem]
        G[binary_sensor.living_room_target_gap]
        U[binary_sensor.living_room_source_unavailable<br/>device_class problem]
    end
    S1[climate.heater] -. source heat .-> C
    S2[climate.ac] -. source cool / dry .-> C
    T[sensor.room_temp] -. reference temp .-> C
    C -- writes reference temp --> X[number.trv_external_temp]
    C --> M & G & U
```

### 2.3 Climate entity

- **E-4 Features:** Part I §1.3.4.

Properties per state:

| Property | Off | On(m) | On(m), source away | Combined HC |
|---|---|---|---|---|
| `temperature` / `target_temp_low` / `target_temp_high` | low+high if the entity has low/high, else targets of `next_mode` | per mode (§4.2) | as m | low + high |
| fan / swing options | shared options if every mode synced, else none | source of m | source of m (known) | phase source |
| fan / swing value | memory if every mode synced, else none | active source | memory of m | phase source |

Extra attributes:

| Attribute | Content |
|---|---|
| `active_entity_id` | Active source, or `None`. |
| `mode_entity_ids` | `{mode: source}` as configured. |
| `unavailable_modes` | Modes whose source is unavailable or does not offer the mode. |
| `foreign_modes` | `{source: mode}` of sources running a mode they do not serve. |
| `saved_targets` | `{temperature, target_temp_low, target_temp_high}` as kept (before offset and source step). |
| `saved_settings` | `{mode: {fan_mode, swing_mode, swing_horizontal_mode}}` (not recorded in history). |

### 2.4 Binary sensors

| Sensor | On when | Attributes | Detail |
|---|---|---|---|
| `_monitoring` | a problem lasted its duration | `max_gap`, `problems` | §6.1 |
| `_target_gap` | a shown target differs from the kept one | `gaps` | §6.4 |
| `_source_unavailable` | a source of the stored mode is unavailable (off: never) | `entity_ids` | §6.5 |

All three are always available.

### 2.5 Other outputs

- **E-7 Event** `adaptative_climate_problem` on each problem start/end.
- **E-8 Logs:** warning on foreign mode (each entry into it and at start),
  unsupported mode, failed send after retry, problem start; info on
  problem end.

---

## 3. Management of sources

### 3.7 Active source away

- **S-17** `turn_on` while `WAITING(m)` does nothing (the mode is on).
  (Rest of the behavior: Part I §1.3.2.5.)

### 3.8 Commands and errors

- **S-19** Every call to a source is a blocking service call; any error is
  raised as `HomeAssistantError` to the caller.

---

## 4. Temperature management

### 4.1 The three targets

The entity keeps three targets, in reference temperature, on its own step:

```mermaid
flowchart LR
    subgraph Store["Targets kept by the entity (saved_targets)"]
        L[low = heating setpoint]
        Hi[high = cooling setpoint]
        S[single]
    end
    L -- "≥ min_gap below" --- Hi
```

- **T-1** low and high are shared by heat, cool, heat/cool and auto with
  low/high. single is shared by dry and auto without low/high.
- **T-2** Targets are kept across restarts, and while off, in fan only,
  in a mode without target, while the source is away.

### 4.2 Which target each mode uses

| Mode | Source gets | Entity shows `temperature` | `target_temp_low` | `target_temp_high` |
|---|---|---|---|---|
| heat | `temperature` ← low | low | — | — |
| cool | `temperature` ← high | high | — | — |
| heat_cool (own source with low/high) | low, high | — | low | high |
| heat_cool (own source without low/high) | `temperature` ← single | single | — | — |
| heat_cool bi-source, phase heat | heat source `temperature` ← low | — | low | high |
| heat_cool bi-source, phase cool | cool source `temperature` ← high | — | low | high |
| auto, source with low/high | low, high | — | low | high |
| auto, source with single only | `temperature` ← single | single | — | — |
| auto / dry, source without target | nothing | — | — | — |
| dry, source with single | `temperature` ← single | single | — | — |
| fan_only | nothing | — | — | — |
| off, entity has low/high | — | — | low | high |
| off, entity has no low/high | — | as `next_mode` | as `next_mode` | as `next_mode` |

- ❓ **Q-8** heat_cool with its own source **without** low/high uses the
  single target (shared with dry/auto), not low/high. OK?

### 4.3 Step

- **T-4** Every target of the entity is on the step of the entity (Part I
  ENT-STEP-1), whatever sets it. Each source gets the target rounded to
  **its own** step.

### 4.5 Offset

- **T-8** Offset: Part I §2.2. Still to specify here: the target sent is
  rounded to the step of the source and kept in its range; the targets and
  ranges read from it are minus the offset.

### 4.6 First targets

```mermaid
flowchart TD
    A[First usable source] --> B{single known?}
    B -- no --> C[single = active source target, else any source target,<br/>else middle of range]
    B -- yes --> D
    C --> D{low and high known?}
    D -- yes --> X[done]
    D -- no --> E{heat_cool source has low/high values?}
    E -- yes --> F[take them]
    E -- no --> G[low = heat source target, high = cool source target]
    G --> H[missing: another source low/high pair, else single ∓ 1]
    F --> I[apply gap]
    H --> I
```

### 4.7 Setting targets (user)

- **T-11** `set_temperature(temperature)` sets low in heat, high in cool,
  single otherwise; off → the mode of `next_mode`. `target_temp_low/high`
  set low/high. With `hvac_mode`: targets are set for that mode, then the
  mode is switched.
- **T-12** Gap: low ≥ `min_gap` below high. The target just set stays, the
  other moves (outward, on step, in its range). If it cannot (range), the
  target just set gives way. Both set: high moves.
- **T-14** The state is always written after a `set_temperature` (even
  unchanged), so the card drops the value it shows.

### 4.9 Following the active source

- **T-21** Steady: a target changed on the source becomes the entity
  target (`value − offset`, on entity step), even outside the entity
  limits. The other target moves to keep the gap; the taken one never
  gives way.

### 4.10 What the entity shows

- **T-23** A target the active source (even away) gets is shown clamped to
  **that source's** range (without limits). Others: widest range of the
  sources they go to (with limits), else the entity range.
- **T-24** A shown target differing from the kept one → `target_gap`
  sensor (§6.4).

---

## 5. Fan / swing management

Three settings handled the same way: `fan_mode`, `swing_mode`,
`swing_horizontal_mode`.

### 5.1 What is shown

Options and features: Part I §1.3.4.6. Values shown:

| State | Value |
|---|---|
| On(m) (bi-source: phase source) | active source |
| On(m), source away | memory of m |
| Off, every mode in `sync_modes` | shared memory |
| Off, otherwise | none |

### 5.2 Memory

```mermaid
flowchart LR
    subgraph Memory["saved_settings (persisted)"]
        K1["heat: {fan, swing, h-swing}"]
        K2["fan_only: {...}"]
        K3["sync: {...} shared by cool, dry"]
    end
    SRC[active source] -- "observe: change within mode" --> Memory
    SRC -- "entering: fill only unknown" --> Memory
    U[user while no source runs] -- remember --> Memory
    Memory -- "on activation: send if different" --> NEW[source of new mode]
```

- **F-2** Key: the mode, or `sync` for modes in `sync_modes` (with a
  source). Bi-source `heat_cool` uses the keys `heat` and `cool`.
- **F-3** Entering a mode: only fills settings not yet remembered (first
  use keeps the source's settings). Within a mode: every change is
  remembered, wherever it comes from (user via entity, remote).
- **F-5** Synced: a value is remembered only if every synced source that
  has the setting offers it. A value only some offer (`turbo`) can be used
  but is not remembered. At send, a shared value no longer common is
  replaced by the source's current value.

---

## 6. Monitoring

### 6.3 Problem lifecycle

```mermaid
stateDiagram-v2
    direction LR
    state "Seen" as S
    state "Reported" as R
    [*] --> S : condition true (since = now)
    S --> [*] : condition false (forgotten)
    S --> R : lasted its duration → warning log + event started
    R --> [*] : condition false → info log + event ended
```

- **M-3** A problem that goes away starts from zero when it comes back,
  and after a restart.
- **M-4** Checked on every source/sensor update, when the target
  mismatches change, and at the time the next seen problem is due.
- **M-5** Event data: `entry_id, name, entity_id, status, message, problem`.

### 6.4 Target gap sensor

- **M-6** On while a target is shown otherwise than kept (T-23). `gaps`:
  `[{attribute, saved, shown}]`. Not a problem: informative.

### 6.5 Source unavailable sensor

- **M-7** On while a source of the stored mode is unavailable: the active
  one (away), either source of bi-source heat_cool. Off while the mode is off.
  `entity_ids` lists them.

---

## 7. Trash (what goes nowhere)

Things that exist but have no home in the functional spec. To keep, move
or delete.

- **README "Structure" section** is stale (no `engine/`, `known.py`,
  `binary_sensor.py`).
- **YAML import mechanics**: name = identity, YAML wins, an entry removed
  from YAML is deleted, imported entries have no options. Options flow
  replaces the whole data. → Configuration chapter?
- **Compatibility shim** for HA < 2026.11 (`temperature_unit` etc. without
  `native_`).
- **`force_update` trick** after `set_temperature` (T-14): a frontend
  workaround, not behavior.
- **`<mode>_offset` for `fan_only`** (and dry/auto without target): only
  affects readings (current temperature, monitoring). Useful or noise?
- **`Sources.features()` records into the known capabilities** (side
  effect in a reader).
- **Several `Sources` instances** (climate, monitoring, external sensor
  writer) over the same coordinator.
- **`self_reference` check** (a source cannot be one of our entities).
- **Translations** en/fr, `strings.json`.
- **TODO leftovers**: auto mode doing its own switching (option),
  humidity management, "test en 20??".
- **Obsolete with the stored mode** (Part I ENT-STATE-1): reading the
  mode from the sources, `last_on_source`, "first running source in mode
  order", the saved `waiting` tuple and `heat_cool` flag (replaced by the
  stored mode and phase), `switching_to` (replaced by the request
  confirmation, Part I §1.2.4).
---

## 8. Open questions index

| # | Section | Topic |
|---|---|---|
| Q-1 | 1.7 | Save `last_on_mode` across restarts? |
| Q-8 | 4.2 | heat_cool own source without low/high uses the single target. |
