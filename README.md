# RoomMind — turbolooser fork

[![Based on RoomMind](https://img.shields.io/badge/based%20on-snazzybean%2Froommind-orange.svg)](https://github.com/snazzybean/roommind)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.5%2B-blue.svg)](https://www.home-assistant.io/)
[![License](https://img.shields.io/github/license/turbolooser/roommind)](https://github.com/turbolooser/roommind/blob/main/LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/turbolooser/roommind)](https://github.com/turbolooser/roommind/releases/latest)

**Intelligent room climate control for Home Assistant** — self-learning thermal model, proportional valve control, and a dedicated management panel.

This is a personal fork tuned for a **Daikin multisplit** (3 indoor heads on one outdoor compressor, controlled via [Faikin](https://github.com/revk/ESP32-Faikin) over MQTT).

---

## A big thank-you

This project is built entirely on the excellent work of **[snazzybean](https://github.com/snazzybean)** and the original **[RoomMind](https://github.com/snazzybean/roommind)** integration. All the hard parts — the EKF thermal model, the MPC optimizer, the panel, the solar-gain learning — are theirs. Hut ab und vielen Dank für ein wirklich durchdachtes Stück Software. 🙏

This fork only adds a layer of tuning on top, specifically for running several AC heads off a single inverter compressor. It is MIT-licensed, just like the original. If you found your way here, you almost certainly want the upstream project first.

**→ Full feature documentation, screenshots and how-it-works: see the [upstream README](https://github.com/snazzybean/roommind#readme).**

---

## What this fork adds

Everything from upstream, plus the tunings below. Each is **opt-in or backwards-compatible** — with the new features at their defaults, behaviour is identical to upstream.

## Daikin Multisplit Tunings

A multisplit is one outdoor compressor feeding several indoor units. That creates problems a per-room controller normally ignores: short-cycling the shared compressor, heads fighting over heat-vs-cool, and an inverter that throttles itself behind its own deadband. These tunings address exactly that.

### 1. Compressor-group protection
Define a group of `climate.*` devices that share one outdoor unit. The group enforces anti-short-cycle timing and mode coherence.

- **Minimum run / off time** — default `20 min` / `10 min`. The compressor is never asked to stop or restart faster than this.
- **`enforce_uniform_mode`** — all heads in the group are kept in the same heat/cool mode (multisplit physics: the outdoor unit can only do one at a time).
- **Conflict resolution** — `outdoor_temp` decides heat vs cool when heads disagree.

### 2. Compressor demand control
Instead of bang-bang per head, RoomMind writes a single **compressor capacity limit (%)** to the Faikin demand-control select (`select.<unit>_demand_control`), aggregated from all active heads.

- `demand_min` / `demand_max` — default `30` / `95` %. `demand_max` is a pure safety ceiling.
- `demand_hysteresis` — `10` pts (don't re-apply small changes).
- `demand_min_hold_minutes` — `10 min` between genuine changes (anti-thrash).

### 3. Weather feedforward + Δ-trim
The demand baseline follows outdoor temperature, with a narrow symmetric trim on the summed temperature error of the active zones — reverse-engineered from a proven external controller.

- Feedforward curve (outdoor °C → base %): `>12 → 30`, `>8 → 35`, `>4 → 45`, `>0 → 55`, else `70`.
- Δ-trim range `−15 … +25` pts. Steady state ≈ base; mild peak ≈ 60.

### 4. Anti-ping-pong slew
An inverter cycling around setpoint would otherwise flap the demand cap every few minutes. Demand **rises immediately** (cover a real heat/cool need) but only **steps down** once the active zones have stayed satisfied (Σδ ≤ `0.3 K`) for `demand_down_hold_minutes` (default `5 min`, `0` = legacy immediate).

- A diagnostic sensor `sensor.roommind_demand_<group>_flaps` counts applied demand changes per rolling hour — near `0` when settled, high under a limit cycle.

### 5. PV-surplus boost (opt-in, off by default)
When the home produces solar surplus that would otherwise be exported cheap, lift the demand cap so the AC soaks the overflow into the building's thermal mass.

- `pv_surplus_sensor` — you feed one Watt value (built however your inverter/evcc/grid-meter setup likes).
- Engages after `≥ 1500 W` sustained for `≥ 30 min`; optional `pv_battery_soc_sensor` gates it (home battery keeps charge priority below `90 %`).
- Adds `+15` pts while cooling, `+10` pts while heating, on top of base+trim. Final `demand_max` clamp still rules.

### 6. AC inverter setpoint strategy
Per device, choose **proportional (offset)** or **direct** setpoints. In offset mode the setpoint is pushed below the cool target / above the heat target, scaled by MPC power demand, to force inverter capacity instead of fighting the unit's internal deadband.

- `ac_cool_offset_max` / `ac_heat_offset_max` — max K of offset at full power (default `2.0`).

### 7. Staged idle (setback → off)
Hard-off on an AC head kills air circulation and can lose IR/MQTT state. Idle now does a **setback first**, then escalates to full off only after `idle_off_after_minutes` of continuous setback (default `0` = immediate off; set higher to keep low-load circulation). Setback offset is configurable.

### 8. Outdoor gates
- `outdoor_cooling_min` (default `16 °C`) — never run the compressor for cooling below this averaged outdoor temperature (efficiency + condensation; open a window instead).
- `outdoor_heating_max` (default `22 °C`) — don't heat above this.

### 9. Configurable vacation action
Vacation can **turn heating off while cooling continues** — for a summer trip you protect the house from overheating without wasting energy on heat.

### 10. Panel fix for HA 2026.5+
HA 2026.5 removed `ha-textfield`; this fork registers the polyfill reliably even when `ha-entity-picker` was preloaded, so the panel's input fields always render (no more "fields missing until F5").

---

## Companion HA automation (outside this integration)

Fan-mode **night/auto** per room is handled by a small HA automation (not part of the integration): when a room's demand exceeds a threshold the head's fan switches to `auto`, otherwise back to `night` — presence-aware. It lives in a HA package and pairs nicely with the demand control above.

---

## Installation (this fork via HACS)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=turbolooser&repository=roommind&category=integration)

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/turbolooser/roommind`, category **Integration**
3. Install **RoomMind**, then restart Home Assistant
4. **Settings → Devices & Services → Add Integration → RoomMind**

> Tracking this fork means HACS updates come from here, not from upstream. To pull upstream improvements, merge them into the fork and cut a new release.

---

## Credits

- Original integration & all core engineering: **[snazzybean/roommind](https://github.com/snazzybean/roommind)** (MIT)
- Daikin head control bridge: **[Faikin](https://github.com/revk/ESP32-Faikin)** by RevK
- This fork: [turbolooser](https://github.com/turbolooser) — multisplit tuning only

If you like RoomMind, please support the original author, not this fork. Danke! 🙂
