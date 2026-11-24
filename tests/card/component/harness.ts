// The bench of the component tests (CARD_TESTS.md): the card in a page, with
// what the frontend of Home Assistant gives it.
// - The contexts the copied dial consumes: answered as the frontend does, by
//   the "context-request" protocol, with the same keys (CARD-ARCH-6).
// - The elements of Home Assistant used as is (ha-card, ha-icon-button,
//   ha-svg-icon): small stand-ins, defined only when the page has none.

import "../../../frontend/src/index";
import type { AdaptativeClimateCardConfig } from "../../../frontend/src/ac/config";
import type { HomeAssistant } from "../../../frontend/src/ha/types";

class StandInCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" }).innerHTML = "<slot></slot>";
  }
}

class StandInSvgIcon extends HTMLElement {
  set path(value: string) {
    this.setAttribute("data-path", value);
  }
  get path(): string {
    return this.getAttribute("data-path") ?? "";
  }
}

class StandInIconButton extends HTMLElement {
  set path(value: string) {
    this.setAttribute("data-path", value);
  }
  get path(): string {
    return this.getAttribute("data-path") ?? "";
  }
  set label(value: string) {
    this.setAttribute("title", value);
  }
  get label(): string {
    return this.getAttribute("title") ?? "";
  }
  set disabled(value: boolean) {
    this.toggleAttribute("disabled", value);
  }
  get disabled(): boolean {
    return this.hasAttribute("disabled");
  }
}

for (const [name, element] of [
  ["ha-card", StandInCard],
  ["ha-svg-icon", StandInSvgIcon],
  ["ha-icon-button", StandInIconButton],
] as const) {
  if (!customElements.get(name)) {
    customElements.define(name, element);
  }
}

interface ContextRequest extends Event {
  context: unknown;
  callback: (value: unknown, unsubscribe?: () => void) => void;
}

/** The values of the four contexts, from `hass`, as the frontend provides them. */
function contexts(hass: HomeAssistant): Record<string, unknown> {
  return {
    hassApi: { callService: hass.callService, callWS: hass.callWS },
    hassConfig: { config: hass.config },
    hassFormatters: {
      formatEntityState: hass.formatEntityState,
      formatEntityAttributeValue: hass.formatEntityAttributeValue,
      formatEntityAttributeName: hass.formatEntityAttributeName,
      formatEntityName: hass.formatEntityName,
    },
    hassInternationalization: { language: hass.language, locale: hass.locale, localize: hass.localize },
  };
}

export interface Mounted {
  root: HTMLElement;
  card: HTMLElement & { hass?: HomeAssistant; layout?: string; updateComplete: Promise<boolean> };
  events: { type: string; detail: unknown }[];
}

/** The card in a page, `width` px wide (and `height` px high when given). */
export async function mountCard(
  hass: HomeAssistant,
  config: Partial<AdaptativeClimateCardConfig>,
  size: { width?: number; height?: number; layout?: string } = {},
): Promise<Mounted> {
  document.body.innerHTML = "";
  const root = document.createElement("div");
  root.style.width = `${size.width ?? 500}px`;
  if (size.height) {
    root.style.height = `${size.height}px`;
  }
  const values = contexts(hass);
  root.addEventListener("context-request", (event) => {
    const request = event as ContextRequest;
    const key = request.context as string;
    if (key in values) {
      event.stopPropagation();
      request.callback(values[key], () => undefined);
    }
  });
  const events: Mounted["events"] = [];
  for (const type of ["hass-more-info"]) {
    root.addEventListener(type, (event) => events.push({ type, detail: (event as CustomEvent).detail }));
  }
  document.body.appendChild(root);
  const card = document.createElement("adaptative-climate-card") as Mounted["card"];
  (card as unknown as { setConfig(config: unknown): void }).setConfig({
    type: "custom:adaptative-climate-card",
    entity: "climate.living_room",
    ...config,
  });
  card.layout = size.layout;
  card.hass = hass;
  root.appendChild(card);
  await settle(card);
  return { root, card, events };
}

/** Wait until the card and the elements inside it have rendered. */
export async function settle(element: Element): Promise<void> {
  for (let round = 0; round < 4; round++) {
    const pending = all(element, "*")
      .map((el) => (el as unknown as { updateComplete?: Promise<unknown> }).updateComplete)
      .filter(Boolean);
    await Promise.all([(element as unknown as { updateComplete?: Promise<unknown> }).updateComplete, ...pending]);
    await new Promise((resolve) => requestAnimationFrame(() => resolve(undefined)));
  }
}

/** The parent of an element, through the shadow roots: the host for the top of a shadow root. */
function composedParent(element: Element): Element | null {
  if (element.parentElement) {
    return element.parentElement;
  }
  const parent = element.parentNode;
  return parent instanceof ShadowRoot ? parent.host : null;
}

/** Whether `element` matches `parts`, compound selectors each a descendant of the one before, through the shadow roots. */
function matchesThrough(element: Element, parts: string[], root: Element | ShadowRoot | Document): boolean {
  if (!element.matches(parts[parts.length - 1])) {
    return false;
  }
  let index = parts.length - 2;
  for (let node = composedParent(element); node && index >= 0; node = composedParent(node)) {
    if (node.matches(parts[index])) {
      index--;
    }
    if (node === root) {
      break;
    }
  }
  return index < 0;
}

/**
 * Every element matching `selector`, through the shadow roots, in their
 * order. A descendant combinator crosses them: "ac-dropdown .trigger" is a
 * `.trigger` in the shadow root of `ac-dropdown`. Only descendant
 * combinators and lists ("a, b") are understood.
 */
export function all(root: Element | ShadowRoot | Document, selector: string): Element[] {
  const elements: Element[] = [];
  const visit = (node: Element | ShadowRoot | Document) => {
    for (const child of node.querySelectorAll("*")) {
      elements.push(child);
      if (child.shadowRoot) {
        visit(child.shadowRoot);
      }
    }
  };
  if (root instanceof Element && root.shadowRoot) {
    visit(root.shadowRoot); // the shadow root of the root itself
  }
  visit(root);
  const alternatives = selector.split(",").map((part) => part.trim().split(/\s+/));
  return [...new Set(elements)].filter((element) => alternatives.some((parts) => matchesThrough(element, parts, root)));
}

/** The first element matching `selector`, through the shadow roots. */
export function one<T extends Element = HTMLElement>(root: Element | ShadowRoot | Document, selector: string): T {
  const found = all(root, selector)[0];
  if (!found) {
    throw new Error(`No ${selector}`);
  }
  return found as T;
}

/** The text of an element, with the text of its shadow root. */
export function text(element: Element): string {
  return (element.shadowRoot?.textContent ?? "") + (element.textContent ?? "");
}
