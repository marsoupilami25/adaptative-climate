// AC shim (CARD_ARCHITECTURE.md §4): the four contexts the copy consumes, from
// src/data/context/index.ts of the Home Assistant frontend (Apache 2.0). The
// keys are those of the frontend: its providers answer the copy
// (CARD-ARCH-6).

import { createContext } from "@lit/context";
import type {
  HomeAssistantApi,
  HomeAssistantConfig,
  HomeAssistantFormatters,
  HomeAssistantInternationalization,
} from "../../types";

export const internationalizationContext =
  createContext<HomeAssistantInternationalization>("hassInternationalization");

export const apiContext = createContext<HomeAssistantApi>("hassApi");

export const configContext = createContext<HomeAssistantConfig>("hassConfig");

export const formattersContext = createContext<HomeAssistantFormatters>("hassFormatters");
