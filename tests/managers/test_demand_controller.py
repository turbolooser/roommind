"""Tests for the pure compressor-group demand computation."""

from __future__ import annotations

import pytest

from custom_components.roommind.managers.demand_controller import compute_demand_percent


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
        ([0.4, 0.6], 65),  # mean 0.5
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


def test_full_demand_hits_max():
    assert compute_demand_percent(15.0, [1.0], 30, 95) == 95
