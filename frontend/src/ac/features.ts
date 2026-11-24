// The features of the card, under the dial, in the order of the
// configuration (CARD_SPEC.md §2, §5; CARD-LOOK-1, 2, 4 to 7).

import { css, html, LitElement, nothing } from "lit";
import { customElement, property } from "lit/decorators";
import { classMap } from "lit/directives/class-map";
import type { HomeAssistant } from "../ha/types";
import { type FeatureConfig, LIST_TYPES, type ListFeatureConfig, type ListType } from "./config";
import "./device-feature";
import type { AcClimateEntity } from "./entity";
import "./hvac-modes-feature";
import "./list-feature";
import { listShown } from "./list-feature";

export const DEVICE_HEIGHT = 28;
export const FEATURE_HEIGHT = 42;
export const FEATURE_GAP = 12;

/** A feature as laid out: on a full row, or on half a row. */
export interface Placed {
  config: FeatureConfig;
  half: boolean;
}

function isList(config: FeatureConfig): config is ListFeatureConfig {
  return (LIST_TYPES as readonly string[]).includes(config.type);
}

function inGroup(config: FeatureConfig): boolean {
  return isList(config) && (config.style ?? "dropdown") === "dropdown";
}

// The rows of a group of n lists packed two per row (CARD-LOOK-6): 1 → [1],
// 2 → [2], 3 → [1, 2], 4 → [2, 2]
function packed(group: FeatureConfig[]): Placed[] {
  const single = group.length % 2;
  return group.map((config, index) => ({ config, half: index >= single }));
}

/**
 * The features shown, as laid out. A feature with nothing to show takes no
 * space, the device line excepted (CARD-LOOK-2). Lists in `dropdown` style
 * that follow each other form a group (CARD-LOOK-4); `pack` puts a group two
 * per row.
 */
export function layOut(stateObj: AcClimateEntity | undefined, features: FeatureConfig[], pack: boolean): Placed[] {
  const shown = features.filter(
    (config) => !isList(config) || !stateObj || listShown(stateObj, config.type as ListType),
  );
  const placed: Placed[] = [];
  let group: FeatureConfig[] = [];
  const flush = () => {
    placed.push(...(pack ? packed(group) : group.map((config) => ({ config, half: false }))));
    group = [];
  };
  for (const config of shown) {
    if (inGroup(config)) {
      group.push(config);
    } else {
      flush();
      placed.push({ config, half: false });
    }
  }
  flush();
  return placed;
}

/** The height of the features as laid out, in px. */
export function featuresHeight(placed: Placed[]): number {
  const rows: number[] = [];
  for (let index = 0; index < placed.length; index++) {
    const item = placed[index];
    rows.push(item.config.type === "ac-device" ? DEVICE_HEIGHT : FEATURE_HEIGHT);
    if (item.half) {
      index++; // its pair is on the same row
    }
  }
  return rows.reduce((sum, height) => sum + height, 0) + Math.max(0, rows.length - 1) * FEATURE_GAP;
}

@customElement("ac-features")
export class AcFeatures extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @property({ attribute: false }) public stateObj!: AcClimateEntity;

  @property({ attribute: false }) public features: FeatureConfig[] = [];

  @property({ type: Boolean }) public pack = true;

  private _feature(config: FeatureConfig) {
    switch (config.type) {
      case "ac-device":
        return html`<ac-device-feature .hass=${this.hass} .stateObj=${this.stateObj}></ac-device-feature>`;
      case "ac-hvac-modes":
        return html`<ac-hvac-modes-feature .hass=${this.hass} .stateObj=${this.stateObj} .config=${config}></ac-hvac-modes-feature>`;
      default:
        return isList(config)
          ? html`<ac-list-feature .hass=${this.hass} .stateObj=${this.stateObj} .config=${config}></ac-list-feature>`
          : nothing;
    }
  }

  protected render() {
    return layOut(this.stateObj, this.features, this.pack).map(
      (item) => html`<div class=${classMap({ cell: true, half: item.half })}>${this._feature(item.config)}</div>`,
    );
  }

  // The layout of the features of Home Assistant, on two columns
  static styles = css`
    :host {
      --feature-height: 42px;
      --feature-border-radius: var(--ha-card-features-border-radius, var(--ha-border-radius-lg));
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--ha-card-feature-gap, 12px);
      width: 100%;
      box-sizing: border-box;
    }
    .cell {
      grid-column: 1 / -1;
      min-width: 0;
    }
    .cell.half {
      grid-column: auto;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "ac-features": AcFeatures;
  }
}
