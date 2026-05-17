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


def _room_states(mode="heating", hp=100):
    return {"r1": {"commanded_mode": mode, "heating_power": hp}}


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
    await c._async_apply_group_demand(_room_states(mode="heating", hp=100), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls
    assert calls[0][0][2]["option"] == "95"  # outdoor 10 → base 35; pf 1.0 → 95


@pytest.mark.asyncio
async def test_idle_group_sets_min(hass, mock_config_entry):
    s = {"demand_control_enabled": True, "demand_select_entities": [SEL], "demand_min": 30, "demand_max": 95}
    c = _setup(hass, mock_config_entry, sel_current="60")  # not already at min
    await c._async_apply_group_demand(_room_states(mode="idle", hp=0), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "30"


@pytest.mark.asyncio
async def test_redundant_skip_when_already_at_value(hass, mock_config_entry):
    s = {"demand_control_enabled": True, "demand_select_entities": [SEL], "demand_min": 30, "demand_max": 95}
    c = _create_coordinator(hass, mock_config_entry)
    c._compressor_manager.load_groups([_group()])
    c.outdoor_temp_effective = 10.0
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=_sel_state("95"))  # already at target
    await c._async_apply_group_demand(_room_states(hp=100), _rooms(), s)
    assert not _demand_calls(hass)


@pytest.mark.asyncio
async def test_hysteresis_holds_small_change(hass, mock_config_entry):
    s = {
        "demand_control_enabled": True,
        "demand_select_entities": [SEL],
        "demand_min": 30,
        "demand_max": 95,
        "demand_hysteresis": 10,
        "demand_min_hold_minutes": 0,
    }
    c = _setup(hass, mock_config_entry, sel_current="60")
    c._group_demand_state[GID] = (95, time.monotonic())  # already applied 95
    await c._async_apply_group_demand(_room_states(hp=100), _rooms(), s)  # target 95, Δ0 < 10 → hold
    assert not _demand_calls(hass)
