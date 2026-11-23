// What the card finds in the entity registry of the frontend (`hass.entities`).

import type { HomeAssistant } from "../ha/types";

export const DOMAIN = "adaptative_climate";

export type MonitoringSensor = "sources" | "temperatures";

/** An entity of the integration (CARD-GEN-1). */
export function isAcEntity(hass: HomeAssistant, entityId: string): boolean {
  return hass.entities?.[entityId]?.platform === DOMAIN;
}

/** The AC entities, in the order of their ids. */
export function acClimateEntities(hass: HomeAssistant): string[] {
  return Object.values(hass.entities ?? {})
    .filter((entry) => entry.platform === DOMAIN && entry.entity_id.startsWith("climate."))
    .map((entry) => entry.entity_id)
    .sort();
}

/**
 * The monitoring sensors of the entry of an AC entity: same device, same
 * platform, known translation keys (CARD-ARCH-7). Entity ids can be renamed,
 * these cannot.
 */
export function monitoringSensors(hass: HomeAssistant, entityId: string): Partial<Record<MonitoringSensor, string>> {
  const device = hass.entities?.[entityId]?.device_id;
  const found: Partial<Record<MonitoringSensor, string>> = {};
  if (!device) {
    return found;
  }
  for (const entry of Object.values(hass.entities)) {
    if (entry.device_id !== device || entry.platform !== DOMAIN) {
      continue;
    }
    if (entry.translation_key === "monitoring_sources") {
      found.sources = entry.entity_id;
    } else if (entry.translation_key === "monitoring_temperatures") {
      found.temperatures = entry.entity_id;
    }
  }
  return found;
}
