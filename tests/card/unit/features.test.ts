// The layout of the features (CARD_SPEC.md §2, §5).

import type { FeatureConfig } from "../../../frontend/src/ac/config";
import { DEVICE_HEIGHT, FEATURE_GAP, FEATURE_HEIGHT, featuresHeight, layOut } from "../../../frontend/src/ac/features";
import { barModes } from "../../../frontend/src/ac/hvac-modes-feature";
import { listShown } from "../../../frontend/src/ac/list-feature";
import { acEntity, FAN, PRESET, SWING, SWING_H, TARGET } from "../fakes";

const all = acEntity("cool", { supported_features: TARGET | FAN | PRESET | SWING | SWING_H, fan_modes: ["auto"], swing_modes: ["on"] });
const lists = (n: number): FeatureConfig[] =>
  (["ac-preset-modes", "ac-fan-modes", "ac-swing-modes", "ac-swing-horizontal-modes"] as const).slice(0, n).map((type) => ({ type }));
const halves = (features: FeatureConfig[], pack = true) => layOut(all, features, pack).map((item) => item.half);

describe("CARD-LOOK-1: the order of the configuration", () => {
  it("is kept", () => {
    const features: FeatureConfig[] = [{ type: "ac-fan-modes" }, { type: "ac-device" }, { type: "ac-hvac-modes" }];
    expect(layOut(all, features, true).map((item) => item.config.type)).toEqual(["ac-fan-modes", "ac-device", "ac-hvac-modes"]);
  });
});

describe("CARD-LOOK-2: the height of the features", () => {
  it("counts the device line at its own height, empty or not", () => {
    const off = acEntity("off");
    expect(featuresHeight(layOut(off, [{ type: "ac-device" }], true))).toBe(DEVICE_HEIGHT);
    expect(featuresHeight(layOut(off, [{ type: "ac-device" }, { type: "ac-hvac-modes" }], true))).toBe(
      DEVICE_HEIGHT + FEATURE_GAP + FEATURE_HEIGHT,
    );
  });
  it("counts two lists of a row once", () => {
    expect(featuresHeight(layOut(all, lists(2), true))).toBe(FEATURE_HEIGHT);
    expect(featuresHeight(layOut(all, lists(2), false))).toBe(2 * FEATURE_HEIGHT + FEATURE_GAP);
  });
});

describe("CARD-LOOK-4: a group of lists", () => {
  it("is made of lists in dropdown style that follow each other", () => {
    const features: FeatureConfig[] = [{ type: "ac-fan-modes" }, { type: "ac-device" }, { type: "ac-swing-modes" }];
    expect(halves(features)).toEqual([false, false, false]);
  });
  it("is cut by a list in icons style", () => {
    const features: FeatureConfig[] = [{ type: "ac-fan-modes" }, { type: "ac-swing-modes", style: "icons" }, { type: "ac-preset-modes" }];
    expect(halves(features)).toEqual([false, false, false]);
  });
});

describe("CARD-LOOK-5: room in height", () => {
  it("puts each list on its own row", () => {
    expect(halves(lists(4), false)).toEqual([false, false, false, false]);
  });
});

describe("CARD-LOOK-6: a group packed two per row", () => {
  it.each([
    [1, [false]],
    [2, [true, true]],
    [3, [false, true, true]],
    [4, [true, true, true, true]],
  ])("of %i lists", (n, expected) => {
    expect(halves(lists(n as number))).toEqual(expected);
  });
});

describe("CARD-LIST-1: a list shows when the entity declares its setting", () => {
  it("shows a declared setting, even without option in the current mode", () => {
    const heat = acEntity("heat", { supported_features: TARGET | FAN, fan_modes: [] });
    expect(listShown(heat, "ac-fan-modes")).toBe(true);
  });
  it("hides a setting not declared, and takes no space", () => {
    const heat = acEntity("heat", { supported_features: TARGET | FAN });
    expect(listShown(heat, "ac-preset-modes")).toBe(false);
    expect(layOut(heat, lists(2), true).map((item) => item.config.type)).toEqual(["ac-fan-modes"]);
  });
});

describe("CARD-MODE-2: the modes of the bar", () => {
  const entity = acEntity("heat", { hvac_modes: ["off", "heat", "cool"] });
  it("are those of the entity, in its order, without the option", () => {
    expect(barModes(entity, { type: "ac-hvac-modes" })).toEqual(["off", "heat", "cool"]);
  });
  it("are those of the option, in its order", () => {
    expect(barModes(entity, { type: "ac-hvac-modes", hvac_modes: ["cool", "off"] })).toEqual(["cool", "off"]);
  });
  it("leave out a mode the entity does not list", () => {
    expect(barModes(entity, { type: "ac-hvac-modes", hvac_modes: ["dry", "heat"] })).toEqual(["heat"]);
  });
});
