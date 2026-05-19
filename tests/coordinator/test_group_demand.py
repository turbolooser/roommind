"""Tests for compressor-group demand control (_async_apply_group_demand)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import _create_coordinator

GID = "g1"
AC = "climate.ac1"
SEL = "select.ac1_demand"


def _group():
    return {
        "id": GID,
        "name": "G",
        "members": [AC],
        "min_run_minutes": 20,
        "min_off_minutes": 10,
        "master_entity": "",
        "conflict_resolution": "outdoor_temp",
        "action_script": "",
        "enforce_uniform_mode": True,
    }


def _rooms():
    return {"r1": {"climate_control_enabled": True, "devices": [{"entity_id": AC}]}}


def _room_states(mode="heating", delta=0.0):
    """delta = sign-normalised temp error fed to the trim band.

    Heating: target − current. current pinned at 20, target = 20 + delta.
    """
    return {
        "r1": {
            "commanded_mode": mode,
            "current_temp": 20.0,
            "target_temp": 20.0 + delta,
        }
    }


def _sel_state(val):
    s = MagicMock()
    s.state = str(val)
    return s


def _demand_calls(hass):
    return [c for c in hass.services.async_call.call_args_list if c[0][0] == "select" and c[0][1] == "select_option"]


def _setup(hass, mock_config_entry, sel_current="30"):
    c = _create_coordinator(hass, mock_config_entry)
    c._compressor_manager.load_groups([_group()])
    c.outdoor_temp_effective = 10.0
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=_sel_state(sel_current))
    return c


@pytest.mark.asyncio
async def test_disabled_by_default_no_select_calls(hass, mock_config_entry):
    c = _setup(hass, mock_config_entry)
    await c._async_apply_group_demand(_room_states(), _rooms(), {})
    assert not _demand_calls(hass)


@pytest.mark.asyncio
async def test_enabled_sets_demand_from_aggregate(hass, mock_config_entry):
    s = {"demand_control_enabled": True, "demand_select_entities": [SEL], "demand_min": 30, "demand_max": 95}
    c = _setup(hass, mock_config_entry)
    await c._async_apply_group_demand(_room_states(mode="heating", delta=2.0), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls
    assert calls[0][0][2]["option"] == "60"  # outdoor 10 → base 35; Σδ 2.0 → +25


@pytest.mark.asyncio
async def test_idle_group_sets_min(hass, mock_config_entry):
    s = {"demand_control_enabled": True, "demand_select_entities": [SEL], "demand_min": 30, "demand_max": 95}
    c = _setup(hass, mock_config_entry, sel_current="60")  # not already at min
    await c._async_apply_group_demand(_room_states(mode="idle"), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "30"


@pytest.mark.asyncio
async def test_redundant_skip_when_already_at_value(hass, mock_config_entry):
    s = {"demand_control_enabled": True, "demand_select_entities": [SEL], "demand_min": 30, "demand_max": 95}
    c = _create_coordinator(hass, mock_config_entry)
    c._compressor_manager.load_groups([_group()])
    c.outdoor_temp_effective = 10.0
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=_sel_state("60"))  # already at target
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), s)
    assert not _demand_calls(hass)


@pytest.mark.asyncio
async def test_hysteresis_holds_small_change_vs_device(hass, mock_config_entry):
    """Device already within hysteresis of target → no write (anti-thrash)."""
    s = {
        "demand_control_enabled": True,
        "demand_select_entities": [SEL],
        "demand_min": 30,
        "demand_max": 95,
        "demand_hysteresis": 10,
        "demand_min_hold_minutes": 0,
    }
    c = _setup(hass, mock_config_entry, sel_current="65")  # device at 65
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), s)  # target 60, |60-65|=5 < 10
    assert not _demand_calls(hass)


@pytest.mark.asyncio
async def test_device_drift_is_corrected(hass, mock_config_entry):
    """Regression: device drifted away from intent must be re-applied.

    RoomMind last wanted 35 (prev_val=35); the Faikin drifted to 50 on its
    own. Old intent-vs-intent gate (|35-35|<10) froze forever; the
    device-based gate sees |35-50|=15 ≥ hysteresis and corrects.
    """
    s = {
        "demand_control_enabled": True,
        "demand_select_entities": [SEL],
        "demand_min": 30,
        "demand_max": 95,
        "demand_hysteresis": 10,
        "demand_min_hold_minutes": 0,
    }
    c = _setup(hass, mock_config_entry, sel_current="50")  # drifted
    c._group_demand_state[GID] = (35, time.monotonic())  # last intent = 35
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)  # target 35
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"


@pytest.mark.asyncio
async def test_min_hold_blocks_recent_change_then_releases(hass, mock_config_entry):
    """Off-target device but changed too recently → held by min_hold."""
    s = {
        "demand_control_enabled": True,
        "demand_select_entities": [SEL],
        "demand_min": 30,
        "demand_max": 95,
        "demand_hysteresis": 10,
        "demand_min_hold_minutes": 10,
    }
    c = _setup(hass, mock_config_entry, sel_current="50")  # off target
    c._group_demand_state[GID] = (35, time.monotonic())  # just changed
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)  # target 35
    assert not _demand_calls(hass)  # |35-50|≥hyst but min_hold not elapsed
    # min-hold elapsed → correction is released
    c._group_demand_state[GID] = (35, time.monotonic() - 11 * 60)
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"
