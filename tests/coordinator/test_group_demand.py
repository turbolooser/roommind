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
    """Regression: pure device drift is corrected *immediately*.

    RoomMind last applied 35 (unchanged target); the Faikin drifted to 50
    on its own. Old intent-vs-intent gate froze forever. min_hold must NOT
    delay this — re-asserting an unchanged target is not a short-cycle —
    so it corrects even with a large min_hold window still open.
    """
    s = {
        "demand_control_enabled": True,
        "demand_select_entities": [SEL],
        "demand_min": 30,
        "demand_max": 95,
        "demand_hysteresis": 10,
        "demand_min_hold_minutes": 10,  # wide open, must be bypassed
    }
    c = _setup(hass, mock_config_entry, sel_current="50")  # drifted
    c._group_demand_state[GID] = (35, time.monotonic())  # last applied 35, just now
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)  # target 35
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"


@pytest.mark.asyncio
async def test_min_hold_blocks_genuine_change_then_releases(hass, mock_config_entry):
    """A *genuine* demand change too soon → held by min_hold, then released."""
    s = {
        "demand_control_enabled": True,
        "demand_select_entities": [SEL],
        "demand_min": 30,
        "demand_max": 95,
        "demand_hysteresis": 10,
        "demand_min_hold_minutes": 10,
        "demand_down_hold_minutes": 0,  # isolate min_hold from the slew gate
    }
    c = _setup(hass, mock_config_entry, sel_current="50")  # device at 50
    c._group_demand_state[GID] = (50, time.monotonic())  # last applied 50, just now
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)  # target 35 ≠ 50
    assert not _demand_calls(hass)  # genuine change, min_hold not elapsed
    # min-hold elapsed → the new demand level is released
    c._group_demand_state[GID] = (50, time.monotonic() - 11 * 60)
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"


# --- asymmetric slew (anti ping-pong) ---------------------------------------

_SLEW = {
    "demand_control_enabled": True,
    "demand_select_entities": [SEL],
    "demand_min": 30,
    "demand_max": 95,
    "demand_hysteresis": 10,
    "demand_min_hold_minutes": 0,  # isolate the slew gate
    "demand_down_hold_minutes": 5,
}


@pytest.mark.asyncio
async def test_slew_rise_is_immediate(hass, mock_config_entry):
    """A demand *rise* is never delayed by the slew (cover heat need now)."""
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_demand_state[GID] = (30, time.monotonic())  # last applied low
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), _SLEW)  # → 60
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "60"
    assert c._demand_debug[GID]["slew"] == "none"


@pytest.mark.asyncio
async def test_slew_holds_governing_value_until_sustained(hass, mock_config_entry):
    """Step-down is withheld until the zones stay satisfied long enough.

    While held, the *governing* (previous, higher) value is what gets
    re-asserted — so a drifted device is pulled back up, not down.
    """
    c = _setup(hass, mock_config_entry, sel_current="30")  # device drifted low
    c._group_demand_state[GID] = (60, time.monotonic())  # last applied 60
    # Satisfied (Σδ 0 ≤ 0.3, no heating_power → mean_hp 0) but hold not elapsed.
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), _SLEW)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "60"  # held high, not 35
    assert c._demand_debug[GID]["slew"] == "down_hold"

    # Hold window elapsed → the lower value is released.
    hass.services.async_call.reset_mock()
    hass.states.get = MagicMock(return_value=_sel_state("60"))
    c._group_demand_state[GID] = (60, time.monotonic())
    c._group_demand_downhold[GID] = time.monotonic() - (5 * 60 + 1)
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), _SLEW)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"
    assert c._demand_debug[GID]["slew"] == "down_release"


@pytest.mark.asyncio
async def test_slew_down_wait_when_zones_not_satisfied(hass, mock_config_entry):
    """Zones still need work → cap stays up regardless of the hold timer."""
    c = _setup(hass, mock_config_entry, sel_current="30")  # drifted low
    c._group_demand_state[GID] = (60, time.monotonic())
    # Σδ 0.5 > 0.3 → not settled, even though raw target (43) < 60.
    await c._async_apply_group_demand(_room_states(delta=0.5), _rooms(), _SLEW)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "60"
    assert c._demand_debug[GID]["slew"] == "down_wait"
    assert GID not in c._group_demand_downhold  # timer reset while unsettled


@pytest.mark.asyncio
async def test_slew_release_ignores_bangbang_heating_power(hass, mock_config_entry):
    """Regression (live 2026-05-19): heating_power must NOT gate the step-down.

    heating_power = MPC power_fraction × 100 is bang-bang ≈100 whenever the
    zone heats at all, so an hp gate pinned the cap high until full idle.
    Σδ-sustained is the sole release gate; hp is telemetry only.
    """
    c = _setup(hass, mock_config_entry, sel_current="60")
    c._group_demand_state[GID] = (60, time.monotonic())
    c._group_demand_downhold[GID] = time.monotonic() - (5 * 60 + 1)  # hold elapsed
    # Zone satisfied (Σδ 0) but compressor pf saturated at 100.
    rs = {"r1": {"commanded_mode": "heating", "current_temp": 20.0, "target_temp": 20.0, "heating_power": 100}}
    await c._async_apply_group_demand(rs, _rooms(), _SLEW)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"
    assert c._demand_debug[GID]["slew"] == "down_release"
    assert c._demand_debug[GID]["mean_hp"] == 100.0  # logged, not gated


@pytest.mark.asyncio
async def test_slew_disabled_allows_immediate_down(hass, mock_config_entry):
    """demand_down_hold_minutes = 0 → legacy immediate step-down."""
    s = dict(_SLEW, demand_down_hold_minutes=0)
    c = _setup(hass, mock_config_entry, sel_current="60")
    c._group_demand_state[GID] = (60, time.monotonic())
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)  # → 35
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"
    assert c._demand_debug[GID]["slew"] == "none"


@pytest.mark.asyncio
async def test_flap_counter_tracks_applied_changes(hass, mock_config_entry):
    """The rolling 1 h flap count increments only on applied value changes."""
    s = dict(_SLEW, demand_down_hold_minutes=0)
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_demand_state[GID] = (30, time.monotonic())
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), s)  # 30→60
    assert c._demand_debug[GID]["flaps_1h"] == 1
    # Re-assert the same value (device already at 60) → no change counted.
    hass.states.get = MagicMock(return_value=_sel_state("60"))
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), s)
    assert c._demand_debug[GID]["flaps_1h"] == 1
