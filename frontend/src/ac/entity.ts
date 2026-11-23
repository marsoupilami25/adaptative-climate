// The AC entity as the card reads it: a climate entity with the extra
// attributes of SPEC.md §2.2.

import type { ClimateEntity } from "../ha/data/climate";

export interface AcAttributes {
  active_entity_id?: string | null;
  phase?: "heat" | "cool" | null;
  mode_entity_ids?: Record<string, string>;
  unavailable_modes?: string[];
  foreign_modes?: Record<string, string>;
}

export type AcClimateEntity = ClimateEntity & {
  attributes: ClimateEntity["attributes"] & AcAttributes;
};
