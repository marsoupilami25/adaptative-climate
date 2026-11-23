// The card: our own shell around the copied dial (CARD_ARCHITECTURE.md
// CARD-ARCH-5, §5). It reproduces the shell of the thermostat card of Home
// Assistant: title, ⋮ button, dial sized by the card (CARD-DIAL-1).
// Step 5 of the plan: the shell only, to check the copy. The AC parts come next.

import { ResizeController } from "@lit-labs/observers/resize-controller";
import { mdiDotsVertical } from "@mdi/js";
import { css, html, LitElement, nothing } from "lit";
import { customElement, property, state } from "lit/decorators";
import { styleMap } from "lit/directives/style-map";
import { fireEvent } from "../ha/common/dom/fire_event";
import type { ClimateEntity } from "../ha/data/climate";
import "../ha/state-control/climate/ha-state-control-climate-temperature";
import type { HomeAssistant } from "../ha/types";

export const CARD_TYPE = "adaptative-climate-card";

export interface AdaptativeClimateCardConfig {
  type: string;
  entity: string;
  name?: string;
  show_current_as_primary?: boolean;
}

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

@customElement(CARD_TYPE)
export class AdaptativeClimateCard extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;

  @state() private _config?: AdaptativeClimateCardConfig;

  // The dial gets the height of the container, as on the thermostat card
  private _resizeController = new ResizeController(this, {
    callback: (entries) => {
      const container = entries[0]?.target.shadowRoot?.querySelector(".container") as HTMLElement | undefined;
      return container?.clientHeight;
    },
  });

  public setConfig(config: AdaptativeClimateCardConfig): void {
    if (!config?.entity || config.entity.split(".")[0] !== "climate") {
      throw new Error("Specify an entity from within the climate domain");
    }
    this._config = config;
  }

  public getCardSize(): number {
    return 7;
  }

  public getGridOptions(): GridOptions {
    return { columns: 12, rows: 5, min_columns: 6, min_rows: 2 };
  }

  private _handleMoreInfo(): void {
    fireEvent(this, "hass-more-info", { entityId: this._config!.entity });
  }

  protected render() {
    if (!this.hass || !this._config) {
      return nothing;
    }
    const stateObj = this.hass.states[this._config.entity] as ClimateEntity | undefined;
    if (!stateObj) {
      return html`<ha-card><p class="warning">Entity not available: ${this._config.entity}</p></ha-card>`;
    }
    const controlMaxWidth = this._resizeController.value ? `${this._resizeController.value}px` : undefined;
    return html`
      <ha-card role="group" aria-labelledby="title">
        <p class="title" id="title">${this.hass.formatEntityName(stateObj, this._config.name)}</p>
        <div class="container">
          <ac-ha-state-control-climate-temperature
            style=${styleMap({ maxWidth: controlMaxWidth })}
            prevent-interaction-on-scroll
            .showCurrentAsPrimary=${this._config.show_current_as_primary ?? false}
            show-secondary
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
      </ha-card>
    `;
  }

  // The styles of the thermostat card
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
    .warning {
      padding: 16px;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    [CARD_TYPE]: AdaptativeClimateCard;
  }
}
