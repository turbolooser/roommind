"""Tests for the AC inverter setpoint strategy (boost vs offset).

Covers cooling and AC-heating offset behaviour, clamps, the byte-identical
default ("boost"), and that TRV/underfloor heating is unaffected.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import _make_ac_state_for_plan, build_hass, make_room


def _set_temps(hass):
    return [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]


def _ctrl(hass, room, outdoor):
    return MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=outdoor,
        settings={},
        has_external_sensor=True,
    )


@pytest.mark.asyncio
async def test_cooling_offset_full_demand():
    """offset @ pf=1.0 → cool target minus full offset."""
    hass = build_hass()
    ctrl = _ctrl(hass, make_room(thermostats=[], acs=["climate.ac"]), 30.0)
    await ctrl.async_apply(
        "cooling",
        24.0,
        power_fraction=1.0,
        current_temp=27.0,
        ac_setpoint_strategy="offset",
        ac_cool_offset_max=2.0,
    )
    calls = _set_temps(hass)
    assert calls
    assert calls[0][0][2]["temperature"] == 22.0  # 24 - 1.0*2


@pytest.mark.asyncio
async def test_cooling_offset_zero_demand():
    """offset @ pf=0.0 → exactly the cool target (gentle)."""
    hass = build_hass()
    ctrl = _ctrl(hass, make_room(thermostats=[], acs=["climate.ac"]), 30.0)
    await ctrl.async_apply(
        "cooling",
        24.0,
        power_fraction=0.0,
        current_temp=27.0,
        ac_setpoint_strategy="offset",
        ac_cool_offset_max=2.0,
    )
    assert _set_temps(hass)[0][0][2]["temperature"] == 24.0


@pytest.mark.asyncio
async def test_cooling_offset_clamped_to_boost_floor():
    """A huge offset is clamped up to ac_cool_boost (device/fallback min)."""
    hass = build_hass()
    ctrl = _ctrl(hass, make_room(thermostats=[], acs=["climate.ac"]), 30.0)
    await ctrl.async_apply(
        "cooling",
        24.0,
        power_fraction=1.0,
        current_temp=27.0,
        ac_setpoint_strategy="offset",
        ac_cool_offset_max=20.0,
    )
    # 24 - 20 = 4 → clamped up to AC_COOLING_BOOST_TARGET (16)
    assert _set_temps(hass)[0][0][2]["temperature"] == 16.0


@pytest.mark.asyncio
async def test_cooling_default_boost_unchanged():
    """No strategy kwarg → default 'boost' keeps the legacy ramp."""
    hass = build_hass()
    ctrl = _ctrl(hass, make_room(thermostats=[], acs=["climate.ac"]), 30.0)
    await ctrl.async_apply("cooling", 24.0, power_fraction=1.0, current_temp=27.0)
    # legacy: 27 - 1.0*(27-16) = 16
    assert _set_temps(hass)[0][0][2]["temperature"] == 16.0


@pytest.mark.asyncio
async def test_ac_heating_offset_full_demand():
    """offset @ pf=1.0 on an AC in heat mode → heat target plus full offset."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_make_ac_state_for_plan(["off", "heat", "cool"], "heat"))
    ctrl = _ctrl(hass, make_room(thermostats=[], acs=["climate.ac"]), 2.0)
    await ctrl.async_apply(
        "heating",
        21.0,
        power_fraction=1.0,
        current_temp=18.0,
        ac_setpoint_strategy="offset",
        ac_heat_offset_max=2.0,
    )
    calls = _set_temps(hass)
    assert calls
    assert calls[0][0][2]["temperature"] == 23.0  # 21 + 1.0*2


@pytest.mark.asyncio
async def test_trv_heating_unaffected_by_offset_strategy():
    """TRV/underfloor must keep the boost ramp even with offset strategy."""
    hass = build_hass()
    ctrl = _ctrl(hass, make_room(thermostats=["climate.living_trv"], acs=[]), 2.0)
    await ctrl.async_apply(
        "heating",
        21.0,
        power_fraction=1.0,
        current_temp=18.0,
        ac_setpoint_strategy="offset",
        ac_heat_offset_max=2.0,
    )
    calls = _set_temps(hass)
    assert calls
    # boost (unchanged): 18 + 1.0*(30-18) = 30  (not 21+2=23)
    assert calls[0][0][2]["temperature"] == 30.0
