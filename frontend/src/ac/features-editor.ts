// The features in the editor: add, remove, order, options (CARD-CONF-4), as
// the features of the thermostat card in its editor.

import { mdiArrowDown, mdiArrowUp, mdiChevronDown, mdiChevronUp, mdiDelete, mdiFormatListBulleted, mdiTuneVertical } from "@mdi/js";
import { css, html, LitElement, nothing } from "lit";
import { customElement, property, state } from "lit/decorators";
import { fireEvent } from "../ha/common/dom/fire_event";
import { climateHvacModeIcon } from "../ha/data/climate";
import type { HomeAssistant } from "../ha/types";
import { FEATURE_ORDER, type FeatureConfig, LIST_TYPES, type ListType } from "./config";
import type { AcClimateEntity } from "./entity";
import { LISTS } from "./lists";
import { localize } from "./localize";

const ICONS: Record<string, string> = {
  "ac-device": mdiFormatListBulleted,
  "ac-hvac-modes": climateHvacModeIcon("heat_cool"),
  ...Object.fromEntries(LIST_TYPES.map((type) => [type, LISTS[type].icon])),
};

// Proposed in this order, each one once (CARD-CONF-4)
const ORDER = FEATURE_ORDER.map((feature) => feature.type);

@customElement("ac-features-editor")
export class AcFeaturesEditor extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @property({ attribute: false }) public stateObj?: AcClimateEntity;

  @property({ attribute: false }) public features: FeatureConfig[] = [];

  // The feature whose options are open
  @state() private _open?: number;

  private _t(key: string): string {
    return localize(this.hass, `editor.${key}`);
  }

  private _set(features: FeatureConfig[]): void {
    fireEvent(this, "features-changed", { features });
  }

  private _move(index: number, by: number): void {
    const features = [...this.features];
    const [moved] = features.splice(index, 1);
    features.splice(index + by, 0, moved);
    this._open = this._open === index ? index + by : this._open;
    this._set(features);
  }

  private _remove(index: number): void {
    this._open = undefined;
    this._set(this.features.filter((_, i) => i !== index));
  }

  private _add(type: string): void {
    if (type) {
      this._set([...this.features, { type } as FeatureConfig]);
    }
  }

  private _options(index: number, changes: Record<string, unknown>): void {
    const feature: Record<string, unknown> = { ...this.features[index], ...changes };
    for (const key of Object.keys(changes)) {
      if (feature[key] === undefined || (Array.isArray(feature[key]) && !(feature[key] as unknown[]).length)) {
        delete feature[key];
      }
    }
    this._set(this.features.map((item, i) => (i === index ? (feature as unknown as FeatureConfig) : item)));
  }

  // The options of a feature (CARD-CONF-2)
  private _schema(feature: FeatureConfig) {
    if (feature.type === "ac-hvac-modes") {
      const modes: string[] = this.stateObj?.attributes.hvac_modes ?? ["off", "heat", "cool", "heat_cool", "auto", "dry", "fan_only"];
      const label = (mode: string) => (this.stateObj ? this.hass.formatEntityState(this.stateObj, mode) : mode);
      return [
        {
          name: "hvac_modes",
          selector: { select: { multiple: true, reorder: true, mode: "list", options: modes.map((value) => ({ value, label: label(value) })) } },
        },
      ];
    }
    if ((LIST_TYPES as readonly string[]).includes(feature.type)) {
      return [
        {
          name: "style",
          selector: {
            select: {
              mode: "dropdown",
              options: ["dropdown", "icons"].map((value) => ({ value, label: this._t(`style_${value}`) })),
            },
          },
        },
      ];
    }
    return undefined;
  }

  private _data(feature: FeatureConfig): Record<string, unknown> {
    if (feature.type === "ac-hvac-modes") {
      return { hvac_modes: feature.hvac_modes ?? this.stateObj?.attributes.hvac_modes ?? [] };
    }
    return { style: "dropdown", ...feature };
  }

  protected render() {
    const missing = ORDER.filter((type) => !this.features.some((feature) => feature.type === type));
    return html`
      <div class="title">${this._t("features")}</div>
      ${this.features.map((feature, index) => {
        const schema = this._schema(feature);
        const open = this._open === index;
        return html`
          <div class="feature">
            <ha-svg-icon .path=${ICONS[feature.type] ?? mdiTuneVertical}></ha-svg-icon>
            <span class="name">${this._t(feature.type)}</span>
            ${schema
              ? html`<ha-icon-button
                  .label=${this._t("options")}
                  .path=${open ? mdiChevronUp : mdiChevronDown}
                  @click=${() => (this._open = open ? undefined : index)}
                ></ha-icon-button>`
              : nothing}
            <ha-icon-button .label=${this._t("move_up")} .path=${mdiArrowUp} .disabled=${index === 0} @click=${() => this._move(index, -1)}></ha-icon-button>
            <ha-icon-button
              .label=${this._t("move_down")}
              .path=${mdiArrowDown}
              .disabled=${index === this.features.length - 1}
              @click=${() => this._move(index, 1)}
            ></ha-icon-button>
            <ha-icon-button .label=${this._t("remove")} .path=${mdiDelete} @click=${() => this._remove(index)}></ha-icon-button>
          </div>
          ${schema && open
            ? html`<ha-form
                class="options"
                .hass=${this.hass}
                .data=${this._data(feature)}
                .schema=${schema}
                .computeLabel=${(item: { name: string }) => this._t(item.name)}
                @value-changed=${(ev: CustomEvent) => this._options(index, ev.detail.value)}
              ></ha-form>`
            : nothing}
        `;
      })}
      ${missing.length
        ? html`<ha-form
            .hass=${this.hass}
            .data=${{}}
            .schema=${[
              {
                name: "add",
                selector: { select: { mode: "dropdown", options: missing.map((type) => ({ value: type, label: this._t(type as ListType) })) } },
              },
            ]}
            .computeLabel=${() => this._t("add")}
            @value-changed=${(ev: CustomEvent) => this._add(ev.detail.value.add)}
          ></ha-form>`
        : nothing}
    `;
  }

  static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .title {
      font-size: var(--ha-font-size-l, 16px);
      font-weight: var(--ha-font-weight-medium, 500);
    }
    .feature {
      display: flex;
      align-items: center;
      gap: 4px;
      padding-inline-start: 8px;
      border: 1px solid var(--divider-color);
      border-radius: var(--ha-border-radius-md, 8px);
    }
    .feature ha-svg-icon {
      color: var(--secondary-text-color);
    }
    .name {
      flex: 1;
      min-width: 0;
      padding-inline-start: 8px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .options {
      display: block;
      padding: 0 8px 8px;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "ac-features-editor": AcFeaturesEditor;
  }
}
