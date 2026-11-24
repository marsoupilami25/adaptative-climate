// The texts of the card (CARD_SPEC.md §9).

import { localize } from "../../../frontend/src/ac/localize";
import { fakeHass } from "../fakes";

describe("CARD-LANG-1: the language of the user", () => {
  it("gives the text in French", () => {
    expect(localize(fakeHass(undefined, { language: "fr" }), "monitoring.none")).toBe("Aucun problème");
  });
  it("takes the language without its region", () => {
    expect(localize(fakeHass(undefined, { language: "fr-CA" }), "monitoring.none")).toBe("Aucun problème");
  });
});

describe("CARD-LANG-2: English and French, English for the others", () => {
  it("gives English for another language", () => {
    expect(localize(fakeHass(undefined, { language: "de" }), "monitoring.none")).toBe("No problem");
  });
  it("fills the values", () => {
    expect(localize(fakeHass(), "device.unavailable", { device: "Radiator" })).toBe("Radiator unavailable");
  });
});
