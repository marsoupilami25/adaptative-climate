// AC shim (CARD_ARCHITECTURE.md §4): the part of `HomeAssistant`
// (src/types.ts of the Home Assistant frontend, Apache 2.0) that the copy and
// the AC code use. The frontend gives the card its full `hass` object.

import type {
  Connection,
  HassConfig,
  HassEntities,
  HassEntity,
  HassServices,
  HassServiceTarget,
  MessageBase,
} from "home-assistant-js-websocket";
import type { EntityRegistryDisplayEntry } from "./data/entity/entity_registry";
import type { FrontendLocaleData } from "./data/translation";

export type LocalizeFunc = (key: string, values?: Record<string, unknown>) => string;

export interface HomeAssistantInternationalization {
  language: string;
  locale: FrontendLocaleData;
  localize: LocalizeFunc;
}

export interface HomeAssistantApi {
  callService(
    domain: string,
    service: string,
    serviceData?: Record<string, any>,
    target?: HassServiceTarget,
    notifyOnError?: boolean,
    returnResponse?: boolean,
  ): Promise<unknown>;
  callWS<T>(msg: MessageBase): Promise<T>;
}

export interface HomeAssistantFormatters {
  formatEntityState(stateObj: HassEntity, state?: string): string;
  formatEntityAttributeValue(stateObj: HassEntity, attribute: string, value?: any): string;
  formatEntityAttributeName(stateObj: HassEntity, attribute: string): string;
  formatEntityName(stateObj: HassEntity, name?: string): string;
}

export interface HomeAssistantConfig {
  config: HassConfig;
}

export interface HomeAssistant
  extends HomeAssistantInternationalization,
    HomeAssistantApi,
    HomeAssistantFormatters,
    HomeAssistantConfig {
  states: HassEntities;
  services: HassServices;
  entities: Record<string, EntityRegistryDisplayEntry>;
  connection: Connection;
}

declare global {
  // The events of the copy, declared in src/types.ts of the frontend
  interface HASSDomEvents {
    "value-changed": {
      value: unknown;
    };
    change: undefined;
  }
}
