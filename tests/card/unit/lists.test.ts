// The icons of the values of a list (CARD_SPEC.md §5.2).

import { LISTS, valueIcon } from "../../../frontend/src/ac/lists";

const fan = LISTS["ac-fan-modes"];

describe("CARD-LIST-6: icons of values", () => {
  it("knows the values of Home Assistant", () => {
    expect(valueIcon(fan, "auto")).toBe(fan.values.auto);
  });
  it("ignores the case and the separators", () => {
    expect(valueIcon(fan, "Low")).toBe(valueIcon(fan, "low"));
    expect(valueIcon(LISTS["ac-swing-modes"], "Up-Down")).toBe(valueIcon(LISTS["ac-swing-modes"], "up_down"));
  });
  it("knows common synonyms", () => {
    expect(valueIcon(fan, "quiet")).toBe(valueIcon(fan, "low"));
    expect(valueIcon(fan, "Turbo")).toBe(valueIcon(fan, "high"));
  });
  it("knows numbers", () => {
    expect(valueIcon(fan, "2")).toBeDefined();
    expect(valueIcon(fan, "level 2")).toBe(valueIcon(fan, "2"));
    expect(valueIcon(fan, "speed_3")).not.toBe(valueIcon(fan, "2"));
  });
});

describe("CARD-LIST-7: a value without an icon", () => {
  it("has no icon, not a dot", () => {
    expect(valueIcon(fan, "breeze-mode")).toBeUndefined();
  });
});
