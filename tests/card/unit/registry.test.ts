// What the card finds in the entity registry of the frontend.

import { acClimateEntities, isAcEntity, monitoringSensors } from "../../../frontend/src/ac/registry";
import { AC, HEATER, fakeHass, SOURCES, TEMPERATURES } from "../fakes";

describe("CARD-GEN-1: an AC entity only", () => {
  it("knows an AC entity by its platform", () => {
    const hass = fakeHass();
    expect(isAcEntity(hass, AC)).toBe(true);
    expect(isAcEntity(hass, HEATER)).toBe(false);
    expect(isAcEntity(hass, "climate.unknown")).toBe(false);
  });
  it("lists the AC climate entities only", () => {
    expect(acClimateEntities(fakeHass())).toEqual([AC]);
  });
});

describe("CARD-ARCH-7: the monitoring sensors of the entry", () => {
  it("are found by device and translation key, whatever their ids", () => {
    expect(monitoringSensors(fakeHass(), AC)).toEqual({ sources: SOURCES, temperatures: TEMPERATURES });
  });
  it("are none for an entity without a device", () => {
    expect(monitoringSensors(fakeHass(), HEATER)).toEqual({});
  });
});
