// Entry of the card file (CARD_ARCHITECTURE.md §3, §8).
// The elements of the card are registered here from step 5 on.

declare const __VERSION__: string;

// The version in the browser console: it shows which card file is loaded.
console.info(
  `%c ADAPTATIVE-CLIMATE-CARD %c v${__VERSION__} `,
  "color: white; font-weight: bold; background: #ff6f22",
  "color: #ff6f22; font-weight: bold",
);

export {};
