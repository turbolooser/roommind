import { formatNumber } from "./format";
import { HomeAssistant } from "../types";

export function usesFahrenheit(hass: HomeAssistant): boolean {
  return hass.config?.unit_system?.temperature === "°F";
}

export function tempUnit(hass: HomeAssistant): string {
  return usesFahrenheit(hass) ? "°F" : "°C";
}

export function toDisplay(celsius: number, hass: HomeAssistant): number {
  return usesFahrenheit(hass) ? (celsius * 9) / 5 + 32 : celsius;
}

export function toCelsius(display: number, hass: HomeAssistant): number {
  return usesFahrenheit(hass) ? ((display - 32) * 5) / 9 : display;
}

export function toDisplayDelta(celsiusDelta: number, hass: HomeAssistant): number {
  return usesFahrenheit(hass) ? (celsiusDelta * 9) / 5 : celsiusDelta;
}

export function toCelsiusDelta(displayDelta: number, hass: HomeAssistant): number {
  return usesFahrenheit(hass) ? (displayDelta * 5) / 9 : displayDelta;
}

export function formatTemp(celsius: number, hass: HomeAssistant, decimals = 1): string {
  return toDisplay(celsius, hass).toFixed(decimals);
}

/**
 * Fork: choices of the global "+/- step" setting (`target_temp_step`, °C). Fahrenheit uses the
 * rounded equivalents, so the default 0.5 °C keeps the former 1 °F.
 */
export const TARGET_TEMP_STEPS = [0.1, 0.5, 1] as const;
export type TargetTempStep = (typeof TARGET_TEMP_STEPS)[number];
export const DEFAULT_TARGET_TEMP_STEP: TargetTempStep = 0.5;
const FAHRENHEIT_STEPS: Record<TargetTempStep, number> = { 0.1: 0.2, 0.5: 1, 1: 2 };

/** The stored step, learned from every rooms/list answer; card and panel each keep a copy. */
let targetStepC: TargetTempStep = DEFAULT_TARGET_TEMP_STEP;

export function noteTargetStep(step: unknown): void {
  const known = TARGET_TEMP_STEPS.find((s) => s === step);
  if (known !== undefined) targetStepC = known;
}

export function storedTargetStep(): TargetTempStep {
  return targetStepC;
}

/** One of the step choices in the user's unit. */
export function stepInUnit(step: TargetTempStep, hass: HomeAssistant): number {
  return usesFahrenheit(hass) ? FAHRENHEIT_STEPS[step] : step;
}

/** Step of the +/- buttons on a target temperature, in the user's unit. */
export function targetStep(hass: HomeAssistant): number {
  return stepInUnit(targetStepC, hass);
}

export function tempStep(hass: HomeAssistant): string {
  return usesFahrenheit(hass) ? "1" : "0.5";
}

export function tempRange(
  minC: number,
  maxC: number,
  hass: HomeAssistant,
): { min: string; max: string } {
  return {
    min: String(Math.round(toDisplay(minC, hass))),
    max: String(Math.round(toDisplay(maxC, hass))),
  };
}

/**
 * Plausibility bounds for room target temperatures (°C).
 * Mirrors MIN_TARGET_TEMP/MAX_TARGET_TEMP in the backend's const.py — schedule
 * block temps outside this range are ignored there (#395), so the panel must
 * not present them as the active target either.
 */
export const MIN_TARGET_TEMP_C = 5;
export const MAX_TARGET_TEMP_C = 35;

/** True when a schedule block temperature (in HA display units) is usable. */
export function isPlausibleTargetTemp(displayValue: unknown, hass: HomeAssistant): boolean {
  const num = Number(displayValue);
  if (!Number.isFinite(num)) return false;
  const celsius = toCelsius(num, hass);
  return celsius >= MIN_TARGET_TEMP_C && celsius <= MAX_TARGET_TEMP_C;
}

/** °C value converted to the display unit and formatted in the user's language. */
export function formatTempLocale(
  celsius: number,
  hass: HomeAssistant,
  minDecimals = 1,
  maxDecimals = minDecimals,
): string {
  return formatNumber(toDisplay(celsius, hass), hass, minDecimals, maxDecimals);
}
