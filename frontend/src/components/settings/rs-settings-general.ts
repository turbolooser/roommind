/**
 * rs-settings-general – General settings: climate control, display options, +/- step (fork).
 */
import { html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { hasFloors } from "../../utils/dashboard";
import { formatNumber } from "../../utils/format";
import {
  DEFAULT_TARGET_TEMP_STEP,
  TARGET_TEMP_STEPS,
  stepInUnit,
  tempUnit,
  type TargetTempStep,
} from "../../utils/temperature";
import "../shared/rs-segmented";

@customElement("rs-settings-general")
export class RsSettingsGeneral extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public groupByFloor = false;
  @property({ type: Boolean }) public climateControlActive = true;
  @property({ type: Number }) public targetTempStep: TargetTempStep = DEFAULT_TARGET_TEMP_STEP;

  render() {
    const l = this.hass.language;
    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("settings.climate_control_active", l)}
          .secondary=${localize("settings.climate_control_hint", l)}
          .checked=${this.climateControlActive}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("climateControlActive", e.detail)}
        ></rs-list-row>
      </div>
      ${
        hasFloors(this.hass)
          ? html`<div class="settings-section">
              <rs-list-row
                switch
                wrap
                .heading=${localize("settings.group_by_floor", l)}
                .checked=${this.groupByFloor}
                @toggle-changed=${(e: CustomEvent<boolean>) => this._fire("groupByFloor", e.detail)}
              ></rs-list-row>
            </div>`
          : nothing
      }
      <div class="settings-section">
        <span class="field-label">${localize("settings.target_temp_step", l)}</span>
        <rs-segmented
          .label=${localize("settings.target_temp_step", l)}
          .options=${TARGET_TEMP_STEPS.map((step) => ({
            value: String(step),
            label: `${formatNumber(stepInUnit(step, this.hass), this.hass, 0, 1)}\u00a0${tempUnit(this.hass)}`,
          }))}
          .value=${String(this.targetTempStep)}
          @value-changed=${(e: CustomEvent<{ value: string }>) => {
            const step = Number(e.detail.value);
            if (step && step !== this.targetTempStep) this._fire("targetTempStep", step);
          }}
        ></rs-segmented>
        <p class="field-hint">${localize("settings.target_temp_step_hint", l)}</p>
      </div>
    `;
  }

  static styles = [RsSettingsBase.settingsBaseStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-general": RsSettingsGeneral;
  }
}
