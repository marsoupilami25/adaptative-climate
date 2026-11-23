// AC shim (CARD_ARCHITECTURE.md §4): the type the copy imports from
// src/data/home_shortcuts.ts of the Home Assistant frontend (Apache 2.0).

export interface CustomShortcutItem {
  type: "custom";
  path: string;
  label?: string;
  icon?: string;
  color?: string;
}

export interface SummaryShortcutItem {
  type: "summary";
  key: string;
  hidden?: boolean;
}

export type ShortcutItem = CustomShortcutItem | SummaryShortcutItem;
