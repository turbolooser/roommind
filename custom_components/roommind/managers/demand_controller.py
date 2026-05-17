"""Compressor-group demand controller (pure compute).

Hybrid: an outdoor-temperature feedforward sets a weather-appropriate base
demand %, the aggregate of active member ``power_fraction`` pushes it toward
the configured maximum. Result is clamped to [demand_min, demand_max] and
snapped to the device's demand-select grid. Pure / HA-free → unit-testable.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..const import DEMAND_FEEDFORWARD_CURVE, DEMAND_GRID_STEP


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


def compute_demand_percent(
    outdoor_temp: float | None,
    active_power_fractions: Sequence[float],
    demand_min: int,
    demand_max: int,
    *,
    curve: Sequence[tuple[float, int]] = DEMAND_FEEDFORWARD_CURVE,
    grid: int = DEMAND_GRID_STEP,
) -> int:
    """Return the group demand cap (%) for one compressor group.

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
        return _snap(float(demand_min), grid, demand_min, demand_max)

    fb = sum(active_power_fractions) / len(active_power_fractions)
    fb = max(0.0, min(1.0, fb))

    raw = base + (demand_max - base) * fb
    return _snap(raw, grid, demand_min, demand_max)
