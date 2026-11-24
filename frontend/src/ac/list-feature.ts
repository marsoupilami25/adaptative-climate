// The lists: features `ac-preset-modes`, `ac-fan-modes`, `ac-swing-modes`,
// `ac-swing-horizontal-modes` (CARD_SPEC.md §5.2).

import { css, html, LitElement, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators";
import { styleMap } from "lit/directives/style-map";
import { stateColorCss } from "../ha/common/entity/state_color";
import { supportsFeature } from "../ha/common/entity/supports-feature";
import "../ha/components/ha-control-select";
import type { HomeAssistant } from "../ha/types";
import type { ListFeatureConfig, ListType } from "./config";
import "./dropdown";
import type { AcClimateEntity } from "./entity";
import { LISTS, valueIcon } from "./lists";
import { localize } from "./localize";

function attribute(stateObj: AcClimateEntity | undefined, name: string): unknown {
  return (stateObj?.attributes as unknown as Record<string, unknown> | undefined)?.[name];
}

/** The options the current mode offers; maybe none. */
function offered(stateObj: AcClimateEntity, type: ListType): string[] {
  const options = attribute(stateObj, LISTS[type].options);
  return Array.isArray(options) ? (options as string[]) : [];
}

/**
 * A list shows when the AC entity declares its setting: it does in every mode
 * once discovered (ENT-FAN-2), so the card keeps its size (CARD-LIST-1).
 */
export function listShown(stateObj: AcClimateEntity, type: ListType): boolean {
  return supportsFeature(stateObj, LISTS[type].feature);
}

@customElement("ac-list-feature")
export class AcListFeature extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @property({ attribute: false }) public stateObj!: AcClimateEntity;

  @property({ attribute: false }) public config!: ListFeatureConfig;

  // The value shown: the one chosen until the entity answers
  @state() private _value?: string;

  private get _kind() {
    return LISTS[this.config.type];
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("stateObj") || changed.has("config")) {
      this._value = attribute(this.stateObj, this._kind.attribute) as string | undefined;
    }
  }

  private async _valueChanged(ev: CustomEvent<{ value: string }>): Promise<void> {
    const value = ev.detail.value;
    const kind = this._kind;
    const before = this._value;
    this._value = value;
    try {
      await this.hass.callService("climate", kind.service, {
        entity_id: this.stateObj.entity_id,
        [kind.attribute]: value,
      });
    } catch {
      this._value = before; // refused: back to the value of the entity
    }
  }

  protected render() {
    if (!this.hass || !this.stateObj || !this.config) {
      return nothing;
    }
    const kind = this._kind;
    if (!listShown(this.stateObj, this.config.type)) {
      return nothing;
    }
    const values = offered(this.stateObj, this.config.type);
    const label = (value: string) => this.hass.formatEntityAttributeValue(this.stateObj, kind.attribute, value);
    const name = this.hass.formatEntityAttributeName(this.stateObj, kind.attribute);
    // Greyed out without option in the current mode (CARD-LIST-1, 5)
    const empty = !values.length;
    const disabled = this.stateObj.state === "unavailable" || empty;
    const tooltip = empty ? localize(this.hass, "list.not_offered", { name }) : undefined;
    const icon = empty ? (kind.offIcon ?? kind.icon) : kind.icon;
    if (this.config.style === "icons") {
      if (empty) {
        // Nothing to choose: the bar, faded, with the icon of the list (CARD-LIST-5)
        return html`<div class="empty" title=${tooltip} aria-label=${tooltip}><ha-svg-icon .path=${icon}></ha-svg-icon></div>`;
      }
      // A bar, one button per option; the current one filled (CARD-LIST-4).
      // Icons if every value has one, else the labels: a bar of dots cannot be
      // read (CARD-LIST-7)
      const icons = values.map((value) => valueIcon(kind, value));
      const withIcons = icons.every(Boolean);
      return html`
        <ac-ha-control-select
          .options=${values.map((value, index) => ({ value, label: label(value), path: withIcons ? icons[index] : undefined }))}
          .value=${this._value}
          ?hide-option-label=${withIcons}
          .label=${name}
          style=${styleMap({ "--control-select-color": stateColorCss(this.stateObj) })}
          .disabled=${disabled}
          @value-changed=${this._valueChanged}
        ></ac-ha-control-select>
      `;
    }
    // Its name and the current value; pressed, its options (CARD-LIST-2, 3)
    return html`
      <ac-dropdown
        .icon=${icon}
        .label=${name}
        .tooltip=${tooltip}
        .value=${this._value}
        .options=${values.map((value) => ({ value, label: label(value), path: valueIcon(kind, value) }))}
        .disabled=${disabled}
        @value-changed=${this._valueChanged}
      ></ac-dropdown>
    `;
  }

  static styles = css`
    :host {
      display: block;
      min-width: 0;
    }
    .empty {
      display: flex;
      align-items: center;
      justify-content: center;
      height: var(--feature-height);
      border-radius: var(--feature-border-radius);
      background: rgb(from var(--disabled-color) r g b / 0.2);
      color: var(--primary-text-color);
      opacity: 0.4;
      --mdc-icon-size: 20px;
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
    "ac-list-feature": AcListFeature;
  }
}
