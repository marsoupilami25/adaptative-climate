// The features of the card, under the dial, in the order of the
// configuration (CARD_SPEC.md §2, §5; CARD-LOOK-1).

import { css, html, LitElement, nothing } from "lit";
import { customElement, property } from "lit/decorators";
import type { HomeAssistant } from "../ha/types";
import type { FeatureConfig } from "./config";
import "./device-feature";
import type { AcClimateEntity } from "./entity";
import "./hvac-modes-feature";

@customElement("ac-features")
export class AcFeatures extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @property({ attribute: false }) public stateObj!: AcClimateEntity;

  @property({ attribute: false }) public features: FeatureConfig[] = [];

  private _feature(config: FeatureConfig) {
    switch (config.type) {
      case "ac-device":
        return html`<ac-device-feature .hass=${this.hass} .stateObj=${this.stateObj}></ac-device-feature>`;
      case "ac-hvac-modes":
        return html`<ac-hvac-modes-feature .hass=${this.hass} .stateObj=${this.stateObj} .config=${config}></ac-hvac-modes-feature>`;
      default:
        return nothing; // the lists: step 6c
    }
  }

  protected render() {
    return this.features.map((config) => this._feature(config));
  }

  // The layout of the features of Home Assistant
  static styles = css`
    :host {
      --feature-height: 42px;
      --feature-border-radius: var(--ha-card-features-border-radius, var(--ha-border-radius-lg));
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: var(--ha-card-feature-gap, 12px);
      width: 100%;
      box-sizing: border-box;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "ac-features": AcFeatures;
  }
}
