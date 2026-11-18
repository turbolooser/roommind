// @vitest-environment happy-dom
import { afterEach, expect, test } from "vitest";
import { render } from "lit";
import { tempRow } from "../components/shared/temp-row";
import "../card/roommind-room-card";
import type { RoomMindRoomCard } from "../card/roommind-room-card";
import { refreshRooms } from "../card/rooms-feed";
import { roundToStep } from "./schedule-week";
import { parseDecimalEntry } from "./format";
import {
  DEFAULT_TARGET_TEMP_STEP,
  noteTargetStep,
  stepInUnit,
  storedTargetStep,
  targetStep,
} from "./temperature";
import type { HomeAssistant } from "../types";

// Fork: the +/- step of target temperatures is one global setting (`target_temp_step`).

const hassC = { language: "de", config: { unit_system: { temperature: "°C" } } } as HomeAssistant;
const hassF = { language: "en", config: { unit_system: { temperature: "°F" } } } as HomeAssistant;

afterEach(() => {
  noteTargetStep(DEFAULT_TARGET_TEMP_STEP);
  document.body.replaceChildren();
});

test("default step keeps the former 0.5 °C / 1 °F", () => {
  expect(storedTargetStep()).toBe(0.5);
  expect(targetStep(hassC)).toBe(0.5);
  expect(targetStep(hassF)).toBe(1);
});

test("Fahrenheit uses the rounded equivalents of each choice", () => {
  expect([0.1, 0.5, 1].map((s) => stepInUnit(s as 0.1 | 0.5 | 1, hassF))).toEqual([0.2, 1, 2]);
  noteTargetStep(0.1);
  expect(targetStep(hassC)).toBe(0.1);
  expect(targetStep(hassF)).toBe(0.2);
});

test.each([undefined, null, 0.2, 0, "0.1", Number.NaN])(
  "an unknown stored value %s keeps the last known step",
  (value) => {
    noteTargetStep(1);
    noteTargetStep(value);
    expect(storedTargetStep()).toBe(1);
  },
);

test("schedule rounding follows the step without float noise", () => {
  expect(roundToStep(21.74, 0.1)).toBe(21.7);
  expect(roundToStep(21.7 + 0.1, 0.1)).toBe(21.8);
  expect(roundToStep(21.7, 0.5)).toBe(21.5);
});

test.each([
  ["21,7", 21.7],
  [" 21.7 ", 21.7],
  ["-3", -3],
  [",5", 0.5],
  ["21,7,1", Number.NaN],
  ["abc", Number.NaN],
  ["", Number.NaN],
])("parseDecimalEntry(%j)", (text, expected) => {
  expect(parseDecimalEntry(text)).toEqual(expected);
});

async function panelRow(celsius: number, hass = hassC) {
  const changes: number[] = [];
  const host = document.createElement("div");
  document.body.append(host);
  render(
    tempRow({ hass, side: "heat", label: "Comfort", celsius, onChange: (v) => changes.push(v) }),
    host,
  );
  const stepper = host.querySelector("rs-stepper")!;
  await stepper.updateComplete;
  return { stepper, changes };
}

test("panel stepper moves by the chosen step", async () => {
  noteTargetStep(0.1);
  const { stepper, changes } = await panelRow(21.7);
  expect(stepper.step).toBe(0.1);
  const [minus, plus] = stepper.shadowRoot!.querySelectorAll("button");
  plus.click();
  minus.click();
  expect(changes).toEqual([21.8, 21.6]);
});

test("panel stepper with 1 °C snaps an exact value to whole degrees", async () => {
  noteTargetStep(1);
  const { stepper, changes } = await panelRow(21.7);
  stepper.shadowRoot!.querySelectorAll("button")[1].click();
  expect(changes).toEqual([22]);
});

// ─── Dashboard card ─────────────────────────────────────────────────

interface Sent {
  type: string;
  [key: string]: unknown;
}

const ROOM = {
  area_id: "esszimmer",
  display_name: "Esszimmer",
  devices: [{ entity_id: "climate.esszimmer", type: "trv", role: "auto" }],
  climate_mode: "heat_only",
  comfort_heat: 21.7,
  eco_heat: 17,
  live: { mode: "idle", current_temp: 21, target_temp: 21.7 },
};

async function card(step: number) {
  const sent: Sent[] = [];
  const hass = {
    ...hassC,
    states: {},
    entities: {},
    areas: { esszimmer: { area_id: "esszimmer", name: "Esszimmer" } },
    user: { is_admin: true },
    callWS: async (msg: Sent) => {
      sent.push(msg);
      if (msg.type === "roommind/rooms/list") {
        return { rooms: { esszimmer: ROOM }, climate_control_active: true, target_temp_step: step };
      }
      return {};
    },
  } as unknown as HomeAssistant;
  // The card registers itself only once HA has defined <home-assistant> (scoped registry).
  if (!customElements.get("home-assistant")) {
    customElements.define("home-assistant", class extends HTMLElement {});
  }
  await customElements.whenDefined("roommind-room-card");
  const el = document.createElement("roommind-room-card") as RoomMindRoomCard;
  el.setConfig({ type: "custom:roommind-room-card", area: "esszimmer" });
  el.hass = hass;
  document.body.append(el);
  await refreshRooms(true);
  await el.updateComplete;
  const stepper = el.shadowRoot!.querySelector(".temps-section .stepper")!;
  return { el, stepper, sent };
}

const saves = (sent: Sent[]) => sent.filter((m) => m.type === "roommind/rooms/save");

async function flushSave(el: RoomMindRoomCard) {
  // The card debounces temperature saves by 800 ms; flushing is what disconnecting does.
  el.remove();
  await new Promise((r) => setTimeout(r, 0));
}

test("card +/- uses the step from rooms/list", async () => {
  const { el, stepper, sent } = await card(0.1);
  expect(storedTargetStep()).toBe(0.1);
  (stepper.querySelectorAll("button.step")[1] as HTMLButtonElement).click();
  await el.updateComplete;
  expect(stepper.querySelector("input")!.value).toBe("21,8");
  await flushSave(el);
  expect(saves(sent)[0]).toMatchObject({ area_id: "esszimmer", comfort_heat: 21.8 });
});

test("card keeps 0.5 by default", async () => {
  const { el, stepper } = await card(0.5);
  (stepper.querySelectorAll("button.step")[0] as HTMLButtonElement).click();
  await el.updateComplete;
  expect(stepper.querySelector("input")!.value).toBe("21,5");
});

test.each(["Enter", "blur"])("card accepts a typed comma value on %s", async (action) => {
  const { el, stepper, sent } = await card(0.5);
  const input = stepper.querySelector("input")!;
  expect(input.getAttribute("inputmode")).toBe("decimal");
  expect(input.value).toBe("21,7");
  input.value = "22,3";
  input.dispatchEvent(
    action === "blur" ? new Event("blur") : new KeyboardEvent("keydown", { key: "Enter" }),
  );
  input.dispatchEvent(new Event("blur"));
  await el.updateComplete;
  expect(input.value).toBe("22,3");
  await flushSave(el);
  expect(saves(sent)).toHaveLength(1);
  expect(saves(sent)[0]).toMatchObject({ comfort_heat: 22.3 });
});

test.each(["40", "4", "abc", "21,7"])("card rejects %s and restores the value", async (text) => {
  const { el, stepper, sent } = await card(0.5);
  const input = stepper.querySelector("input")!;
  input.value = text;
  input.dispatchEvent(new Event("blur"));
  expect(input.value).toBe("21,7");
  await flushSave(el);
  expect(saves(sent)).toHaveLength(0);
});

test("Escape on the card resets the entry without saving", async () => {
  const { el, stepper, sent } = await card(0.5);
  const input = stepper.querySelector("input")!;
  input.value = "25";
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  expect(input.value).toBe("21,7");
  input.dispatchEvent(new Event("blur"));
  await flushSave(el);
  expect(saves(sent)).toHaveLength(0);
});

// ─── Settings page ──────────────────────────────────────────────────

test("general settings offer the three steps in the user's unit and fire the choice", async () => {
  await import("../components/settings/rs-settings-general");
  const el = document.createElement("rs-settings-general");
  el.hass = hassF;
  document.body.append(el);
  await el.updateComplete;
  const seg = el.shadowRoot!.querySelector("rs-segmented")!;
  await seg.updateComplete;
  const buttons = [...seg.shadowRoot!.querySelectorAll("button")];
  expect(buttons.map((b) => b.textContent!.trim())).toEqual(["0.2 °F", "1 °F", "2 °F"]);
  const fired: unknown[] = [];
  el.addEventListener("setting-changed", (e) => fired.push((e as CustomEvent).detail));
  buttons[0].click();
  buttons[1].click(); // the current choice does not fire again
  expect(fired).toEqual([{ key: "targetTempStep", value: 0.1 }]);
});
