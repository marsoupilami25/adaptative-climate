// The lists (CARD_SPEC.md §5.2).

import { LISTS } from "../../../frontend/src/ac/lists";
import { acEntity, fakeHass, FAN, TARGET } from "../fakes";
import { all, mountCard, one, settle, text } from "./harness";

const fanEntity = (fan_modes: string[], fan_mode?: string) =>
  acEntity("cool", { supported_features: TARGET | FAN, fan_modes, fan_mode });
const fan = (style?: "dropdown" | "icons") => ({ features: [{ type: "ac-fan-modes" as const, ...(style ? { style } : {}) }] });

describe("CARD-LIST-2, CARD-LIST-3: a list in dropdown style", () => {
  it("CARD-LIST-2: closed, it shows its icon and the current value; its name in its tooltip", async () => {
    const { card } = await mountCard(fakeHass(fanEntity(["auto", "low"], "auto")), fan());
    const trigger = one(card, "ac-dropdown .trigger");
    expect(text(one(card, "ac-dropdown .value"))).toBe("fan_mode:auto");
    expect(trigger.title).toBe("name:fan_mode");
    expect(text(trigger)).not.toContain("name:fan_mode");
    expect(one(card, "ac-dropdown .icon").getAttribute("data-path")).toBe(LISTS["ac-fan-modes"].icon);
  });
  it("CARD-LIST-3: pressed, it opens its options, the current one checked; choosing sets it", async () => {
    const hass = fakeHass(fanEntity(["auto", "low"], "auto"));
    const { card } = await mountCard(hass, fan());
    one(card, "ac-dropdown .trigger").click();
    await settle(card);
    expect(one(card, "ac-dropdown #menu").matches(":popover-open")).toBe(true);
    const options = all(card, "ac-dropdown .option");
    expect(options.map((option) => option.getAttribute("aria-selected"))).toEqual(["true", "false"]);
    (options[1] as HTMLElement).click();
    await settle(card);
    expect(hass.calls).toContainEqual({ domain: "climate", service: "set_fan_mode", data: { entity_id: "climate.living_room", fan_mode: "low" } });
    expect(one(card, "ac-dropdown #menu").matches(":popover-open")).toBe(false);
  });
  it("CARD-LIST-3: the keyboard opens it and chooses", async () => {
    const hass = fakeHass(fanEntity(["auto", "low"], "auto"));
    const { card } = await mountCard(hass, fan());
    one(card, "ac-dropdown .trigger").dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, composed: true }));
    await settle(card);
    const menu = one(card, "ac-dropdown #menu");
    menu.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, composed: true }));
    menu.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, composed: true }));
    await settle(card);
    expect(hass.calls.map((call) => call.data?.fan_mode)).toEqual(["low"]);
  });
});

describe("CARD-LIST-4: a list in icons style", () => {
  it("is a bar, the current value filled", async () => {
    const { card } = await mountCard(fakeHass(fanEntity(["auto", "low"], "low")), fan("icons"));
    expect(all(card, "ac-list-feature ac-ha-control-select .option")).toHaveLength(2);
    expect(one(card, "ac-list-feature .option.selected").id).toBe("option-low");
  });
});

describe("CARD-LIST-5: a greyed list", () => {
  it("is faded, with the off icon, \"—\", no arrow, and says why", async () => {
    const { card } = await mountCard(fakeHass(fanEntity([])), fan());
    const dropdown = one(card, "ac-dropdown");
    expect(dropdown.hasAttribute("disabled")).toBe(true);
    expect(parseFloat(getComputedStyle(one(card, "ac-dropdown .trigger")).opacity)).toBeLessThan(1);
    expect(text(one(card, "ac-dropdown .value"))).toBe("—");
    expect(all(card, "ac-dropdown .arrow")).toHaveLength(0);
    expect(one(card, "ac-dropdown .icon").getAttribute("data-path")).toBe(LISTS["ac-fan-modes"].offIcon);
    expect(one(card, "ac-dropdown .trigger").title).toBe("name:fan_mode: not offered in this mode");
  });
  it("in icons style too", async () => {
    const { card } = await mountCard(fakeHass(fanEntity([])), fan("icons"));
    expect(one(card, "ac-list-feature .empty").title).toBe("name:fan_mode: not offered in this mode");
  });
});

describe("CARD-LIST-7: a value without an icon", () => {
  it("makes the whole bar show the labels", async () => {
    const { card } = await mountCard(fakeHass(fanEntity(["auto", "breeze"], "auto")), fan("icons"));
    expect(all(card, "ac-list-feature .option ha-svg-icon")).toHaveLength(0);
    expect(all(card, "ac-list-feature .option span").map((span) => span.textContent)).toEqual(["fan_mode:auto", "fan_mode:breeze"]);
  });
});
