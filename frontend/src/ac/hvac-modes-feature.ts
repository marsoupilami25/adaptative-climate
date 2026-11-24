// The mode bar, feature `ac-hvac-modes` (CARD_SPEC.md §5.1), on the copied
// ha-control-select (D3.1 c).

import { css, html, LitElement, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators";
import { live } from "lit/directives/live";
import { styleMap } from "lit/directives/style-map";
import { stateColorCss } from "../ha/common/entity/state_color";
import "../ha/components/ha-control-select";
import type { ControlSelectOption } from "../ha/components/ha-control-select";
import { climateHvacModeIcon } from "../ha/data/climate";
import type { HomeAssistant } from "../ha/types";
import type { HvacModesFeatureConfig } from "./config";
import type { AcClimateEntity } from "./entity";
import { localize } from "./localize";

/** The modes of the bar: those of the option, else those of the entity, in their order (CARD-MODE-2). */
export function barModes(stateObj: AcClimateEntity, config: HvacModesFeatureConfig): string[] {
  const offered: string[] = stateObj.attributes.hvac_modes ?? [];
  return config.hvac_modes ? config.hvac_modes.filter((mode) => offered.includes(mode)) : offered;
}

@customElement("ac-hvac-modes-feature")
export class AcHvacModesFeature extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @property({ attribute: false }) public stateObj!: AcClimateEntity;

  @property({ attribute: false }) public config: HvacModesFeatureConfig = { type: "ac-hvac-modes" };

  // The mode shown: the one pressed until the entity answers, as on the thermostat card
  @state() private _currentMode?: string;

  // Why a greyed mode was not asked for, for a few seconds (CARD-MODE-4)
  @state() private _notice?: string;

  private _noticeTimer?: number;

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.clearTimeout(this._noticeTimer);
  }

  private _showNotice(text: string): void {
    this._notice = text;
    window.clearTimeout(this._noticeTimer);
    this._noticeTimer = window.setTimeout(() => (this._notice = undefined), 4000);
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("stateObj")) {
      this._currentMode = this.stateObj?.state;
    }
  }

  private _devices(mode: string): string[] {
    const sources = this.stateObj.attributes.mode_entity_ids ?? {};
    const ids = sources[mode] ? [sources[mode]] : mode === "heat_cool" ? [sources.heat, sources.cool] : [];
    return ids.filter(Boolean).map((id) => {
      const source = this.hass.states[id];
      return source ? this.hass.formatEntityName(source) : id;
    });
  }

  private _option(mode: string): ControlSelectOption {
    // The tooltip gives the mode and its devices (CARD-MODE-5)
    const label = [this.hass.formatEntityState(this.stateObj, mode), ...this._devices(mode)].join(" · ");
    return {
      value: mode,
      label,
      path: climateHvacModeIcon(mode),
      // Greyed out, still pressable: the integration answers (CARD-MODE-4)
      dimmed: (this.stateObj.attributes.unavailable_modes ?? []).includes(mode),
    };
  }

  private async _valueChanged(ev: CustomEvent<{ value: string }>): Promise<void> {
    const mode = ev.detail.value;
    if (mode === this.stateObj.state) {
      return;
    }
    if ((this.stateObj.attributes.unavailable_modes ?? []).includes(mode)) {
      // The entity tells it would refuse it: say why, ask nothing (CARD-MODE-4)
      this._currentMode = this.stateObj.state;
      const devices = this._devices(mode).join(", ");
      const name = this.hass.formatEntityState(this.stateObj, mode);
      this._showNotice(
        devices
          ? localize(this.hass, "mode.not_available", { mode: name, devices })
          : localize(this.hass, "mode.not_available_unknown", { mode: name }),
      );
      return;
    }
    this._notice = undefined;
    this._currentMode = mode;
    try {
      await this.hass.callService("climate", "set_hvac_mode", {
        entity_id: this.stateObj.entity_id,
        hvac_mode: mode,
      });
    } catch {
      this._currentMode = this.stateObj.state; // refused: back to the mode of the entity
    }
  }

  protected render() {
    if (!this.hass || !this.stateObj) {
      return nothing;
    }
    return html`
      <ac-ha-control-select
        .options=${barModes(this.stateObj, this.config).map((mode) => this._option(mode))}
        .value=${live(this._currentMode)}
        hide-option-label
        .label=${this.hass.formatEntityAttributeName(this.stateObj, "hvac_modes")}
        style=${styleMap({ "--control-select-color": stateColorCss(this.stateObj) })}
        .disabled=${this.stateObj.state === "unavailable"}
        @value-changed=${this._valueChanged}
      ></ac-ha-control-select>
      ${this._notice
        ? html`<div class="notice" role="status" @click=${() => (this._notice = undefined)}>${this._notice}</div>`
        : nothing}
    `;
  }

  // The styles of the features of Home Assistant
  static styles = css`
    :host {
      display: block;
      position: relative;
    }
    /* As the bubble of the device line (CARD-DEV-6) */
    .notice {
      position: absolute;
      top: 100%;
      left: 50%;
      transform: translateX(-50%);
      z-index: 1;
      margin-top: 4px;
      max-width: 90%;
      padding: 6px 10px;
      border-radius: var(--ha-border-radius-md, 8px);
      background: var(--card-background-color);
      box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0, 0, 0, 0.3));
      color: var(--primary-text-color);
      font-size: var(--ha-font-size-s, 12px);
      cursor: pointer;
    }
    ac-ha-control-select {
      --control-select-padding: 0;
      --control-select-thickness: var(--feature-height);
      --control-select-border-radius: var(--feature-border-radius);
      --control-select-button-border-radius: var(--feature-border-radius);
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "ac-hvac-modes-feature": AcHvacModesFeature;
  }
}
