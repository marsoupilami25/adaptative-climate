// The mode bar, feature `ac-hvac-modes` (CARD_SPEC.md §5.1), on the copied
// ha-control-select (D3.1 c).

import { css, html, LitElement, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators";
import { styleMap } from "lit/directives/style-map";
import { stateColorCss } from "../ha/common/entity/state_color";
import "../ha/components/ha-control-select";
import type { ControlSelectOption } from "../ha/components/ha-control-select";
import { climateHvacModeIcon } from "../ha/data/climate";
import type { HomeAssistant } from "../ha/types";
import type { HvacModesFeatureConfig } from "./config";
import type { AcClimateEntity } from "./entity";

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
        .value=${this._currentMode}
        hide-option-label
        .label=${this.hass.formatEntityAttributeName(this.stateObj, "hvac_modes")}
        style=${styleMap({ "--control-select-color": stateColorCss(this.stateObj) })}
        .disabled=${this.stateObj.state === "unavailable"}
        @value-changed=${this._valueChanged}
      ></ac-ha-control-select>
    `;
  }

  // The styles of the features of Home Assistant
  static styles = css`
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
