// The mode bar (CARD_SPEC.md §5.1).

import { acEntity, fakeHass } from "../fakes";
import { all, mountCard, one, settle, text } from "./harness";

const bar = { features: [{ type: "ac-hvac-modes" as const }] };

describe("CARD-MODE-1 to 5: the mode bar", () => {
  it("CARD-MODE-1: one button per mode, with its icon", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat")), bar);
    const options = all(card, "ac-ha-control-select .option");
    expect(options).toHaveLength(3);
    expect(all(card, "ac-ha-control-select .option ha-svg-icon")).toHaveLength(3);
  });
  it("CARD-MODE-3: the button of the current mode is selected", async () => {
    const { card } = await mountCard(fakeHass(acEntity("cool")), bar);
    expect(one(card, "ac-ha-control-select .option.selected").id).toBe("option-cool");
  });
  it("CARD-MODE-5: the tooltip gives the mode and its device", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat")), bar);
    expect(one(card, "#option-heat").title).toBe("state:heat · Radiator");
  });
  it("CARD-GEN-5: pressing a mode sets it with climate.set_hvac_mode", async () => {
    const hass = fakeHass(acEntity("heat"));
    const { card } = await mountCard(hass, bar);
    one(card, "#option-cool").click();
    await settle(card);
    expect(hass.calls).toContainEqual({ domain: "climate", service: "set_hvac_mode", data: { entity_id: "climate.living_room", hvac_mode: "cool" } });
  });
  it("CARD-MODE-4: a mode not available is greyed out; pressing it asks nothing and says why", async () => {
    const hass = fakeHass(acEntity("heat", { unavailable_modes: ["cool"] }));
    const { card } = await mountCard(hass, bar);
    expect(one(card, "#option-cool").classList.contains("dimmed")).toBe(true);
    one(card, "#option-cool").click();
    await settle(card);
    expect(hass.calls).toEqual([]);
    expect(text(one(card, "ac-hvac-modes-feature .notice"))).toBe("state:cool: Air conditioner unavailable");
    expect(one(card, "ac-ha-control-select .option.selected").id).toBe("option-heat");
  });
});

describe("CARD-LANG-3: the texts of Home Assistant", () => {
  it("name the modes", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat")), bar);
    expect(one(card, "#option-off").title).toBe("state:off");
  });
});
