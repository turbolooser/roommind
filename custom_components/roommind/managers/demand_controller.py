"""Compressor-group demand controller (pure compute).

Hybrid: an outdoor-temperature feedforward sets a weather-appropriate base
demand %, the aggregate of active member ``power_fraction`` pushes it toward
the configured maximum. Result is clamped to [demand_min, demand_max] and
snapped to the device's demand-select grid. Pure / HA-free → unit-testable.

Aggregation note (Phase 0.5): a multi-split outdoor compressor modulates to
satisfy its *most demanding* indoor zone, not the average of all zones. The
aggregate therefore uses the **maximum** active power_fraction. ``fb_mean`` is
still computed and surfaced for diagnostics / offline analysis.
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
    base: int
    fb: float  # aggregated power_fraction actually used (Phase 0.5: = fb_max)
    fb_mean: float  # mean of active power_fractions (diagnostic only)
    fb_max: float  # max of active power_fractions
    n_active: int  # number of active (non-idle) members
    raw: float  # pre-snap, pre-clamp blended value


def _feedforward_base(outdoor_temp: float, curve: Sequence[tuple[float, int]]) -> int:
    """Weather feedforward: colder outside → higher base demand %."""
    for threshold, base in curve:
        if outdoor_temp > threshold:
            return base
    return curve[-1][1]


def _snap(value: float, grid: int, lo: int, hi: int) -> int:
    """Clamp to [lo, hi] then snap to the device grid, re-clamped."""
    clamped = max(float(lo), min(float(hi), value))
    snapped = round(clamped / grid) * grid
    return int(max(lo, min(hi, snapped)))


def compute_demand(
    outdoor_temp: float | None,
    active_power_fractions: Sequence[float],
    demand_min: int,
    demand_max: int,
    *,
    curve: Sequence[tuple[float, int]] = DEMAND_FEEDFORWARD_CURVE,
    grid: int = DEMAND_GRID_STEP,
) -> DemandResult:
    """Return the group demand cap (%) plus diagnostics for one group.

    ``active_power_fractions`` are the power_fractions (0..1) of members whose
    room is currently *not* idle. Empty → group idle → demand_min.
    """
    if demand_max < demand_min:
        demand_max = demand_min

    # Unknown outdoor temp → assume mild (mirrors legacy float(10) default).
    t_out = 10.0 if outdoor_temp is None else outdoor_temp
    base = _feedforward_base(t_out, curve)
    base = max(demand_min, min(demand_max, base))

    if not active_power_fractions:
        return DemandResult(
            percent=_snap(float(demand_min), grid, demand_min, demand_max),
            base=base,
            fb=0.0,
            fb_mean=0.0,
            fb_max=0.0,
            n_active=0,
            raw=float(demand_min),
        )

    clamped_pfs = [max(0.0, min(1.0, p)) for p in active_power_fractions]
    fb_mean = sum(clamped_pfs) / len(clamped_pfs)
    fb_max = max(clamped_pfs)
    # Multi-split: the most-demanding zone dictates compressor speed.
    fb = fb_max

    raw = base + (demand_max - base) * fb
    return DemandResult(
        percent=_snap(raw, grid, demand_min, demand_max),
        base=base,
        fb=fb,
        fb_mean=fb_mean,
        fb_max=fb_max,
        n_active=len(clamped_pfs),
        raw=raw,
    )


def compute_demand_percent(
    outdoor_temp: float | None,
    active_power_fractions: Sequence[float],
    demand_min: int,
    demand_max: int,
    *,
    curve: Sequence[tuple[float, int]] = DEMAND_FEEDFORWARD_CURVE,
    grid: int = DEMAND_GRID_STEP,
) -> int:
    """Backward-compatible thin wrapper returning only the demand %."""
    return compute_demand(
        outdoor_temp,
        active_power_fractions,
        demand_min,
        demand_max,
        curve=curve,
        grid=grid,
    ).percent
