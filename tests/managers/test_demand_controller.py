"""Tests for the pure compressor-group demand computation (Phase 1).

Model: demand = clamp_snap(feedforward_base + symmetric_trim(Σ active
sign-normalised temp errors)). Steady state (Σδ≈0) → base; the trim is a
narrow ±band, so a saturated zone no longer pins to demand_max.
"""

from __future__ import annotations

import pytest

from custom_components.roommind.managers.demand_controller import (
    DemandResult,
    compute_demand,
    compute_demand_percent,
)


@pytest.mark.parametrize(
    ("t_out", "expected_base"),
    [
        (None, 35),  # unknown → mild 10°C → >8 → 35
        (15.0, 30),  # >12
        (10.0, 35),  # >8
        (5.0, 45),  # >4
        (1.0, 55),  # >0
        (-5.0, 70),  # else
    ],
)
def test_feedforward_base_curve(t_out, expected_base):
    """Base is the weather feedforward; idle group still returns demand_min."""
    res = compute_demand(t_out, [], 30, 95)
    assert res.base == expected_base
    assert res.percent == 30  # idle (no active deltas) → demand_min


@pytest.mark.parametrize(
    ("total_delta", "expected_adj"),
    [
        (-2.0, -15),
        (-1.0, -8),
        (-0.5, 0),  # boundary: not < -0.5 (strict) → neutral band
        (0.0, 0),
        (0.3, 0),  # boundary: not > 0.3 (strict)
        (0.5, 8),
        (1.0, 15),
        (2.0, 25),
    ],
)
def test_symmetric_trim_band(total_delta, expected_adj):
    """Trim band ported 1:1 from klima_neu_demand_gesamt."""
    res = compute_demand(10.0, [total_delta], 30, 95)  # base 35
    assert res.adjustment == expected_adj
    assert res.total_delta == pytest.approx(total_delta)


@pytest.mark.parametrize(
    ("deltas", "expected"),
    [
        ([0.0], 35),  # base only, no trim
        ([0.5], 45),  # 35 + 8 = 43 → snap 45
        ([1.0], 50),  # 35 + 15 = 50
        ([2.0], 60),  # 35 + 25 = 60  (= field-observed mild-weather peak)
        ([-1.0], 30),  # 35 - 8 = 27 → clamp up to demand_min
        ([0.2, 0.2, 0.2], 45),  # Σ=0.6 > 0.3 → +8 → 43 → snap 45
        ([1.0, 1.0], 60),  # Σ=2.0 > 1.5 → +25 → 60 (no longer pins to max)
    ],
)
def test_demand_blend_and_grid_snap(deltas, expected):
    assert compute_demand_percent(10.0, deltas, 30, 95) == expected


def test_saturated_zone_does_not_pin_to_max():
    """Regression: one zone far below target must stay near base, not max."""
    # Single zone 1.2 K below target: Σδ=1.2 → +15 → 35+15 = 50, not 95.
    assert compute_demand_percent(10.0, [1.2], 30, 95) == 50


def test_final_clamp_only_no_early_base_clamp():
    """Cold base (70) above demand_max clamps only after the trim is added."""
    assert compute_demand_percent(-5.0, [], 30, 50) == 30  # idle → min
    res = compute_demand(-5.0, [0.0], 30, 50)  # base 70, trim 0
    assert res.base == 70  # base not pre-clamped
    assert res.percent == 50  # final clamp to demand_max


def test_cold_base_with_negative_trim():
    """Base 70, rooms slightly overshot → modest reduction, still snapped."""
    res = compute_demand(-5.0, [-0.6, -0.6], 30, 95)  # Σ=-1.2 → -8
    assert res.base == 70
    assert res.adjustment == -8
    assert res.percent == 60  # 70 - 8 = 62 → snap 60


def test_idle_returns_min_snapped():
    assert compute_demand_percent(10.0, [], 32, 95) == 32  # re-clamped up to lo


def test_inverted_range_guard():
    assert compute_demand_percent(10.0, [], 30, 20) == 30  # demand_max<min → min
    res = compute_demand(10.0, [0.8], 30, 20)  # range collapses to [30,30]
    assert res.percent == 30
    assert res.base == 35  # base itself is unaffected by the guard


def test_feedforward_falls_back_to_last_curve_entry():
    """outdoor_temp below every threshold → last curve base is used."""
    curve = ((10.0, 30), (5.0, 50))
    res = compute_demand(-20.0, [], 30, 95, curve=curve)
    assert res.base == 50  # no threshold exceeded → curve[-1][1]


def test_compute_demand_diagnostics_active():
    """Rich result exposes the controller's intent for the flight recorder."""
    res = compute_demand(10.0, [0.4, 0.6], 30, 95)  # Σ=1.0 > 0.8 → +15
    assert isinstance(res, DemandResult)
    assert res.base == 35
    assert res.n_active == 2
    assert res.total_delta == pytest.approx(1.0)
    assert res.adjustment == 15
    assert res.raw == pytest.approx(50.0)
    assert res.percent == 50


def test_compute_demand_diagnostics_idle():
    res = compute_demand(10.0, [], 30, 95)
    assert res.n_active == 0
    assert res.adjustment == 0
    assert res.total_delta == 0.0
    assert res.raw == pytest.approx(30.0)
    assert res.percent == 30


def test_cooling_sign_is_caller_supplied():
    """compute_demand is sign-agnostic: the coordinator sign-normalises.

    A cooling room 1 K too warm is passed as +1.0 (needs work) → boost,
    exactly like a heating room 1 K too cold.
    """
    assert compute_demand_percent(10.0, [1.0], 30, 95) == 50
