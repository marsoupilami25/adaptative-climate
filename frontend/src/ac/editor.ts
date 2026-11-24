// The visual editor of the card (CARD_SPEC.md §8: CARD-CONF-4, 5; D3.2 b):
// ha-form for the options, our own list for the features.

import { css, html, LitElement, nothing } from "lit";
import { customElement, property, state } from "lit/decorators";
import { fireEvent } from "../ha/common/dom/fire_event";
import type { HomeAssistant } from "../ha/types";
import { type AdaptativeClimateCardConfig, type FeatureConfig, MONITORING_DISPLAYS } from "./config";
import type { AcClimateEntity } from "./entity";
import "./features-editor";
import { localize } from "./localize";
import { DOMAIN } from "./registry";

declare global {
  interface HASSDomEvents {
    "config-changed": { config: AdaptativeClimateCardConfig };
    "features-changed": { features: FeatureConfig[] };
  }
}

/**
 * ha-form is loaded on demand by the frontend (CARD-ARCH-9): ask it for the
 * editor of the thermostat card, which imports it.
 */
export async function loadHaForm(): Promise<void> {
  if (customElements.get("ha-form")) {
    return;
  }
  const helpers = await (window as unknown as { loadCardHelpers?: () => Promise<any> }).loadCardHelpers?.();
  const card = await helpers?.createCardElement({ type: "thermostat", entity: "climate.loader" });
  await card?.constructor?.getConfigElement?.();
}

@customElement("adaptative-climate-card-editor")
export class AdaptativeClimateCardEditor extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;

  @state() private _config?: AdaptativeClimateCardConfig;

  public setConfig(config: AdaptativeClimateCardConfig): void {
    this._config = config;
  }

  private _schema() {
    const option = (value: string) => ({ value, label: localize(this.hass, `editor.monitoring_${value}`) });
    return [
      {
        name: "entity",
        required: true,
        selector: { entity: { filter: { integration: DOMAIN, domain: "climate" } } },
      },
      { name: "name", selector: { text: {} } },
      {
        name: "monitoring",
        selector: { select: { mode: "dropdown", options: MONITORING_DISPLAYS.map(option) } },
      },
      { name: "show_current_as_primary", selector: { boolean: {} } },
    ];
  }

  private _label = (schema: { name: string }) => localize(this.hass, `editor.${schema.name}`);

  /** The new configuration: the keys of the dashboard kept, the empty ones removed (CARD-CONF-5). */
  private _changed(changes: Partial<AdaptativeClimateCardConfig>): void {
    const config: Record<string, unknown> = { ...this._config, ...changes };
    for (const key of Object.keys(changes)) {
      if (config[key] === undefined || config[key] === "") {
        delete config[key];
      }
    }
    this._config = config as unknown as AdaptativeClimateCardConfig;
    fireEvent(this, "config-changed", { config: this._config });
  }

  protected render() {
    if (!this.hass || !this._config) {
      return nothing;
    }
    const data = { monitoring: "always", show_current_as_primary: false, ...this._config };
    return html`
      <ha-form
        .hass=${this.hass}
        .data=${data}
        .schema=${this._schema()}
        .computeLabel=${this._label}
        @value-changed=${(ev: CustomEvent) => this._changed(ev.detail.value)}
      ></ha-form>
      <ac-features-editor
        .hass=${this.hass}
        .stateObj=${this.hass.states[this._config.entity] as AcClimateEntity | undefined}
        .features=${this._config.features ?? []}
        @features-changed=${(ev: CustomEvent) => this._changed({ features: ev.detail.features })}
      ></ac-features-editor>
    `;
  }

  static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      gap: 24px;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "adaptative-climate-card-editor": AdaptativeClimateCardEditor;
  }
}
