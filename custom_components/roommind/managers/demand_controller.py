"""Compressor-group demand controller (pure compute).

The demand select is only a **power cap** on the compressor group — the MPC
owns comfort via the AC setpoint. So the cap just has to open on demand and
close at rest. Two models, picked by ``mode``:

* **Cooling** — one lever: ``cap = FLOOR + SLOPE·Σδ``, where Σδ is the summed
  room overshoot (cur − target) of the active cooling zones. The demand shows
  up directly as overshoot, so no weather feedforward and no PV boost are
  needed — a single, explainable line from a resting floor to the ceiling.

* **Heating** — the legacy field-tuned model (kept verbatim): an
  outdoor-temperature feedforward ``base`` (colder → higher) plus a small
  symmetric ``trim`` on the summed sign-normalised error, plus an optional
  ``pv_boost``. Reproduces the field-proven ``klima_neu_demand_gesamt``.

Both clamp to ``[demand_min, demand_max]`` and snap to the device demand-select
grid. Pure / HA-free → unit-testable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..const import (
    DEMAND_COOL_FLOOR,
    DEMAND_COOL_SLOPE,
    DEMAND_FEEDFORWARD_CURVE,
    DEMAND_GRID_STEP,
    MODE_COOLING,
)


@dataclass(frozen=True)
class DemandResult:
    """Outcome of one demand computation plus diagnostics for logging.

    ``percent`` is the value written to the device. The remaining fields are
    the intermediate signals (the controller's *intent*) so a recorded
    diagnostic sensor can later explain *why* this value was chosen.
    """

    percent: int
    base: int  # weather feedforward demand %
    adjustment: int  # symmetric trim applied to base (±band)
    pv_boost: int  # extra demand %-points from PV surplus (0 when inactive)
    total_delta: float  # Σ of active members' sign-normalised temp error
    n_active: int  # number of active (non-idle) members
    raw: float  # base + adjustment + pv_boost, pre-clamp / pre-snap


def _feedforward_base(outdoor_temp: float, curve: Sequence[tuple[float, int]]) -> int:
    """Weather feedforward: pick the base % of the first threshold the outdoor
    temp exceeds (curve evaluated highest-first). Direction lives in the curve:
    the heat curve rises as it gets colder, the cool curve as it gets hotter."""
    for threshold, base in curve:
        if outdoor_temp > threshold:
            return base
    return curve[-1][1]


def _delta_adjustment(total_delta: float) -> int:
    """Symmetric trim band, ported 1:1 from ``klima_neu_demand_gesamt``.

    ``total_delta`` is the summed sign-normalised error of the active zones:
    positive → still need work (boost), negative → already overshot (reduce).
    """
    if total_delta < -1.5:
        return -15
    if total_delta < -0.5:
        return -8
    if total_delta > 1.5:
        return 25
    if total_delta > 0.8:
        return 15
    if total_delta > 0.3:
        return 8
    return 0


def _snap(value: float, grid: int, lo: int, hi: int) -> int:
    """Clamp to [lo, hi] then snap to the device grid, re-clamped."""
    clamped = max(float(lo), min(float(hi), value))
    snapped = round(clamped / grid) * grid
    return int(max(lo, min(hi, snapped)))


def compute_demand(
    outdoor_temp: float | None,
    active_deltas: Sequence[float],
    demand_min: int,
    demand_max: int,
    *,
    pv_boost: int = 0,
    mode: str | None = None,
    curve: Sequence[tuple[float, int]] = DEMAND_FEEDFORWARD_CURVE,
    grid: int = DEMAND_GRID_STEP,
) -> DemandResult:
    """Return the group demand cap (%) plus diagnostics for one group.

    ``active_deltas`` are the sign-normalised temperature errors (positive =
    zone still needs work) of members whose room is currently *not* idle.
    Empty → group idle → ``demand_min``.

    ``mode`` picks the model:

    * **Cooling** — one lever: ``cap = FLOOR + SLOPE·Σδ`` (see const.py). The
      demand select is only a power cap; the MPC owns comfort via the setpoint,
      so the cap just tracks room overshoot. No weather feedforward, no
      ``pv_boost`` (it is ignored while cooling).
    * **Heating / unknown** — legacy field-tuned model: weather feedforward
      ``base`` + symmetric ``adjustment`` trim + ``pv_boost``. Unchanged.

    The result is clamped only once, at the end, to ``[demand_min, demand_max]``
    (a cold-weather heating base above the ceiling still trims correctly first).
    """
    if demand_max < demand_min:
        demand_max = demand_min

    cooling = mode == MODE_COOLING
    # Diagnostics base: cooling rests on the flat floor; heating uses the
    # weather feedforward (unknown outdoor temp → mild, legacy float(10)).
    t_out = 10.0 if outdoor_temp is None else outdoor_temp
    base = DEMAND_COOL_FLOOR if cooling else _feedforward_base(t_out, curve)

    if not active_deltas:
        return DemandResult(
            percent=_snap(float(demand_min), grid, demand_min, demand_max),
            base=base,
            adjustment=0,
            pv_boost=0,
            total_delta=0.0,
            n_active=0,
            raw=float(demand_min),
        )

    total_delta = sum(active_deltas)
    if cooling:
        # cap = FLOOR + SLOPE·Σδ — the whole cooling model.
        adjustment = int(round(DEMAND_COOL_SLOPE * total_delta))
        applied_boost = 0
    else:
        adjustment = _delta_adjustment(total_delta)
        applied_boost = pv_boost
    raw = float(base + adjustment + applied_boost)
    return DemandResult(
        percent=_snap(raw, grid, demand_min, demand_max),
        base=base,
        adjustment=adjustment,
        pv_boost=applied_boost,
        total_delta=total_delta,
        n_active=len(active_deltas),
        raw=raw,
    )


def compute_demand_percent(
    outdoor_temp: float | None,
    active_deltas: Sequence[float],
    demand_min: int,
    demand_max: int,
    *,
    pv_boost: int = 0,
    mode: str | None = None,
    curve: Sequence[tuple[float, int]] = DEMAND_FEEDFORWARD_CURVE,
    grid: int = DEMAND_GRID_STEP,
) -> int:
    """Backward-compatible thin wrapper returning only the demand %."""
    return compute_demand(
        outdoor_temp,
        active_deltas,
        demand_min,
        demand_max,
        pv_boost=pv_boost,
        mode=mode,
        curve=curve,
        grid=grid,
    ).percent
