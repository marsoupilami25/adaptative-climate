// The monitoring in the header (CARD_SPEC.md §6).

import { indicators, monitoringWidth } from "../../../frontend/src/ac/monitoring";
import { AC, fakeHass, SOURCES, TEMPERATURES } from "../fakes";

describe("CARD-MON-1: what the header shows", () => {
  const ok = indicators(fakeHass(), AC);
  const problem = indicators(fakeHass(undefined, { temperatures: "on" }), AC);
  it("has the two sensors, the sources first", () => {
    expect(ok.map((indicator) => indicator.entityId)).toEqual([SOURCES, TEMPERATURES]);
    expect(problem.map((indicator) => indicator.on)).toEqual([false, true]);
  });
  it.each([
    ["always", 2, 2],
    ["compact", 1, 1],
    ["errors", 0, 1],
    ["hidden", 0, 0],
  ] as const)("takes its room in %s", (display, withoutProblem, withProblem) => {
    expect(monitoringWidth(display, ok)).toBe(withoutProblem);
    expect(monitoringWidth(display, problem)).toBe(withProblem);
  });
});
