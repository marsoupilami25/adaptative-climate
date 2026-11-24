// The four lists (CARD_SPEC.md §5.2): what each one reads, sets and shows.
// Icons of the values: those of homeassistant/components/climate/icons.json
// (Home Assistant core, Apache 2.0), as Home Assistant shows them for a climate
// entity, with common synonyms and numbers (CARD-LIST-6). ha-attribute-icon is
// loaded on demand only (CARD-ARCH-4).

import {
  mdiAccountArrowRight,
  mdiArrowAll,
  mdiArrowCollapseHorizontal,
  mdiArrowCollapseVertical,
  mdiArrowDown,
  mdiArrowExpandHorizontal,
  mdiArrowLeft,
  mdiArrowLeftRight,
  mdiArrowOscillating,
  mdiArrowOscillatingOff,
  mdiArrowRight,
  mdiArrowUp,
  mdiArrowUpDown,
  mdiBed,
  mdiCircleOffOutline,
  mdiFan,
  mdiFanAuto,
  mdiFanOff,
  mdiHome,
  mdiLeaf,
  mdiMotionSensor,
  mdiNumeric0CircleOutline,
  mdiNumeric1CircleOutline,
  mdiNumeric2CircleOutline,
  mdiNumeric3CircleOutline,
  mdiNumeric4CircleOutline,
  mdiNumeric5CircleOutline,
  mdiNumeric6CircleOutline,
  mdiNumeric7CircleOutline,
  mdiNumeric8CircleOutline,
  mdiNumeric9CircleOutline,
  mdiRocketLaunch,
  mdiSofa,
  mdiSpeedometer,
  mdiSpeedometerMedium,
  mdiSpeedometerSlow,
  mdiTarget,
  mdiTuneVariant,
  mdiWeatherWindy,
} from "@mdi/js";
import { ClimateEntityFeature } from "../ha/data/climate";
import type { ListType } from "./config";

export interface ListKind {
  attribute: string; // the current value
  options: string; // the values offered
  service: string; // climate.<service>, with { <attribute>: value }
  feature: number; // the supported feature
  icon: string; // the icon of the closed list
  offIcon?: string; // its icon when the current mode offers no option (CARD-LIST-5)
  values: Record<string, string>; // the icons of the values, by normalized name
}

// The same icon for several names
const named = (icon: string, ...names: string[]) => Object.fromEntries(names.map((name) => [name, icon]));

export const LISTS: Record<ListType, ListKind> = {
  "ac-preset-modes": {
    attribute: "preset_mode",
    options: "preset_modes",
    service: "set_preset_mode",
    feature: ClimateEntityFeature.PRESET_MODE,
    icon: mdiTuneVariant,
    values: {
      ...named(mdiMotionSensor, "activity"),
      ...named(mdiAccountArrowRight, "away", "vacation", "holiday"),
      ...named(mdiRocketLaunch, "boost", "turbo"),
      ...named(mdiSofa, "comfort"),
      ...named(mdiLeaf, "eco", "economy"),
      ...named(mdiHome, "home"),
      ...named(mdiBed, "sleep", "night"),
      ...named(mdiCircleOffOutline, "none", "off"),
    },
  },
  "ac-fan-modes": {
    attribute: "fan_mode",
    options: "fan_modes",
    service: "set_fan_mode",
    feature: ClimateEntityFeature.FAN_MODE,
    icon: mdiFan,
    offIcon: mdiFanOff,
    values: {
      ...named(mdiFanAuto, "auto", "automatic"),
      ...named(mdiWeatherWindy, "diffuse"),
      ...named(mdiTarget, "focus"),
      ...named(mdiSpeedometer, "high", "max", "maximum", "turbo", "powerful", "strong", "boost"),
      ...named(mdiSpeedometerSlow, "low", "min", "minimum", "quiet", "silent", "silence", "mute"),
      ...named(mdiSpeedometerMedium, "medium", "middle", "mid", "med", "normal"),
      ...named(mdiFanOff, "off"),
      ...named(mdiFan, "on"),
    },
  },
  "ac-swing-modes": {
    attribute: "swing_mode",
    options: "swing_modes",
    service: "set_swing_mode",
    feature: ClimateEntityFeature.SWING_MODE,
    icon: mdiArrowOscillating,
    offIcon: mdiArrowOscillatingOff,
    values: {
      ...named(mdiArrowAll, "both", "all", "3d"),
      ...named(mdiArrowLeftRight, "horizontal", "left_right"),
      ...named(mdiArrowOscillatingOff, "off", "stop", "fixed"),
      ...named(mdiArrowOscillating, "on", "auto", "swing"),
      ...named(mdiArrowUpDown, "vertical", "up_down", "updown"),
      ...named(mdiArrowUp, "top", "up", "highest"),
      ...named(mdiArrowDown, "bottom", "down", "lowest"),
      ...named(mdiArrowCollapseVertical, "middle", "mid", "center", "centre"),
    },
  },
  "ac-swing-horizontal-modes": {
    attribute: "swing_horizontal_mode",
    options: "swing_horizontal_modes",
    service: "set_swing_horizontal_mode",
    feature: ClimateEntityFeature.SWING_HORIZONTAL_MODE,
    icon: mdiArrowLeftRight,
    offIcon: mdiArrowOscillatingOff,
    values: {
      ...named(mdiArrowOscillatingOff, "off", "stop", "fixed"),
      ...named(mdiArrowExpandHorizontal, "on", "auto", "swing", "both", "wide"),
      ...named(mdiArrowLeft, "left", "leftmost"),
      ...named(mdiArrowRight, "right", "rightmost"),
      ...named(mdiArrowCollapseHorizontal, "middle", "mid", "center", "centre"),
    },
  },
};

const DIGITS = [
  mdiNumeric0CircleOutline,
  mdiNumeric1CircleOutline,
  mdiNumeric2CircleOutline,
  mdiNumeric3CircleOutline,
  mdiNumeric4CircleOutline,
  mdiNumeric5CircleOutline,
  mdiNumeric6CircleOutline,
  mdiNumeric7CircleOutline,
  mdiNumeric8CircleOutline,
  mdiNumeric9CircleOutline,
];

/**
 * The icon of a value, without the case, with synonyms and numbers
 * (CARD-LIST-6); none for an unknown value: its label shows (CARD-LIST-7).
 */
export function valueIcon(kind: ListKind, value: string): string | undefined {
  const name = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const known = kind.values[name];
  if (known) {
    return known;
  }
  // "1", "level_2", "speed 3"...: a number from 0 to 9
  const digit = /^(?:(?:level|speed|fan|step)_?)?(\d)$/.exec(name);
  return digit ? DIGITS[Number(digit[1])] : undefined;
}
