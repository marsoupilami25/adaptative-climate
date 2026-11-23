// The monitoring indicators of the header (CARD_SPEC.md §6).

import { mdiSync, mdiSyncAlert, mdiThermometerAlert, mdiThermometerCheck } from "@mdi/js";
import { css, html, LitElement, nothing } from "lit";
import { customElement, property } from "lit/decorators";
import { classMap } from "lit/directives/class-map";
import { fireEvent } from "../ha/common/dom/fire_event";
import type { HomeAssistant } from "../ha/types";
import type { MonitoringDisplay } from "./config";
import { localize } from "./localize";
import { type MonitoringSensor, monitoringSensors } from "./registry";

// Each sensor has its own icons, off and on (CARD-MON-3)
const ICONS: Record<MonitoringSensor, { off: string; on: string }> = {
  sources: { off: mdiSync, on: mdiSyncAlert },
  temperatures: { off: mdiThermometerCheck, on: mdiThermometerAlert },
};

interface Indicator {
  kind: MonitoringSensor;
  entityId: string;
  on: boolean;
}

/** The monitoring sensors of the entry, sources first, with their state. */
export function indicators(hass: HomeAssistant, entityId: string): Indicator[] {
  const sensors = monitoringSensors(hass, entityId);
  return (["sources", "temperatures"] as const).flatMap((kind) => {
    const sensor = sensors[kind];
    return sensor ? [{ kind, entityId: sensor, on: hass.states[sensor]?.state === "on" }] : [];
  });
}

/** The width of an indicator in the header, in px. */
export const INDICATOR_WIDTH = 30;

/** How many places the header gives to the monitoring, for the title. */
export function monitoringWidth(display: MonitoringDisplay, shown: Indicator[]): number {
  if (display === "hidden") {
    return 0;
  }
  if (display === "compact") {
    return shown.length ? 1 : 0;
  }
  return display === "errors" ? shown.filter((indicator) => indicator.on).length : shown.length;
}

@customElement("ac-monitoring")
export class AcMonitoring extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @property({ attribute: false }) public entityId!: string;

  @property({ attribute: false }) public display: MonitoringDisplay = "always";

  private _open(entityId: string): void {
    fireEvent(this, "hass-more-info", { entityId });
  }

  private _text(indicator: Indicator): string {
    return localize(this.hass, `monitoring.${indicator.kind}_${indicator.on ? "on" : "off"}`);
  }

  protected render() {
    if (!this.hass || !this.entityId || this.display === "hidden") {
      return nothing;
    }
    const all = indicators(this.hass, this.entityId);
    if (this.display === "compact") {
      return this._renderDot(all);
    }
    // always: every sensor; errors: the sensors on, from the left (CARD-MON-1)
    const shown = this.display === "errors" ? all.filter((indicator) => indicator.on) : all;
    return shown.map(
      (indicator) => html`
        <ha-icon-button
          class=${classMap({ on: indicator.on })}
          .path=${indicator.on ? ICONS[indicator.kind].on : ICONS[indicator.kind].off}
          .label=${this._text(indicator)}
          @click=${() => this._open(indicator.entityId)}
        ></ha-icon-button>
      `,
    );
  }

  // One dot for both sensors (CARD-MON-4); it opens the sensor on, the sources first (CARD-MON-5)
  private _renderDot(all: Indicator[]) {
    if (!all.length) {
      return nothing;
    }
    const on = all.filter((indicator) => indicator.on);
    const label = on.length ? on.map((indicator) => this._text(indicator)).join("\n") : localize(this.hass, "monitoring.none");
    return html`
      <button
        class=${classMap({ dot: true, on: on.length > 0 })}
        title=${label}
        aria-label=${label}
        @click=${() => this._open((on[0] ?? all[0]).entityId)}
      >
        <span></span>
      </button>
    `;
  }

  static styles = css`
    :host {
      display: flex;
    }
    /* Close together: 30px each, the icon is 24px (CARD-MON-1) */
    ha-icon-button {
      --ha-icon-button-size: 30px;
      --ha-icon-button-padding-inline: 0;
      color: var(--success-color);
    }
    ha-icon-button.on {
      color: var(--error-color);
    }
    .dot {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 30px;
      height: 30px;
      padding: 0;
      border: none;
      background: none;
      cursor: pointer;
    }
    .dot span {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background-color: var(--success-color);
    }
    .dot.on span {
      background-color: var(--error-color);
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "ac-monitoring": AcMonitoring;
  }
}
