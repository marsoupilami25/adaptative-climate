// The world of the card, for its tests: a `hass` object and AC entities, as the
// frontend of Home Assistant gives them (CARD_TESTS.md).

import type { AcClimateEntity } from "../../frontend/src/ac/entity";
import type { HomeAssistant } from "../../frontend/src/ha/types";

export const AC = "climate.living_room";
export const HEATER = "climate.radiator";
export const AIRCON = "climate.aircon";
export const SOURCES = "binary_sensor.living_room_monitoring_sources";
export const TEMPERATURES = "binary_sensor.living_room_monitoring_temperatures";

// supported_features of a climate entity
export const TARGET = 1;
export const RANGE = 2;
export const FAN = 8;
export const PRESET = 16;
export const SWING = 32;
export const SWING_H = 512;

export interface Call {
  domain: string;
  service: string;
  data?: Record<string, unknown>;
}

/** An AC entity: a climate entity with the attributes of SPEC.md §2.2. */
export function acEntity(state = "heat", attributes: Record<string, unknown> = {}): AcClimateEntity {
  return {
    entity_id: AC,
    state,
    last_changed: "",
    last_updated: "",
    context: { id: "", parent_id: null, user_id: null },
    attributes: {
      friendly_name: "Living room",
      hvac_modes: ["off", "heat", "cool"],
      supported_features: TARGET,
      min_temp: 7,
      max_temp: 35,
      target_temp_step: 0.5,
      temperature: 21,
      current_temperature: 20,
      active_entity_id: state === "heat" ? HEATER : state === "cool" ? AIRCON : null,
      phase: null,
      mode_entity_ids: { heat: HEATER, cool: AIRCON },
      unavailable_modes: [],
      foreign_modes: {},
      ...attributes,
    },
  } as unknown as AcClimateEntity;
}

function entity(entityId: string, state: string, attributes: Record<string, unknown> = {}) {
  return { entity_id: entityId, state, last_changed: "", last_updated: "", context: { id: "", parent_id: null, user_id: null }, attributes };
}

const NAMES: Record<string, string> = {
  [AC]: "Living room",
  [HEATER]: "Radiator",
  [AIRCON]: "Air conditioner",
};

/**
 * A `hass` object with the AC entity, its two sources and its two monitoring
 * sensors. `calls` records the service calls; a call for a mode in
 * `refused` fails, as the integration refuses it.
 */
export function fakeHass(
  stateObj: AcClimateEntity = acEntity(),
  options: { language?: string; sources?: string; temperatures?: string; heater?: string; aircon?: string } = {},
): HomeAssistant & { calls: Call[] } {
  const calls: Call[] = [];
  const states: Record<string, unknown> = {
    [AC]: stateObj,
    [HEATER]: entity(HEATER, options.heater ?? "off", { friendly_name: "Radiator" }),
    [AIRCON]: entity(AIRCON, options.aircon ?? "off", { friendly_name: "Air conditioner" }),
    [SOURCES]: entity(SOURCES, options.sources ?? "off"),
    [TEMPERATURES]: entity(TEMPERATURES, options.temperatures ?? "off"),
  };
  const registry = (entityId: string, extra: Record<string, unknown> = {}) => ({
    entity_id: entityId,
    labels: [],
    ...extra,
  });
  const hass = {
    calls,
    states,
    entities: {
      [AC]: registry(AC, { platform: "adaptative_climate", device_id: "dev1" }),
      [SOURCES]: registry(SOURCES, { platform: "adaptative_climate", device_id: "dev1", translation_key: "monitoring_sources" }),
      [TEMPERATURES]: registry(TEMPERATURES, { platform: "adaptative_climate", device_id: "dev1", translation_key: "monitoring_temperatures" }),
      [HEATER]: registry(HEATER, { platform: "demo" }),
      [AIRCON]: registry(AIRCON, { platform: "demo" }),
    },
    language: options.language ?? "en",
    locale: { language: options.language ?? "en", number_format: "language", time_format: "language" },
    config: { unit_system: { temperature: "°C" } },
    localize: (key: string) => key,
    formatEntityState: (obj: { attributes: Record<string, unknown>; state: string }, state?: string) => `state:${state ?? obj.state}`,
    formatEntityAttributeValue: (_obj: unknown, attribute: string, value?: unknown) => `${attribute}:${value}`,
    formatEntityAttributeName: (_obj: unknown, attribute: string) => `name:${attribute}`,
    formatEntityName: (obj: { entity_id: string }, name?: string) => name ?? NAMES[obj.entity_id] ?? obj.entity_id,
    callService: async (domain: string, service: string, data?: Record<string, unknown>) => {
      calls.push({ domain, service, data });
      return undefined;
    },
    callWS: async () => undefined,
    connection: {},
  };
  return hass as unknown as HomeAssistant & { calls: Call[] };
}
