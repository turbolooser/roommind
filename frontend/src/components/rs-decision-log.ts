/**
 * rs-decision-log – Why-log tab (fork): one line per room whenever its mode, target or
 * reason changed, newest first, the last 14 days. Filter by room with the chips.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../types";
import { localize, type TranslationKey } from "../utils/localize";
import { formatTempLocale } from "../utils/temperature";
import { formatDayTime, haTimeZone } from "../utils/analytics-time";
import { tokens } from "../styles/tokens";
import type { ChipItem } from "./shared/rs-chip-group";
import "./shared/rs-chip-group";

export interface DecisionLogEntry {
  area_id: string;
  ts: number;
  mode: "heating" | "cooling" | "idle";
  reason: string;
  target_reason: string;
  heat: number | null;
  cool: number | null;
  current: number | null;
  outdoor: number | null;
  windows?: string[];
}

const ALL_ROOMS = "__all__";
const MAX_LINES = 1000;

@customElement("rs-decision-log")
export class RsDecisionLog extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Object }) public rooms: Record<string, RoomConfig> = {};

  @state() private _room = ALL_ROOMS;
  @state() private _entries: DecisionLogEntry[] = [];
  @state() private _loading = true;
  @state() private _error = "";

  private _refresh?: ReturnType<typeof setInterval>;
  private _fetchId = 0;

  connectedCallback() {
    super.connectedCallback();
    this._fetch();
    this._refresh = setInterval(() => this._fetch(), 60_000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._refresh) {
      clearInterval(this._refresh);
      this._refresh = undefined;
    }
  }

  protected updated(changed: Map<string, unknown>) {
    if (changed.has("_room") && changed.get("_room") !== undefined) this._fetch();
  }

  private async _fetch() {
    if (!this.hass) return;
    const fetchId = ++this._fetchId;
    const msg: Record<string, unknown> = { type: "roommind/decision_log/get", limit: MAX_LINES };
    if (this._room !== ALL_ROOMS) msg.area_id = this._room;
    try {
      const result = await this.hass.callWS<{ entries: DecisionLogEntry[] }>(msg);
      if (fetchId !== this._fetchId) return;
      this._entries = result.entries;
      this._error = "";
    } catch (err) {
      if (fetchId !== this._fetchId) return;
      this._error = String((err as { message?: string })?.message ?? err);
    } finally {
      if (fetchId === this._fetchId) this._loading = false;
    }
  }

  private _roomName(areaId: string): string {
    return this.rooms[areaId]?.display_name || this.hass?.areas?.[areaId]?.name || areaId;
  }

  private _chips(l: string): ChipItem[] {
    return [
      {
        id: ALL_ROOMS,
        label: localize("decision_log.all_rooms", l),
        icon: "mdi:home-outline",
        active: this._room === ALL_ROOMS,
      },
      ...Object.keys(this.rooms).map((areaId) => ({
        id: areaId,
        label: this._roomName(areaId),
        icon: this.hass?.areas?.[areaId]?.icon || "mdi:texture-box",
        active: areaId === this._room,
      })),
    ];
  }

  private _onChip(e: CustomEvent<string>) {
    e.stopPropagation();
    if (e.detail && e.detail !== this._room) {
      this._loading = true;
      this._room = e.detail;
    }
  }

  private _temp(value: number | null): string {
    return value == null ? "–" : `${formatTempLocale(value, this.hass)}°`;
  }

  private _target(entry: DecisionLogEntry, l: string): string {
    if (entry.heat == null && entry.cool == null) return localize("decision_log.target_off", l);
    if (entry.mode === "cooling" || entry.heat == null) return this._temp(entry.cool);
    if (entry.mode === "heating" || entry.cool == null) return this._temp(entry.heat);
    return `${this._temp(entry.heat)} – ${this._temp(entry.cool)}`;
  }

  private _windowNames(entry: DecisionLogEntry): string {
    return (entry.windows ?? [])
      .map((eid) => (this.hass?.states?.[eid]?.attributes?.friendly_name as string) || eid)
      .join(", ");
  }

  render() {
    const l = this.hass.language;
    const tz = haTimeZone(this.hass);
    const showRoom = this._room === ALL_ROOMS;
    return html`
      <rs-chip-group
        scrollable
        .label=${localize("decision_log.room", l)}
        .chips=${this._chips(l)}
        @chip-clicked=${this._onChip}
      ></rs-chip-group>
      <p class="hint">${localize("decision_log.hint", l)}</p>
      ${
        this._error
          ? html`<div class="error" role="alert">${this._error}</div>`
          : this._loading
            ? html`<div class="empty">${localize("panel.loading", l)}</div>`
            : this._entries.length === 0
              ? html`<div class="empty">${localize("decision_log.empty", l)}</div>`
              : html`<ul class="log">
                  ${this._entries.map((entry) => {
                    const windows = this._windowNames(entry);
                    return html`<li class="line">
                      <div class="head">
                        <time datetime=${new Date(entry.ts * 1000).toISOString()}
                          >${formatDayTime(entry.ts * 1000, l, tz)}</time
                        >
                        ${showRoom ? html`<span class="room">${this._roomName(entry.area_id)}</span>` : nothing}
                        <span class="mode ${entry.mode}"
                          >${localize(`mode.${entry.mode}` as TranslationKey, l)}</span
                        >
                      </div>
                      <div class="reason">
                        ${localize(`decision_log.reason.${entry.reason}` as TranslationKey, l)}
                        ${windows ? html`<span class="windows">(${windows})</span>` : nothing}
                      </div>
                      <div class="values">
                        <span
                          >${localize("decision_log.target", l)}: ${this._target(entry, l)}
                          (${localize(`decision_log.target_reason.${entry.target_reason}` as TranslationKey, l)})</span
                        >
                        <span
                          >${localize("decision_log.current", l)}:
                          ${this._temp(entry.current)}</span
                        >
                        <span
                          >${localize("decision_log.outdoor", l)}:
                          ${this._temp(entry.outdoor)}</span
                        >
                      </div>
                    </li>`;
                  })}
                </ul>`
      }
    `;
  }

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        padding: var(--rs-space-4);
        max-width: 900px;
        margin: 0 auto;
      }
      .hint {
        color: var(--secondary-text-color);
        font-size: var(--rs-font-sm);
        margin: var(--rs-space-3) 0;
      }
      .empty,
      .error {
        padding: var(--rs-space-6) 0;
        text-align: center;
        color: var(--secondary-text-color);
      }
      .error {
        color: var(--rs-err-text);
      }
      .log {
        list-style: none;
        margin: 0;
        padding: 0;
        background: var(--rs-surface);
        border-radius: var(--rs-radius);
        border: 1px solid var(--rs-border);
      }
      .line {
        padding: var(--rs-space-3) var(--rs-space-4);
        border-bottom: 1px solid var(--rs-border);
      }
      .line:last-child {
        border-bottom: none;
      }
      .head {
        display: flex;
        flex-wrap: wrap;
        gap: var(--rs-space-2);
        align-items: baseline;
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }
      .room {
        font-weight: 500;
        color: var(--primary-text-color);
      }
      .mode {
        padding: 0 var(--rs-space-2);
        border-radius: var(--rs-radius-sm);
        background: var(--rs-fill);
      }
      .mode.heating {
        color: var(--rs-heat-text);
      }
      .mode.cooling {
        color: var(--rs-cool-text);
      }
      .reason {
        font-size: var(--rs-font-md);
        margin: var(--rs-space-1) 0;
      }
      .windows {
        color: var(--secondary-text-color);
      }
      .values {
        display: flex;
        flex-wrap: wrap;
        gap: var(--rs-space-1) var(--rs-space-4);
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-decision-log": RsDecisionLog;
  }
}
