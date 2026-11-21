"""Tests for the window frost floor of the idle setback (fork feature).

While an open window pauses a room, a heating setback goes down to
``frost_temp`` instead of target - offset: with the plain setback, a room that
cools below it makes the TRV open its valve again with the window still open.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import (
    _idle_cfg,
    async_idle_device,
    clear_command_cache,
)

from .conftest import build_hass


def _trv_state(hvac: str = "heat", temperature: float = 18.5, hvac_modes=None, min_temp: float = 5.0) -> MagicMock:
    state = MagicMock()
    state.state = hvac
    state.attributes = {
        "hvac_modes": hvac_modes if hvac_modes is not None else ["heat", "off"],
        "min_temp": min_temp,
        "max_temp": 30.0,
        "target_temp_step": 0.5,
        "temperature": temperature,
    }
    return state


def _devices(idle_action: str = "setback", **extra) -> list[dict]:
    return [
        {
            "entity_id": "climate.trv1",
            "type": "trv",
            "role": "auto",
            "idle_action": idle_action,
            "idle_fan_mode": "",
            **extra,
        }
    ]


def _temps(hass) -> list[float]:
    return [c[0][2]["temperature"] for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]


@pytest.fixture(autouse=True)
def _reset():
    clear_command_cache()
    _idle_cfg["setback_offset"] = 1.0
    _idle_cfg["off_after_minutes"] = 0.0
    yield
    clear_command_cache()


@pytest.mark.asyncio
async def test_setback_goes_to_frost_while_window_open():
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=18.5))

    held = await async_idle_device(
        hass, "climate.trv1", _devices(), area_id="bath", targets=TargetTemps(heat=19.5, cool=None), frost_temp=7.0
    )

    assert _temps(hass) == [7.0]
    assert held is True


@pytest.mark.asyncio
async def test_setback_without_frost_keeps_target_minus_offset():
    """No frost_temp (window closed, or rooms without window sensors): upstream setback."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=21.0))

    await async_idle_device(hass, "climate.trv1", _devices(), area_id="bath", targets=TargetTemps(heat=19.5, cool=None))

    assert _temps(hass) == [18.5]


@pytest.mark.asyncio
async def test_frost_never_raises_a_lower_setback():
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=21.0))

    await async_idle_device(
        hass, "climate.trv1", _devices(), area_id="bath", targets=TargetTemps(heat=7.0, cool=None), frost_temp=7.0
    )

    assert _temps(hass) == [6.0]


@pytest.mark.asyncio
async def test_frost_clamped_to_device_minimum():
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=18.5, min_temp=10.0))

    await async_idle_device(
        hass, "climate.trv1", _devices(), area_id="bath", targets=TargetTemps(heat=19.5, cool=None), frost_temp=7.0
    )

    assert _temps(hass) == [10.0]


@pytest.mark.asyncio
async def test_frost_already_set_sends_nothing():
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=7.0))

    held = await async_idle_device(
        hass, "climate.trv1", _devices(), area_id="bath", targets=TargetTemps(heat=19.5, cool=None), frost_temp=7.0
    )

    assert _temps(hass) == []
    assert held is True


@pytest.mark.asyncio
async def test_cooling_setback_ignores_frost():
    hass = build_hass()
    state = _trv_state("cool", temperature=24.0, hvac_modes=["cool", "off"])
    hass.states.get = MagicMock(return_value=state)

    await async_idle_device(
        hass,
        "climate.trv1",
        _devices(type="ac"),
        area_id="bath",
        targets=TargetTemps(heat=None, cool=24.0),
        frost_temp=7.0,
    )

    assert _temps(hass) == [25.0]


@pytest.mark.asyncio
async def test_off_fallback_setpoint_uses_frost():
    """Without a usable min_temp the setpoint sent before "off" is the fallback; with the window open the frost floor."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=19.5, min_temp=0.0))

    await async_idle_device(
        hass,
        "climate.trv1",
        _devices(idle_action="off"),
        area_id="bath",
        targets=TargetTemps(heat=19.5, cool=None),
        frost_temp=7.0,
    )

    assert _temps(hass) == [7.0]
