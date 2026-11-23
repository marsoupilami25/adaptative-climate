// AC shim (CARD_ARCHITECTURE.md §4): the type the copy imports from
// src/data/entity/entity_registry.ts of the Home Assistant frontend (Apache 2.0).

export interface EntityRegistryDisplayEntry {
  entity_id: string;
  name?: string;
  icon?: string;
  device_id?: string;
  area_id?: string;
  labels: string[];
  hidden?: boolean;
  translation_key?: string;
  platform?: string;
  display_precision?: number;
  has_entity_name?: boolean;
}
