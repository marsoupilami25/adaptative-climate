// The card as a whole (CARD_SPEC.md §1, §2, §3, §7).

import { acEntity, AC, fakeHass, FAN, RANGE, SWING, TARGET } from "../fakes";
import { all, mountCard, one, text } from "./harness";

describe("CARD-GEN-1, CARD-GEN-2: the entity", () => {
  it("CARD-GEN-1: another entity gives a message", async () => {
    const { card } = await mountCard(fakeHass(), { entity: "climate.radiator" });
    expect(text(one(card, ".warning"))).toContain("is not an Adaptative Climate entity");
  });
  it("CARD-GEN-2: an entity that does not exist gives a message", async () => {
    const { card } = await mountCard(fakeHass(), { entity: "climate.nowhere" });
    expect(text(one(card, ".warning"))).toContain("Entity not available");
  });
});

describe("CARD-DIAL-1: the header and the dial of the thermostat card", () => {
  it("shows the title, and the ⋮ button opens the details of the entity", async () => {
    const { card, events } = await mountCard(fakeHass(), { name: "My room" });
    expect(text(one(card, ".title")).trim()).toBe("My room");
    one(card, "ha-icon-button.more-info").click();
    expect(events).toContainEqual({ type: "hass-more-info", detail: { entityId: AC } });
    expect(all(card, "ac-ha-state-control-climate-temperature")).toHaveLength(1);
  });
});

describe("CARD-PHASE-1 to 3: the handle of the phase", () => {
  const rangeEntity = (phase: string | null) =>
    acEntity("heat_cool", { supported_features: RANGE, target_temp_low: 19, target_temp_high: 24, phase });
  it("CARD-PHASE-1, CARD-PHASE-2: the handle of the current phase is inverted, the other one is not", async () => {
    const { card } = await mountCard(fakeHass(rangeEntity("cool")), {});
    expect(all(card, ".target.emphasis-high")).toHaveLength(1);
    expect(all(card, ".target-border.emphasis-high")).toHaveLength(1);
    expect(all(card, ".emphasis-low")).toHaveLength(0);
  });
  it("CARD-PHASE-3: without phase, no handle is inverted", async () => {
    const { card } = await mountCard(fakeHass(rangeEntity(null)), {});
    expect(all(card, "[class*=emphasis]")).toHaveLength(0);
  });
});

describe("CARD-DIAL-2: a mode without a target", () => {
  it("shows its state smaller than the thermostat card, centered", async () => {
    const { card } = await mountCard(fakeHass(acEntity("fan_only", { supported_features: 0, temperature: undefined })), {});
    const state = one(card, ".primary-state");
    const style = getComputedStyle(state);
    expect(parseFloat(style.fontSize)).toBeLessThan(36);
    expect(style.textAlign).toBe("center");
  });
});

describe("CARD-MISS-1: the entity unavailable", () => {
  it("greys out the mode bar, and still shows the monitoring", async () => {
    const hass = fakeHass(acEntity("unavailable", { active_entity_id: null }), { sources: "on" });
    const { card } = await mountCard(hass, { features: [{ type: "ac-hvac-modes" }] });
    expect(one(card, "ac-ha-control-select").hasAttribute("disabled") || (one(card, "ac-ha-control-select") as unknown as { disabled: boolean }).disabled).toBe(true);
    expect(all(card, "ac-monitoring ha-icon-button.on")).toHaveLength(1);
  });
});

describe("CARD-LOOK-1, CARD-LOOK-5 to 7: the features under the dial", () => {
  const lists = { supported_features: TARGET | FAN | SWING, fan_modes: ["auto", "low"], swing_modes: ["on", "off"] };
  const features = [{ type: "ac-fan-modes" as const }, { type: "ac-device" as const }, { type: "ac-swing-modes" as const }];
  it("CARD-LOOK-1: in the order of the configuration", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat", lists)), { features });
    const order = all(card, "ac-list-feature, ac-device-feature").map((element) => element.localName);
    expect(order).toEqual(["ac-list-feature", "ac-device-feature", "ac-list-feature"]);
  });
  const two = [{ type: "ac-fan-modes" as const }, { type: "ac-swing-modes" as const }];
  it("CARD-LOOK-6: two lists share a row when the height is automatic", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat", lists)), { features: two }, { width: 500 });
    expect(all(card, ".cell.half")).toHaveLength(2);
  });
  it("CARD-LOOK-5: each list on its own row when the card has room in height", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat", lists)), { features: two }, { width: 500, height: 900, layout: "grid" });
    expect(all(card, ".cell.half")).toHaveLength(0);
  });
  it("CARD-LOOK-6: two lists share a row when the card has no room in height", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat", lists)), { features: two }, { width: 500, height: 420, layout: "grid" });
    expect(all(card, ".cell.half")).toHaveLength(2);
  });
  it("CARD-LOOK-7: each list on its own row when the card is too narrow", async () => {
    const { card } = await mountCard(fakeHass(acEntity("heat", lists)), { features: two }, { width: 250 });
    expect(all(card, ".cell.half")).toHaveLength(0);
  });
});

describe("CARD-MISS-2: an attribute missing", () => {
  it("hides what it feeds, and nothing breaks", async () => {
    const bare = acEntity("heat");
    for (const name of ["active_entity_id", "mode_entity_ids", "unavailable_modes", "foreign_modes", "phase"]) {
      delete (bare.attributes as unknown as Record<string, unknown>)[name];
    }
    const { card } = await mountCard(fakeHass(bare), { features: [{ type: "ac-device" }, { type: "ac-hvac-modes" }] });
    expect(all(card, "ac-device-feature .name, ac-device-feature .status")).toHaveLength(0);
    expect(one(card, "#option-heat").title).toBe("state:heat");
  });
});
