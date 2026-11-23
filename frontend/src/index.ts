// Entry of the card file (CARD_ARCHITECTURE.md §3, §8): registers the
// elements, and lists the card in "Add card" (CARD-CONF-3).

import "./ac/card";
import { CARD_TYPE } from "./ac/config";

declare const __VERSION__: string;

interface CustomCardEntry {
  type: string;
  name: string;
  description: string;
  preview?: boolean;
}

declare global {
  interface Window {
    customCards?: CustomCardEntry[];
  }
}

// The version in the browser console: it shows which card file is loaded.
console.info(
  `%c ADAPTATIVE-CLIMATE-CARD %c v${__VERSION__} `,
  "color: white; font-weight: bold; background: #ff6f22",
  "color: #ff6f22; font-weight: bold",
);

window.customCards ??= [];
if (!window.customCards.some((card) => card.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: "Adaptative Climate",
    description: "The thermostat of an Adaptative Climate entity.",
  });
}
