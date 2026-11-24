// Our own list, for the lists in `dropdown` style (CARD_SPEC.md §5.2, D3.1-bis iii).
// The menu opens in the top layer (Popover API): the card does not clip it, and
// a click outside or Escape closes it.

import { mdiCheck, mdiMenuDown } from "@mdi/js";
import { css, html, LitElement, nothing } from "lit";
import { customElement, property, query, state } from "lit/decorators";
import { classMap } from "lit/directives/class-map";
import { fireEvent } from "../ha/common/dom/fire_event";

export interface DropdownOption {
  value: string;
  label: string;
  path?: string;
}

@customElement("ac-dropdown")
export class AcDropdown extends LitElement {
  @property() public label = "";

  @property() public value?: string;

  @property({ attribute: false }) public options: DropdownOption[] = [];

  @property({ attribute: false }) public icon?: string;

  // The tooltip, when it is not the label (a greyed list: CARD-LIST-5)
  @property() public tooltip?: string;

  @property({ type: Boolean, reflect: true }) public disabled = false;

  @state() private _open = false;

  @query("button.trigger") private _trigger!: HTMLButtonElement;

  @query("#menu") private _menu!: HTMLElement;

  private _onScroll = () => this._close();

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener("scroll", this._onScroll, true);
  }

  private _toggle(): void {
    if (this._open) {
      this._close();
    } else {
      this._show();
    }
  }

  private _show(): void {
    if (this.disabled || !this.options.length) {
      return;
    }
    const rect = this._trigger.getBoundingClientRect();
    const menu = this._menu;
    menu.style.minWidth = `${rect.width}px`;
    menu.style.left = `${rect.left}px`;
    menu.showPopover();
    // Below the list, or above when there is no room below
    const below = rect.bottom + 4 + menu.offsetHeight <= window.innerHeight;
    menu.style.top = below ? `${rect.bottom + 4}px` : `${Math.max(4, rect.top - 4 - menu.offsetHeight)}px`;
    window.addEventListener("scroll", this._onScroll, true);
    const current = menu.querySelector<HTMLElement>("[aria-selected='true']") ?? menu.querySelector<HTMLElement>("[role='option']");
    current?.focus();
  }

  private _close(): void {
    if (this._menu?.matches(":popover-open")) {
      this._menu.hidePopover();
    }
  }

  private _toggled(ev: ToggleEvent): void {
    this._open = ev.newState === "open";
    if (!this._open) {
      window.removeEventListener("scroll", this._onScroll, true);
    }
  }

  private _choose(value: string): void {
    this._close();
    this._trigger.focus();
    if (value !== this.value) {
      fireEvent(this, "value-changed", { value });
    }
  }

  private _triggerKey(ev: KeyboardEvent): void {
    if (["ArrowDown", "ArrowUp"].includes(ev.key)) {
      ev.preventDefault();
      this._show();
    }
  }

  private _menuKey(ev: KeyboardEvent): void {
    const items = [...this._menu.querySelectorAll<HTMLElement>("[role='option']")];
    const index = items.indexOf(this.shadowRoot!.activeElement as HTMLElement);
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      const next = (index + (ev.key === "ArrowDown" ? 1 : items.length - 1)) % items.length;
      items[next]?.focus();
    } else if (ev.key === "Home" || ev.key === "End") {
      ev.preventDefault();
      items[ev.key === "Home" ? 0 : items.length - 1]?.focus();
    } else if ((ev.key === "Enter" || ev.key === " ") && index >= 0) {
      ev.preventDefault();
      this._choose(this.options[index].value);
    } else if (ev.key === "Tab") {
      this._close();
    }
  }

  protected render() {
    const current = this.options.find((option) => option.value === this.value);
    return html`
      <button
        class="trigger"
        title=${this.tooltip ?? this.label}
        aria-label=${this.tooltip ?? `${this.label}: ${current?.label ?? this.value ?? ""}`}
        aria-haspopup="listbox"
        aria-expanded=${this._open ? "true" : "false"}
        ?disabled=${this.disabled}
        @click=${this._toggle}
        @keydown=${this._triggerKey}
      >
        ${this.icon ? html`<ha-svg-icon class="icon" .path=${this.icon}></ha-svg-icon>` : nothing}
        <span class="value">${current?.label ?? this.value ?? "—"}</span>
        ${this.disabled ? nothing : html`<ha-svg-icon class="arrow" .path=${mdiMenuDown}></ha-svg-icon>`}
      </button>
      <div id="menu" popover="auto" role="listbox" aria-label=${this.label} @toggle=${this._toggled} @keydown=${this._menuKey}>
        ${this.options.map(
          (option) => html`
            <div
              role="option"
              tabindex="-1"
              aria-selected=${option.value === this.value ? "true" : "false"}
              class=${classMap({ option: true, selected: option.value === this.value })}
              @click=${() => this._choose(option.value)}
            >
              <ha-svg-icon class="check" .path=${mdiCheck}></ha-svg-icon>
              ${option.path ? html`<ha-svg-icon .path=${option.path}></ha-svg-icon>` : nothing}
              <span>${option.label}</span>
            </div>
          `,
        )}
      </div>
    `;
  }

  static styles = css`
    :host {
      display: block;
      min-width: 0;
      --mdc-icon-size: 20px;
    }
    .trigger {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      height: var(--feature-height, 42px);
      padding: 0 8px 0 12px;
      box-sizing: border-box;
      border: none;
      border-radius: var(--feature-border-radius, 12px);
      /* As the background of the mode bar */
      background: rgb(from var(--disabled-color) r g b / 0.2);
      color: var(--primary-text-color);
      font: inherit;
      font-size: var(--ha-font-size-m, 14px);
      cursor: pointer;
      text-align: start;
    }
    .trigger:focus-visible {
      outline: 2px solid var(--primary-color);
      outline-offset: -2px;
    }
    /* Greyed out: faded, as a mode not available (CARD-LIST-5) */
    :host([disabled]) .trigger {
      opacity: 0.4;
      cursor: default;
    }
    .icon {
      flex: none;
      color: var(--secondary-text-color);
    }
    .value {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: var(--ha-font-weight-medium, 500);
    }
    .arrow {
      flex: none;
      color: var(--secondary-text-color);
    }
    #menu {
      position: fixed;
      inset: auto;
      margin: 0;
      padding: 4px;
      border: none;
      border-radius: var(--ha-border-radius-md, 8px);
      background: var(--card-background-color, white);
      color: var(--primary-text-color);
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
      max-height: 50vh;
      overflow-y: auto;
      --mdc-icon-size: 20px;
    }
    .option {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px 8px 8px;
      border-radius: var(--ha-border-radius-sm, 6px);
      cursor: pointer;
      white-space: nowrap;
      outline: none;
    }
    .option:hover,
    .option:focus-visible {
      background: rgb(from var(--primary-color) r g b / 0.1);
    }
    .check {
      visibility: hidden;
      color: var(--primary-color);
    }
    .selected .check {
      visibility: visible;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "ac-dropdown": AcDropdown;
  }
}
