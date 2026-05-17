"""Tests for staged idle: setback → (after idle_off_after_minutes) → off."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control import mpc_controller as mc
from custom_components.roommind.control.mpc_controller import MPCController, async_idle_device
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import build_hass, make_room

ENTITY = "climate.ac"
DEVICES = [{"entity_id": ENTITY, "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": "low"}]


def _heat_state():
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 30.0, "temperature": None}
    return state


def _fake_clock(monkeypatch):
    holder = {"t": 1000.0}
    monkeypatch.setattr(mc.time, "monotonic", lambda: holder["t"])
    return holder


def _setpoint_calls(hass):
    return [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]


def _off_calls(hass):
    return [
        c
        for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"
    ]


@pytest.mark.asyncio
async def test_default_zero_never_escalates(monkeypatch):
    """idle_off_after_minutes=0 (default) → always setback, never off."""
    clock = _fake_clock(monkeypatch)
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_heat_state())
    # default after clear_command_cache fixture is 0.0
    for _ in range(3):
        clock["t"] += 100000  # huge time jumps must not escalate
        await async_idle_device(hass, ENTITY, DEVICES, area_id="t", targets=TargetTemps(heat=21.0, cool=None))
    assert _setpoint_calls(hass)
    assert not _off_calls(hass)


@pytest.mark.asyncio
async def test_setback_then_off_after_timeout(monkeypatch):
    """Setback first; after the timeout elapses, escalate to off."""
    clock = _fake_clock(monkeypatch)
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_heat_state())
    mc._idle_cfg["off_after_minutes"] = 10  # 10 min

    # First idle cycle → setback, timer starts
    await async_idle_device(hass, ENTITY, DEVICES, area_id="t", targets=TargetTemps(heat=21.0, cool=None))
    assert _setpoint_calls(hass)
    assert not _off_calls(hass)
    assert ENTITY in mc._idle_setback_since

    # Just before threshold → still setback
    clock["t"] += 10 * 60 - 1
    await async_idle_device(hass, ENTITY, DEVICES, area_id="t", targets=TargetTemps(heat=21.0, cool=None))
    assert not _off_calls(hass)

    # At/after threshold → off
    clock["t"] += 2
    await async_idle_device(hass, ENTITY, DEVICES, area_id="t", targets=TargetTemps(heat=21.0, cool=None))
    assert _off_calls(hass)


@pytest.mark.asyncio
async def test_timer_resets_when_device_reactivated(monkeypatch):
    """_call() with an active hvac_mode clears the setback timer."""
    _fake_clock(monkeypatch)
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_heat_state())
    ctrl = MPCController(
        hass,
        make_room(thermostats=[], acs=[ENTITY]),
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mc._idle_setback_since[ENTITY] = 999.0

    await ctrl._call("set_hvac_mode", {"entity_id": ENTITY, "hvac_mode": "heat"})

    assert ENTITY not in mc._idle_setback_since


@pytest.mark.asyncio
async def test_clear_command_cache_resets_state():
    """clear_command_cache() resets the staged-idle module state."""
    mc._idle_setback_since["x"] = 1.0
    mc._idle_cfg["off_after_minutes"] = 30
    mc.clear_command_cache()
    assert mc._idle_setback_since == {}
    assert mc._idle_cfg["off_after_minutes"] == 0.0
