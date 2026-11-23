// The device line, feature `ac-device` (CARD_SPEC.md §4).

import { mdiRemote, mdiSyncAlert } from "@mdi/js";
import { css, html, LitElement, nothing } from "lit";
import { customElement, property, state } from "lit/decorators";
import { classMap } from "lit/directives/class-map";
import { styleMap } from "lit/directives/style-map";
import { stateColorCss } from "../ha/common/entity/state_color";
import { climateHvacModeIcon } from "../ha/data/climate";
import type { HomeAssistant } from "../ha/types";
import type { AcClimateEntity } from "./entity";
import { localize } from "./localize";

type Status = "unavailable" | "foreign";

// The status icon and its color (CARD-DEV-3)
const STATUS_ICONS: Record<Status, string> = {
  // the same as the sources problem of the monitoring (CARD-MON-3)
  unavailable: mdiSyncAlert,
  foreign: mdiRemote,
};

@customElement("ac-device-feature")
export class AcDeviceFeature extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @property({ attribute: false }) public stateObj!: AcClimateEntity;

  // The reasons shown on a press, for a touch screen (CARD-DEV-6)
  @state() private _showReasons = false;

  private _name(entityId: string): string {
    const source = this.hass.states[entityId];
    return source ? this.hass.formatEntityName(source) : entityId;
  }

  /** The reasons for the status icon, one per line, and the status shown (CARD-DEV-3 to 5). */
  private _reasons(active: string | null | undefined): { status?: Status; lines: string[] } {
    const lines: string[] = [];
    let status: Status | undefined;
    if (active && (this.hass.states[active]?.state ?? "unavailable") === "unavailable") {
      status = "unavailable"; // wins over foreign (CARD-DEV-4)
      lines.push(localize(this.hass, "device.unavailable", { device: this._name(active) }));
    }
    for (const [entityId, mode] of Object.entries(this.stateObj.attributes.foreign_modes ?? {})) {
      status ??= "foreign";
      const source = this.hass.states[entityId];
      lines.push(
        localize(this.hass, "device.foreign", {
          device: this._name(entityId),
          mode: source ? this.hass.formatEntityState(source, mode) : mode,
        }),
      );
    }
    return { status, lines };
  }

  private _toggleReasons(): void {
    this._showReasons = !this._showReasons;
  }

  protected render() {
    if (!this.hass || !this.stateObj) {
      return nothing;
    }
    const active = this.stateObj.attributes.active_entity_id;
    const { status, lines } = this._reasons(active);
    const text = lines.join("\n");
    return html`
      <div class=${classMap({ line: true, [status ?? "ok"]: true })}>
        ${active
          ? html`
              <ha-svg-icon
                class="mode"
                style=${styleMap({ color: stateColorCss(this.stateObj) })}
                .path=${climateHvacModeIcon(this.stateObj.state)}
              ></ha-svg-icon>
              <span class="name">${this._name(active)}</span>
            `
          : nothing}
        ${status
          ? html`
              <button class="status" title=${text} aria-label=${text} @click=${this._toggleReasons}>
                <ha-svg-icon .path=${STATUS_ICONS[status]}></ha-svg-icon>
              </button>
            `
          : nothing}
      </div>
      ${status && this._showReasons ? html`<div class="reasons" @click=${this._toggleReasons}>${text}</div>` : nothing}
    `;
  }

  static styles = css`
    :host {
      display: block;
      position: relative;
      /* Same height empty or not: the dial does not jump (CARD-LOOK-2) */
      height: 28px;
    }
    .line {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      height: 100%;
      color: var(--secondary-text-color);
      font-size: var(--ha-font-size-m);
      --mdc-icon-size: 20px;
    }
    .name {
      /* One line, an ellipsis when too long (CARD-DEV-2) */
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .unavailable .name,
    .unavailable .status {
      color: var(--error-color);
    }
    .foreign .name,
    .foreign .status {
      color: var(--warning-color);
    }
    .status {
      display: flex;
      padding: 0;
      border: none;
      background: none;
      cursor: pointer;
      flex: none;
    }
    .reasons {
      position: absolute;
      top: 100%;
      left: 50%;
      transform: translateX(-50%);
      z-index: 1;
      max-width: 90%;
      padding: 6px 10px;
      border-radius: var(--ha-border-radius-md, 8px);
      background: var(--card-background-color);
      box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0, 0, 0, 0.3));
      color: var(--primary-text-color);
      font-size: var(--ha-font-size-s, 12px);
      white-space: pre-line;
      cursor: pointer;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "ac-device-feature": AcDeviceFeature;
  }
}
