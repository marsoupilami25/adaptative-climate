// The phase of a bi-source heat_cool (CARD_SPEC.md §3).

import { phaseEmphasis } from "../../../frontend/src/ac/card";
import { acEntity } from "../fakes";

describe("CARD-PHASE-1: the handle of the current phase", () => {
  it("is the low handle in heat, the high handle in cool", () => {
    expect(phaseEmphasis(acEntity("heat_cool", { phase: "heat" }))).toBe("low");
    expect(phaseEmphasis(acEntity("heat_cool", { phase: "cool" }))).toBe("high");
  });
});

describe("CARD-PHASE-3: without phase", () => {
  it("no handle is inverted", () => {
    expect(phaseEmphasis(acEntity("heat_cool", { phase: null }))).toBeUndefined();
    expect(phaseEmphasis(acEntity("heat"))).toBeUndefined();
  });
});
