// The card: our own shell around the copied dial (CARD_ARCHITECTURE.md
// CARD-ARCH-5, §5). It reproduces the shell of the thermostat card of Home
// Assistant (title, ⋮ button, dial sized by the card: CARD-DIAL-1), and adds
// the AC parts.

import { ResizeController } from "@lit-labs/observers/resize-controller";
import { mdiDotsVertical } from "@mdi/js";
import { css, html, LitElement, nothing } from "lit";
import { customElement, property, state } from "lit/decorators";
import { styleMap } from "lit/directives/style-map";
import { fireEvent } from "../ha/common/dom/fire_event";
import "../ha/state-control/climate/ha-state-control-climate-temperature";
import type { HomeAssistant } from "../ha/types";
import { type AdaptativeClimateCardConfig, CARD_TYPE, checkConfig, stubConfig } from "./config";
import "./editor";
import { loadHaForm } from "./editor";
import "./features";
import { featuresHeight, layOut } from "./features";
import { localize } from "./localize";
import "./monitoring";
import { INDICATOR_WIDTH, indicators, monitoringWidth } from "./monitoring";
import type { AcClimateEntity } from "./entity";
import { isAcEntity } from "./registry";

// The layout of the lists (CARD_ARCHITECTURE.md §6)
const TITLE_HEIGHT = 41; // the title of the thermostat card: 16px x 2, 8px padding
const DIAL_MAX = 320; // the width of the dial of the thermostat card
const LIST_MIN_WIDTH = 140; // CARD-ARCH-13
const PADDING = 12; // around the features

interface GridOptions {
  columns?: number | "full";
  rows?: number | "auto";
  min_columns?: number;
  min_rows?: number;
}

declare global {
  interface HASSDomEvents {
    "hass-more-info": { entityId: string };
  }
}

/** The handle filled with the color of the current phase (CARD-PHASE-1 to 3). */
export function phaseEmphasis(stateObj: AcClimateEntity): "low" | "high" | undefined {
  const phase = stateObj.attributes.phase;
  return phase === "heat" ? "low" : phase === "cool" ? "high" : undefined;
}

@customElement(CARD_TYPE)
export class AdaptativeClimateCard extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;

  // "grid" in a section of a dashboard, set by Home Assistant (CARD-ARCH-10)
  @property({ attribute: false }) public layout?: string;

  @state() private _config?: AdaptativeClimateCardConfig;

  // The dial gets the height of the container, as on the thermostat card
  private _resizeController = new ResizeController(this, {
    callback: (entries) => {
      const container = entries[0]?.target.shadowRoot?.querySelector(".container") as HTMLElement | undefined;
      return container?.clientHeight;
    },
  });

  // The size of the card, for the layout of the lists
  private _sizeController = new ResizeController(this, {
    callback: (entries) => entries[0]?.contentRect,
  });

  public static async getConfigElement(): Promise<HTMLElement> {
    await loadHaForm();
    return document.createElement("adaptative-climate-card-editor");
  }

  public static getStubConfig(hass: HomeAssistant): AdaptativeClimateCardConfig {
    return stubConfig(hass);
  }

  public setConfig(config: AdaptativeClimateCardConfig): void {
    this._config = checkConfig(config);
  }

  public getCardSize(): number {
    return 7;
  }

  public getGridOptions(): GridOptions {
    // The lists counted two per row: the card starts compact (CARD-ARCH-12).
    // As the thermostat card: two thirds of a grid row per feature row.
    const stateObj = this._config ? (this.hass?.states[this._config.entity] as AcClimateEntity | undefined) : undefined;
    const placed = layOut(stateObj, this._config?.features ?? [], true);
    const featureRows = placed.filter((item) => !item.half).length + placed.filter((item) => item.half).length / 2;
    const extra = Math.ceil((featureRows * 2) / 3);
    return { columns: 12, rows: 5 + extra, min_columns: 6, min_rows: 2 + extra };
  }

  /** Lists two per row: when the height is automatic or short, if the width allows (CARD-LOOK-5 to 7). */
  private _pack(stateObj: AcClimateEntity): boolean {
    const size = this._sizeController.value;
    if (!size) {
      return true;
    }
    if ((size.width - 2 * PADDING - 12) / 2 < LIST_MIN_WIDTH) {
      return false; // too narrow for two (CARD-ARCH-13)
    }
    if (this.layout !== "grid" || this._config?.grid_options?.rows === "auto") {
      return true; // automatic height (CARD-ARCH-10)
    }
    // Room in height: the dial at its size, and each list on its own row (CARD-ARCH-11)
    const oneByRow = featuresHeight(layOut(stateObj, this._config?.features ?? [], false));
    const dial = Math.min(DIAL_MAX, size.width - 16) + 16;
    return size.height - TITLE_HEIGHT - PADDING - oneByRow < dial;
  }

  private _handleMoreInfo(): void {
    fireEvent(this, "hass-more-info", { entityId: this._config!.entity });
  }

  private _warning(key: string) {
    return html`<ha-card><p class="warning">${localize(this.hass, key, { entity: this._config!.entity })}</p></ha-card>`;
  }

  protected render() {
    if (!this.hass || !this._config) {
      return nothing;
    }
    const entityId = this._config.entity;
    const stateObj = this.hass.states[entityId] as AcClimateEntity | undefined;
    if (!stateObj) {
      return this._warning("error.not_found"); // CARD-GEN-2
    }
    if (!isAcEntity(this.hass, entityId)) {
      return this._warning("error.not_ac"); // CARD-GEN-1
    }
    const monitoring = this._config.monitoring ?? "always";
    const places = monitoringWidth(monitoring, indicators(this.hass, entityId));
    const controlMaxWidth = this._resizeController.value ? `${this._resizeController.value}px` : undefined;
    return html`
      <ha-card role="group" aria-labelledby="title">
        <ac-monitoring class="monitoring" .hass=${this.hass} .entityId=${entityId} .display=${monitoring}></ac-monitoring>
        <p
          class="title"
          id="title"
          style=${styleMap({ paddingInline: places ? `${places * INDICATOR_WIDTH + 12}px` : undefined })}
        >
          ${this.hass.formatEntityName(stateObj, this._config.name)}
        </p>
        <div class="container">
          <ac-ha-state-control-climate-temperature
            style=${styleMap({ maxWidth: controlMaxWidth })}
            prevent-interaction-on-scroll
            .showCurrentAsPrimary=${this._config.show_current_as_primary ?? false}
            show-secondary
            .emphasis=${phaseEmphasis(stateObj)}
            .stateObj=${stateObj}
          ></ac-ha-state-control-climate-temperature>
        </div>
        <ha-icon-button
          class="more-info"
          .label=${this.hass.localize("ui.panel.lovelace.cards.show_more_info")}
          .path=${mdiDotsVertical}
          @click=${this._handleMoreInfo}
          tabindex="0"
        ></ha-icon-button>
        ${this._config.features?.length
          ? html`<ac-features
              .hass=${this.hass}
              .stateObj=${stateObj}
              .features=${this._config.features}
              .pack=${this._pack(stateObj)}
            ></ac-features>`
          : nothing}
      </ha-card>
    `;
  }

  // The styles of the thermostat card, and the monitoring indicators
  static styles = css`
    :host {
      position: relative;
      display: block;
      height: 100%;
    }
    ha-card {
      position: relative;
      height: 100%;
      width: 100%;
      padding: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: space-between;
    }
    .title {
      width: 100%;
      font-size: var(--ha-font-size-l);
      line-height: var(--ha-line-height-expanded);
      padding: 8px 30px 8px 30px;
      margin: 0;
      text-align: center;
      box-sizing: border-box;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: none;
    }
    .container {
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow: hidden;
      max-width: 100%;
      box-sizing: border-box;
      flex: 1;
    }
    .container:before {
      content: "";
      display: block;
      padding-top: 100%;
    }
    .container > * {
      padding: 8px;
    }
    .more-info {
      position: absolute;
      cursor: pointer;
      top: 0;
      right: 0;
      inset-inline-end: 0px;
      inset-inline-start: initial;
      border-radius: var(--ha-border-radius-pill);
      color: var(--secondary-text-color);
      direction: var(--direction);
    }
    .monitoring {
      position: absolute;
      top: 6px;
      left: 4px;
      inset-inline-start: 4px;
      inset-inline-end: initial;
    }
    ac-features {
      flex: none;
      padding: 0 12px 12px 12px;
    }
    .warning {
      margin: 0;
      padding: 16px;
      color: var(--primary-text-color);
      background-color: rgb(from var(--warning-color) r g b / 0.2);
      border-radius: var(--ha-card-border-radius, 12px);
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    [CARD_TYPE]: AdaptativeClimateCard;
  }
}
