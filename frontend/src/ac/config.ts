// The configuration of the card (CARD_SPEC.md §8, CARD_ARCHITECTURE.md CARD-ARCH-8).

import {
  array,
  assert,
  boolean,
  enums,
  literal,
  optional,
  string,
  type as looseObject,
  union,
} from "superstruct";
import type { HomeAssistant } from "../ha/types";
import { acClimateEntities } from "./registry";

export const CARD_TYPE = "adaptative-climate-card";

export const LIST_TYPES = [
  "ac-preset-modes",
  "ac-fan-modes",
  "ac-swing-modes",
  "ac-swing-horizontal-modes",
] as const;
export type ListType = (typeof LIST_TYPES)[number];

export interface DeviceFeatureConfig {
  type: "ac-device";
}

export interface HvacModesFeatureConfig {
  type: "ac-hvac-modes";
  hvac_modes?: string[];
}

export interface ListFeatureConfig {
  type: ListType;
  style?: "dropdown" | "icons";
}

export type FeatureConfig = DeviceFeatureConfig | HvacModesFeatureConfig | ListFeatureConfig;

export const MONITORING_DISPLAYS = ["always", "compact", "errors", "hidden"] as const;
export type MonitoringDisplay = (typeof MONITORING_DISPLAYS)[number];

export interface AdaptativeClimateCardConfig {
  type: string;
  entity: string;
  name?: string;
  show_current_as_primary?: boolean;
  monitoring?: MonitoringDisplay;
  features?: FeatureConfig[];
  // Set by the dashboard, read for the layout of the lists (CARD-ARCH-10)
  grid_options?: { rows?: number | "auto" };
}

// The features, in the order the editor proposes them (CARD-CONF-4)
export const FEATURE_ORDER: FeatureConfig[] = [
  { type: "ac-device" },
  { type: "ac-hvac-modes" },
  ...LIST_TYPES.map((type) => ({ type })),
];

// Loose objects (`type`): the dashboard adds its own keys (grid_options,
// view_layout, visibility...), which are not ours to refuse.
const featureStruct = union([
  looseObject({ type: literal("ac-device") }),
  looseObject({ type: literal("ac-hvac-modes"), hvac_modes: optional(array(string())) }),
  looseObject({ type: enums(LIST_TYPES), style: optional(enums(["dropdown", "icons"])) }),
]);

const configStruct = looseObject({
  type: string(),
  entity: string(),
  name: optional(string()),
  show_current_as_primary: optional(boolean()),
  monitoring: optional(enums(MONITORING_DISPLAYS)),
  features: optional(array(featureStruct)),
});

/** Throws on a wrong value: the dashboard shows the error in the card (CARD-CONF-6). */
export function checkConfig(config: unknown): AdaptativeClimateCardConfig {
  assert(config, configStruct);
  if (config.entity.split(".")[0] !== "climate") {
    throw new Error(`${config.entity}: not a climate entity`);
  }
  return config as AdaptativeClimateCardConfig;
}

/** The first AC entity, without feature, as the thermostat card (CARD-CONF-3). */
export function stubConfig(hass: HomeAssistant): AdaptativeClimateCardConfig {
  return {
    type: `custom:${CARD_TYPE}`,
    entity: acClimateEntities(hass)[0] ?? "",
  };
}
