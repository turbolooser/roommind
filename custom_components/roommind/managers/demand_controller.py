"""Compressor-group demand controller (pure compute).

Phase 1 — capacity-aware trim model. An outdoor-temperature feedforward sets
a weather-appropriate *base* demand %. A small **symmetric trim** derived
from the summed temperature error (Σ of ``target − actual`` over the active
member zones, sign-normalised so "needs more work" is always positive) nudges
the base up (rooms too far from target) or down (rooms already past target).

This reproduces the field-proven external controller
(``sensor.klima_neu_demand_gesamt``): the base dominates and the trim is a
narrow ±band, so steady state ≈ base (≈30–35 % in mild weather) and the
result no longer pins to ``demand_max`` whenever a saturated MPC
``power_fraction`` (≈1.0 during any heating) is present — the defect the
previous pf-blend produced. ``demand_max`` is now a pure safety ceiling.

Result is clamped to ``[demand_min, demand_max]`` and snapped to the device
demand-select grid. Pure / HA-free → unit-testable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..const import DEMAND_FEEDFORWARD_CURVE, DEMAND_GRID_STEP


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
    """Weather feedforward: colder outside → higher base demand %."""
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
    curve: Sequence[tuple[float, int]] = DEMAND_FEEDFORWARD_CURVE,
    grid: int = DEMAND_GRID_STEP,
) -> DemandResult:
    """Return the group demand cap (%) plus diagnostics for one group.

    ``active_deltas`` are the sign-normalised temperature errors (positive =
    zone still needs work) of members whose room is currently *not* idle.
    Empty → group idle → ``demand_min`` (and ``pv_boost`` is ignored — no
    point lifting the cap when there is no work to do).

    ``pv_boost`` is an integer number of demand %-points added on top of
    ``base + adjustment``. The caller is responsible for the gating logic
    (sustained surplus, battery SoC, mode-appropriate amount) — by the time
    it reaches here the boost has already earned its right to apply.

    The feedforward base is intentionally **not** pre-clamped to
    ``demand_max``: only the final ``base + adjustment + pv_boost`` sum is
    clamped, so a cold-weather base above the safety ceiling still trims
    correctly (matches the legacy controller's single final clamp).
    """
    if demand_max < demand_min:
        demand_max = demand_min

    # Unknown outdoor temp → assume mild (mirrors legacy float(10) default).
    t_out = 10.0 if outdoor_temp is None else outdoor_temp
    base = _feedforward_base(t_out, curve)

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
    adjustment = _delta_adjustment(total_delta)
    raw = float(base + adjustment + pv_boost)
    return DemandResult(
        percent=_snap(raw, grid, demand_min, demand_max),
        base=base,
        adjustment=adjustment,
        pv_boost=pv_boost,
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
        curve=curve,
        grid=grid,
    ).percent
