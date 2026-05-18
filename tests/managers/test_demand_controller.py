"""Tests for the pure compressor-group demand computation."""

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
def test_feedforward_curve_when_idle(t_out, expected_base):
    """Group idle → demand_min, but base curve still drives the floor logic."""
    # idle (no active pfs) always returns demand_min
    assert compute_demand_percent(t_out, [], 30, 95) == 30


@pytest.mark.parametrize(
    ("pfs", "expected"),
    [
        ([0.0], 35),  # base only (t=10 → 35)
        ([1.0, 1.0], 95),  # 35 + (95-35)*1.0
        ([0.5], 65),  # 35 + 60*0.5
        ([0.4, 0.6], 70),  # Phase 0.5: max 0.6 → 35 + 60*0.6 = 71 → snap 70
        ([0.3], 55),  # 35 + 60*0.3 = 53 → snap 55
    ],
)
def test_feedback_blend_and_grid_snap(pfs, expected):
    assert compute_demand_percent(10.0, pfs, 30, 95) == expected


def test_base_clamped_into_range():
    """Cold base (70) clamped down to demand_max."""
    assert compute_demand_percent(-5.0, [], 30, 50) == 30  # idle → min
    assert compute_demand_percent(-5.0, [0.0], 30, 50) == 50  # base 70 → clamp 50


def test_idle_returns_min_snapped():
    assert compute_demand_percent(10.0, [], 32, 95) == 32  # re-clamped up to lo


def test_inverted_range_guard():
    assert compute_demand_percent(10.0, [], 30, 20) == 30  # demand_max<min → min
    # demand_max < demand_min with an active member: range collapses to min
    res = compute_demand(10.0, [0.8], 30, 20)
    assert res.percent == 30
    assert res.base == 30


def test_full_demand_hits_max():
    assert compute_demand_percent(15.0, [1.0], 30, 95) == 95


def test_feedforward_falls_back_to_last_curve_entry():
    """outdoor_temp below every threshold → last curve base is used."""
    curve = ((10.0, 30), (5.0, 50))
    res = compute_demand(-20.0, [], 30, 95, curve=curve)
    assert res.base == 50  # no threshold exceeded → curve[-1][1]


def test_most_demanding_zone_dictates():
    """A single hot zone must not be diluted by idle-ish co-members."""
    # mean would be 0.3 → 35 + 60*0.3 = 53 → snap 55
    # max is 0.9 → 35 + 60*0.9 = 89 → snap 90
    assert compute_demand_percent(10.0, [0.9, 0.0, 0.0], 30, 95) == 90


def test_compute_demand_diagnostics_active():
    """Rich result exposes the controller's intent for the flight recorder."""
    res = compute_demand(10.0, [0.4, 0.6], 30, 95)
    assert isinstance(res, DemandResult)
    assert res.base == 35
    assert res.n_active == 2
    assert res.fb_max == pytest.approx(0.6)
    assert res.fb_mean == pytest.approx(0.5)
    assert res.fb == res.fb_max  # max aggregation
    assert res.raw == pytest.approx(35 + 60 * 0.6)
    assert res.percent == 70


def test_compute_demand_diagnostics_idle():
    res = compute_demand(10.0, [], 30, 95)
    assert res.n_active == 0
    assert res.fb == 0.0
    assert res.fb_mean == 0.0
    assert res.fb_max == 0.0
    assert res.percent == 30


def test_pf_values_clamped_into_unit_range():
    """Out-of-range power fractions are clamped before aggregation."""
    res = compute_demand(10.0, [1.5, -0.2], 30, 95)
    assert res.fb_max == 1.0
    assert res.fb_mean == pytest.approx(0.5)  # (1.0 + 0.0) / 2
    assert res.percent == 95
