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


@pytest.mark.parametrize(
    ("t_out", "expected_floor"),
    [
        (34.0, 90),  # >33 → heatwave hold-load near max
        (32.0, 80),  # >31
        (30.0, 70),  # >29 (field-measured cooled DG at cap 90)
        (28.0, 62),  # >27
        (26.0, 54),  # >25
        (24.0, 46),  # >23
        (20.0, 40),  # mild → resting floor
        (None, 40),  # unknown → mild 10° → floor
    ],
)
def test_cool_floor_curve(t_out, expected_floor):
    """Cooling FLOOR rises with outdoor temp (hold-load feedforward)."""
    res = compute_demand(t_out, [], 30, 95, mode="cooling")
    assert res.base == expected_floor


def test_cool_floor_pins_to_max_in_heatwave():
    """At heatwave outdoor temps the lifted floor + any real Σδ pins the cap
    stably to demand_max — no more hovering at 90 and flapping the hysteresis.
    """
    # 34 °C: floor 90, even a small Σδ=0.3 → 90+8=98 → clamp/snap 95.
    assert compute_demand_percent(34.0, [0.3], 30, 95, mode="cooling") == 95
    # 33.6 °C (the field snapshot), DG ~0.6 over: floor 90 + 15 = 105 → 95.
    assert compute_demand_percent(33.6, [0.6], 30, 95, mode="cooling") == 95
    # The same heatwave floor can reach 100 when the ceiling is lifted by PV.
    assert compute_demand_percent(34.0, [0.3], 30, 100, mode="cooling") == 100


@pytest.mark.parametrize(
    ("total_delta", "expected"),
    [
        (-0.4, 35),  # 46 - 10 = 36 → snap 35
        (0.0, 45),  # floor 46 → snap 45
        (0.5, 60),  # 46 + 12.5 = 58.5 → snap 60
        (1.0, 70),  # 46 + 25 = 71 → snap 70
        (2.0, 95),  # 46 + 50 = 96 → clamp demand_max
    ],
)
def test_cool_floor_plus_slope(total_delta, expected):
    """cap = clamp(FLOOR(outdoor) + SLOPE·Σδ). At 24 °C the floor is 46."""
    res = compute_demand(24.0, [total_delta], 30, 95, mode="cooling")
    assert res.base == 46
    assert res.percent == expected


def test_cool_floor_breaks_teufelskreis_on_hot_day():
    """The feedforward floor keeps the cap high on a hot day even as a room
    nears target (Σδ small) — the top-floor-at-30° fix.
    """
    # 30 °C, DG ~0.6° over: floor 70 + 15 = 85 (vs 40+15=55, which wouldn't hold).
    assert compute_demand_percent(30.0, [0.6], 30, 95, mode="cooling") == 85
    # Same overshoot but mild (20 °C): floor 40 + 15 = 55 → stays efficient.
    assert compute_demand_percent(20.0, [0.6], 30, 95, mode="cooling") == 55


def test_cool_ignores_pv_boost():
    """PV boost is heating-only now → ignored (and zeroed) while cooling."""
    res = compute_demand(24.0, [1.0], 30, 95, mode="cooling", pv_boost=40)
    assert res.pv_boost == 0
    assert res.percent == 70  # floor 46 + 25, boost makes no difference


def test_cool_lifts_cap_where_broken_heat_curve_pinned_to_floor():
    """Regression for 'RM won't cool properly': the heat curve floored the
    cooling base at 30 → cap stuck at 45; the cool feedforward lifts it.
    """
    deltas = [1.05, 0.05, 0.38]  # field snapshot: Σδ ≈ 1.48
    assert compute_demand_percent(24.0, deltas, 30, 95) == 45  # heat curve (bug)
    # cool: floor(24°)=46 + 37 = 83 → snap 85.
    assert compute_demand_percent(24.0, deltas, 30, 95, mode="cooling") == 85


def test_heating_and_default_mode_keep_heat_curve():
    """mode None or heating → unchanged heat-curve base (byte-identical)."""
    assert compute_demand(24.0, [0.0], 30, 95).base == 30  # default
    assert compute_demand(24.0, [0.0], 30, 95, mode="heating").base == 30


def test_pv_boost_added_on_top_of_base_and_trim():
    """pv_boost stacks with base + trim, then clamps to demand_max."""
    # Mild weather (base 35), zone at target (no trim), boost +15 → 50.
    res = compute_demand(10.0, [0.0], 30, 95, pv_boost=15)
    assert res.base == 35
    assert res.adjustment == 0
    assert res.pv_boost == 15
    assert res.raw == pytest.approx(50.0)
    assert res.percent == 50


def test_pv_boost_clamps_to_demand_max():
    """Boost cannot exceed the safety ceiling — final clamp still rules."""
    # base 35 + adj 25 + boost 30 = 90, but demand_max=70 caps it.
    res = compute_demand(10.0, [2.0], 30, 70, pv_boost=30)
    assert res.raw == pytest.approx(90.0)
    assert res.percent == 70  # clamped, then snapped


def test_pv_boost_ignored_when_group_idle():
    """No active zones → boost has nowhere to go; result is demand_min."""
    res = compute_demand(10.0, [], 30, 95, pv_boost=20)
    assert res.percent == 30
    assert res.pv_boost == 0  # diagnostics reflect that boost did not apply


def test_pv_boost_defaults_to_zero():
    """compute_demand without pv_boost kwarg stays byte-identical to legacy."""
    res = compute_demand(10.0, [0.5], 30, 95)
    assert res.pv_boost == 0
    assert res.percent == 45  # 35 + 8 → snap 45
