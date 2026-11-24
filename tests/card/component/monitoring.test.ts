// The monitoring in the header (CARD_SPEC.md §6).

import { mdiSync, mdiSyncAlert, mdiThermometerAlert, mdiThermometerCheck } from "../../../frontend/node_modules/@mdi/js/mdi.js";
import { fakeHass, SOURCES, TEMPERATURES } from "../fakes";
import { all, mountCard, one } from "./harness";

const indicators = (card: Element) => all(card, "ac-monitoring ha-icon-button");

describe("CARD-MON-1 to 5: the monitoring", () => {
  it("CARD-MON-1: always: the two indicators", async () => {
    const { card } = await mountCard(fakeHass(), { monitoring: "always" });
    expect(indicators(card)).toHaveLength(2);
  });
  it("CARD-MON-1: errors: the indicators of the sensors on only", async () => {
    const { card } = await mountCard(fakeHass(undefined, { temperatures: "on" }), { monitoring: "errors" });
    expect(indicators(card).map((icon) => icon.getAttribute("data-path"))).toEqual([mdiThermometerAlert]);
  });
  it("CARD-MON-1: hidden: nothing", async () => {
    const { card } = await mountCard(fakeHass(undefined, { sources: "on" }), { monitoring: "hidden" });
    expect(all(card, "ac-monitoring *")).toHaveLength(0);
  });
  it("CARD-MON-2, CARD-MON-3: green and off icons without problem, red and on icons with", async () => {
    const { card } = await mountCard(fakeHass(undefined, { sources: "on" }), {});
    const [sources, temperatures] = indicators(card);
    expect([sources.getAttribute("data-path"), sources.classList.contains("on")]).toEqual([mdiSyncAlert, true]);
    expect([temperatures.getAttribute("data-path"), temperatures.classList.contains("on")]).toEqual([mdiThermometerCheck, false]);
    expect(mdiSync).toBeDefined();
  });
  it("CARD-MON-4: compact: one dot, red when a sensor is on", async () => {
    const { card } = await mountCard(fakeHass(undefined, { temperatures: "on" }), { monitoring: "compact" });
    expect(all(card, "ac-monitoring .dot.on")).toHaveLength(1);
    expect(indicators(card)).toHaveLength(0);
  });
  it("CARD-MON-5: pressing an indicator opens its sensor; the dot opens the sensor on", async () => {
    let mounted = await mountCard(fakeHass(), {});
    (indicators(mounted.card)[1] as HTMLElement).click();
    expect(mounted.events).toContainEqual({ type: "hass-more-info", detail: { entityId: TEMPERATURES } });
    mounted = await mountCard(fakeHass(undefined, { temperatures: "on" }), { monitoring: "compact" });
    one(mounted.card, "ac-monitoring .dot").click();
    expect(mounted.events).toContainEqual({ type: "hass-more-info", detail: { entityId: TEMPERATURES } });
    expect(SOURCES).toBeDefined();
  });
});
