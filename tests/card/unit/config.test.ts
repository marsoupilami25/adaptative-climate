// The configuration of the card (CARD_SPEC.md §8).

import { checkConfig, FEATURE_ORDER, stubConfig } from "../../../frontend/src/ac/config";
import { AC, fakeHass } from "../fakes";

const base = { type: "custom:adaptative-climate-card", entity: AC };

describe("CARD-CONF-1, CARD-CONF-2: options and features", () => {
  it("accepts every option and every feature", () => {
    const config = {
      ...base,
      name: "Room",
      show_current_as_primary: true,
      monitoring: "compact",
      features: [
        { type: "ac-device" },
        { type: "ac-hvac-modes", hvac_modes: ["heat", "off"] },
        { type: "ac-fan-modes", style: "icons" },
        { type: "ac-swing-modes", style: "dropdown" },
      ],
    };
    expect(checkConfig(config)).toEqual(config);
  });
  it("keeps the keys the dashboard adds", () => {
    const config = { ...base, grid_options: { rows: 6 }, view_layout: { position: "main" }, visibility: [] };
    expect(checkConfig(config)).toEqual(config);
  });
});

describe("CARD-CONF-6: a wrong value", () => {
  it.each([
    ["no entity", { type: base.type }],
    ["a monitoring not listed", { ...base, monitoring: "sometimes" }],
    ["a feature not known", { ...base, features: [{ type: "ac-humidity" }] }],
    ["a style not known", { ...base, features: [{ type: "ac-fan-modes", style: "slider" }] }],
    ["a boolean option given as text", { ...base, show_current_as_primary: "yes" }],
    ["an entity that is not a climate", { ...base, entity: "sensor.room" }],
  ])("is refused: %s", (_why, config) => {
    expect(() => checkConfig(config)).toThrow();
  });
});

describe("CARD-CONF-3: the start configuration", () => {
  it("takes the first AC entity, and no feature", () => {
    expect(stubConfig(fakeHass())).toEqual({ type: "custom:adaptative-climate-card", entity: AC });
  });
});

describe("CARD-CONF-4: the order the editor proposes the features", () => {
  it("is the order of the spec", () => {
    expect(FEATURE_ORDER.map((feature) => feature.type)).toEqual([
      "ac-device",
      "ac-hvac-modes",
      "ac-preset-modes",
      "ac-fan-modes",
      "ac-swing-modes",
      "ac-swing-horizontal-modes",
    ]);
  });
});
