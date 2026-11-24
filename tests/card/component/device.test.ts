// The device line (CARD_SPEC.md §4).

import { acEntity, AIRCON, fakeHass, HEATER } from "../fakes";
import { all, mountCard, one, text } from "./harness";

const line = { features: [{ type: "ac-device" as const }] };

describe("CARD-DEV-1 to 7: the device line", () => {
  it("CARD-DEV-1: the icon of the mode, then the device of the active source", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat")), line);
    expect(all(card, "ac-device-feature ha-svg-icon.mode")).toHaveLength(1);
    expect(text(one(card, "ac-device-feature .name"))).toBe("Radiator");
  });
  it("CARD-DEV-2: one line, an ellipsis when too long", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat")), line);
    const style = getComputedStyle(one(card, "ac-device-feature .name"));
    expect([style.whiteSpace, style.textOverflow]).toEqual(["nowrap", "ellipsis"]);
  });
  it("CARD-DEV-3: the active source unavailable: the status icon, in the error color", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat"), { heater: "unavailable" }), line);
    expect(all(card, "ac-device-feature .line.unavailable .status")).toHaveLength(1);
  });
  it("CARD-DEV-3: a device in a foreign mode: the status icon, in the warning color", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat", { foreign_modes: { [AIRCON]: "dry" } })), line);
    expect(all(card, "ac-device-feature .line.foreign .status")).toHaveLength(1);
  });
  it("CARD-DEV-4: both reasons: the unavailable one shows", async () => {
    const hass = fakeHass(acEntity("heat", { foreign_modes: { [AIRCON]: "dry" } }), { heater: "unavailable" });
    const { card } = await mountCard(hass, line);
    expect(all(card, "ac-device-feature .line.unavailable")).toHaveLength(1);
  });
  it("CARD-DEV-5: the tooltip gives each reason on its own line", async () => {
    const hass = fakeHass(acEntity("heat", { foreign_modes: { [AIRCON]: "dry" } }), { heater: "unavailable" });
    const { card } = await mountCard(hass, line);
    expect(one(card, "ac-device-feature .status").title.split("\n")).toEqual([
      "Radiator unavailable",
      "Air conditioner runs state:dry · not managed",
    ]);
  });
  it("CARD-DEV-6: pressing the status icon shows the same text", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat"), { heater: "unavailable" }), line);
    one(card, "ac-device-feature .status").click();
    await (one(card, "ac-device-feature") as unknown as { updateComplete: Promise<unknown> }).updateComplete;
    expect(text(one(card, "ac-device-feature .reasons"))).toBe(`${HEATER === "climate.radiator" ? "Radiator" : HEATER} unavailable`);
  });
  it("CARD-DEV-7: without an active source, the status icon only", async () => {
    const { card } = await mountCard(fakeHass(acEntity("off", { foreign_modes: { [AIRCON]: "dry" } })), line);
    expect(all(card, "ac-device-feature .name")).toHaveLength(0);
    expect(all(card, "ac-device-feature .status")).toHaveLength(1);
  });
});
