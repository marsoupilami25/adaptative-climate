// The texts of the card, in English and French (CARD_SPEC.md §9). The other
// texts (modes, actions, options) come from Home Assistant.

import type { HomeAssistant } from "../ha/types";
import en from "./translations/en.json";
import fr from "./translations/fr.json";

type Tree = { [key: string]: string | Tree };

const LANGUAGES: Record<string, Tree> = { en, fr };

function lookup(tree: Tree, key: string): string | undefined {
  let node: string | Tree | undefined = tree;
  for (const part of key.split(".")) {
    node = typeof node === "object" ? node[part] : undefined;
  }
  return typeof node === "string" ? node : undefined;
}

/** The text of `key` in the language of the user, else in English (CARD-LANG-1, 2). */
export function localize(
  hass: HomeAssistant | undefined,
  key: string,
  values: Record<string, string> = {},
): string {
  const language = (hass?.language ?? "en").split("-")[0];
  const text = lookup(LANGUAGES[language] ?? en, key) ?? lookup(en, key) ?? key;
  return text.replace(/\{(\w+)\}/g, (match, name: string) => values[name] ?? match);
}
