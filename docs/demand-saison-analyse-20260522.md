# RM Saison- & Demand-Steuerung — Analyse 22.05.2026

Recherche-Notiz während User-Session. Nicht für Upstream-PR gedacht, ggf. lokal halten / gitignoren.

## Saison-Steuerung (heat ↔ cool)

RM regelt Saison komplett intern, ohne HA-seitige Saison-Helper. Pro Raum sind im Storage (`/config/.storage/roommind`, `data.rooms.<area_id>`) 4 Setpoints definiert:

| Feld | Bedeutung |
|---|---|
| `comfort_heat` | Heiz-Soll wenn linked `schedule.<raum>` on |
| `comfort_cool` | Kühl-Soll wenn linked `schedule.<raum>` on |
| `eco_heat`     | Heiz-Soll wenn `schedule.<raum>` off |
| `eco_cool`     | Kühl-Soll wenn `schedule.<raum>` off |

Heat vs. Cool: entscheidet der Controller intern (Ist vs. heat-/cool-Target). AC-Device hat `role: auto`, `setpoint_mode: proportional`.

Räume ohne AC (TRV-only, `acs: []`, z.B. Bad/Küche): cool-Setpoints irrelevant — RM kann dort nicht kühlen, egal was drinsteht.

Aktuelle Werte (alle Räume) — Stand 22.05.:
- WZ/EZ/DG: comfort 20/22, eco 19/23 (DG/EZ 20.0; WZ 20.3 — leichte Drift, vom User nicht erklärt)
- Bad/Küche: 19.5/24, 18.5/27 (cool-Werte Platzhalter)

## „Modus + Zahl" in der RM-Karte

Wert hinter dem Mode (z.B. „kühlen 85 %") ist **NICHT** das Daikin `demand_control`, sondern das per-Raum Steuersignal `heating_power` aus dem Coordinator:

```python
# coordinator.py:1181
"heating_power": round(display_pf * 100) if display_mode != MODE_IDLE else 0
```

Frontend (`roommind-panel.js`):
```js
${xt(i.mode, lang)}${i.heating_power>0 && i.heating_power<100 ? ` ${i.heating_power}%` : ''}
```

`display_pf` ist `power_fraction` aus dem Controller, ggf. durch EKF/MPC moduliert. Umsetzung Hardware-spezifisch:
- TRV: Setpoint-Offset/Ventilstellung
- AC (proportional): Setpoint, den RM dem Faikin schickt — NICHT demand_control

## Demand-Berechnung (Compressor-Gruppe)

`managers/demand_controller.py` — capacity-aware trim. **Demand und heating_power sind seit RCA 19.05. entkoppelt** (alter pf-blend pinnte demand_max bei jedem heating bang-bang ≈100). Demand schaut nur noch auf:

**1) Base aus Außentemp** (`DEMAND_FEEDFORWARD_CURVE`, const.py:115)

| Außen | Base % |
|---:|---:|
| > 12 | 30 |
| > 8  | 35 |
| > 4  | 45 |
| > 0  | 55 |
| ≤ 0  | 70 |

**2) Trim aus Σδ aller aktiven (non-idle) Raum-Member der Gruppe** (`_delta_adjustment`)

Sign-normalisiert: positiv = "braucht noch Arbeit". `cooling: cur−tgt`, `heating: tgt−cur`.

| Σδ | Trim |
|---:|---:|
| < −1.5 | −15 |
| < −0.5 | −8 |
| −0.5..+0.3 | 0 |
| > +0.3 | +8 |
| > +0.8 | +15 |
| > +1.5 | +25 |

**3)** `raw = base + trim` → clamp `[demand_min, demand_max]` → snap auf `DEMAND_GRID_STEP=5`.

## Defaults (const.py:94 ff)

| Const | Default |
|---|---:|
| `DEFAULT_DEMAND_CONTROL_ENABLED` | False (User: True) |
| `DEFAULT_DEMAND_MIN` | 30 |
| `DEFAULT_DEMAND_MAX` | 95 |
| `DEFAULT_DEMAND_HYSTERESIS` | 10 (%-Punkte; kleinere Δ → kein Write) |
| `DEFAULT_DEMAND_MIN_HOLD_MINUTES` | 10 (Anti-Short-Cycle) |
| `DEFAULT_DEMAND_DOWN_HOLD_MINUTES` | 5 (Step-Down erst nach settled-Zeit) |
| `DEMAND_DOWN_SETTLED_DELTA` | 0.3 (Σδ ≤ 0.3 zählt als "settled") |

## Asymmetrisches Slew

- Hoch: sofort schreiben
- Runter: nur wenn Σδ ≤ 0.3 für `down_hold` Minuten ununterbrochen — sonst halten

## Live-State 22.05.2026 ~11:30 (Gruppe `b1ba23a2`, DG-AC)

```
outdoor=22.25 → base=30
zones=[(dg_schlafzimmer, 0.14)]  ← Δ aus GEFILTERTER current_temp (EKF), NICHT roh BLE 22.61
total_delta=0.14 → trim=0 (unter 0.3-Schwelle)
raw=30 → clamp/snap → target=30 = device=30
held_reason=hysteresis (|0|<10) → kein Write
mean_hp=100 (heating_power = MPC bang-bang; nicht Gating)
n_active=1, flaps_1h=1, demand_min=30, demand_max=95
```

**Lesson:** Bei Diagnose nicht den BLE-Rohwert nehmen — RM rechnet auf geglättetem `current_temp` (EKF).
