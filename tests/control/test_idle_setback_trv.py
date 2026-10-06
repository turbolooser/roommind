"""Tests for idle_action='setback' on thermostats (TRVs) and the per-device offset.

Fork feature. Upstream documents setback for climate devices only; here it is a
supported, tested option for TRVs too, because on a sluggish radiator "low"
(setpoint to device minimum) lets the radiator go cold and heat then takes
minutes to return. The offset is resolved per device because the useful value
follows the device type: ~1 K for a radiator, ~2 K for an AC.
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
from custom_components.roommind.utils.device_utils import (
    DEFAULT_IDLE_SETBACK_OFFSET,
    get_idle_setback_offset,
)

from .conftest import build_hass


def _trv_state(hvac: str = "heat", temperature: float = 21.0) -> MagicMock:
    state = MagicMock()
    state.state = hvac
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "target_temp_step": 0.5,
        "temperature": temperature,
    }
    return state


def _trv(**overrides) -> list[dict]:
    device = {
        "entity_id": "climate.trv1",
        "type": "trv",
        "role": "auto",
        "idle_action": "setback",
        "idle_fan_mode": "",
    }
    device.update(overrides)
    return [device]


def _temp_calls(hass) -> list:
    return [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]


def _hvac_calls(hass) -> list:
    return [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_hvac_mode"]


# ---------------------------------------------------------------------------
# setback on a TRV
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trv_setback_in_heat_uses_target_minus_offset():
    """A TRV sitting in heat is set back to target minus the offset, not turned off."""
    clear_command_cache()
    _idle_cfg["setback_offset"] = DEFAULT_IDLE_SETBACK_OFFSET
    _idle_cfg["off_after_minutes"] = 0.0
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=21.0))

    await async_idle_device(
        hass,
        "climate.trv1",
        _trv(),
        area_id="bath",
        targets=TargetTemps(heat=21.0, cool=None),
    )

    temp_calls = _temp_calls(hass)
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 19.0  # 21.0 - 2.0
    # The valve stays in heat: never commanded off, which is the whole point.
    assert _hvac_calls(hass) == []


@pytest.mark.asyncio
async def test_trv_setback_when_off_falls_back_to_off():
    """A TRV already in 'off' stays off rather than being woken into heat.

    Deliberate: setback shifts an *active* setpoint. Waking a valve that the user
    or an earlier escalation turned off would re-enable heating behind their
    back, so the documented behaviour is to leave it off.
    """
    clear_command_cache()
    _idle_cfg["setback_offset"] = DEFAULT_IDLE_SETBACK_OFFSET
    _idle_cfg["off_after_minutes"] = 0.0
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("off", temperature=5.0))

    await async_idle_device(
        hass,
        "climate.trv1",
        _trv(),
        area_id="bath",
        targets=TargetTemps(heat=21.0, cool=None),
    )

    # Falls back to the off path; no setback setpoint is written.
    assert all(c[0][2].get("hvac_mode") == "off" for c in _hvac_calls(hass))
    assert all(c[0][2]["temperature"] != 19.0 for c in _temp_calls(hass))


@pytest.mark.asyncio
async def test_trv_setback_clamps_to_device_minimum():
    """The setback setpoint never falls below the valve's own min_temp."""
    clear_command_cache()
    _idle_cfg["setback_offset"] = DEFAULT_IDLE_SETBACK_OFFSET
    _idle_cfg["off_after_minutes"] = 0.0
    hass = build_hass()
    state = _trv_state("heat", temperature=21.0)
    state.attributes["min_temp"] = 16.0
    hass.states.get = MagicMock(return_value=state)

    await async_idle_device(
        hass,
        "climate.trv1",
        _trv(),
        area_id="bath",
        targets=TargetTemps(heat=17.0, cool=None),
    )

    temp_calls = _temp_calls(hass)
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 16.0  # 17.0 - 2.0 clamped up to min_temp


# ---------------------------------------------------------------------------
# per-device offset: inheritance and overriding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_device_offset_overrides_global():
    """A device-level offset wins over the global setting."""
    clear_command_cache()
    _idle_cfg["setback_offset"] = 2.0
    _idle_cfg["off_after_minutes"] = 0.0
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=21.0))

    await async_idle_device(
        hass,
        "climate.trv1",
        _trv(idle_setback_offset=1.0),
        area_id="bath",
        targets=TargetTemps(heat=21.0, cool=None),
    )

    temp_calls = _temp_calls(hass)
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 20.0  # 21.0 - 1.0, not - 2.0


@pytest.mark.asyncio
async def test_without_per_device_offset_global_applies():
    """Without a device value the global offset still applies (no migration needed)."""
    clear_command_cache()
    _idle_cfg["setback_offset"] = 2.0
    _idle_cfg["off_after_minutes"] = 0.0
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=21.0))

    await async_idle_device(
        hass,
        "climate.trv1",
        _trv(),  # no idle_setback_offset key at all — the pre-upgrade shape
        area_id="bath",
        targets=TargetTemps(heat=21.0, cool=None),
    )

    temp_calls = _temp_calls(hass)
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 19.0


@pytest.mark.asyncio
async def test_two_devices_in_one_room_get_their_own_offsets():
    """The reason this is per device: a radiator and an AC need different offsets."""
    clear_command_cache()
    _idle_cfg["setback_offset"] = 2.0
    _idle_cfg["off_after_minutes"] = 0.0
    devices = [
        {
            "entity_id": "climate.trv1",
            "type": "trv",
            "role": "auto",
            "idle_action": "setback",
            "idle_fan_mode": "",
            "idle_setback_offset": 1.0,
        },
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "idle_action": "setback",
            "idle_fan_mode": "",
        },
    ]
    targets = TargetTemps(heat=21.0, cool=None)

    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=21.0))
    await async_idle_device(hass, "climate.trv1", devices, area_id="bath", targets=targets)
    assert _temp_calls(hass)[0][0][2]["temperature"] == 20.0  # radiator: 1 K

    clear_command_cache()
    hass2 = build_hass()
    hass2.states.get = MagicMock(return_value=_trv_state("heat", temperature=21.0))
    await async_idle_device(hass2, "climate.ac1", devices, area_id="bath", targets=targets)
    assert _temp_calls(hass2)[0][0][2]["temperature"] == 19.0  # AC: inherits 2 K


# ---------------------------------------------------------------------------
# get_idle_setback_offset — resolution rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (None, 2.0),  # explicit null inherits
        ("", 2.0),  # empty string inherits (UI clears the field)
        (1.0, 1.0),  # plain override
        ("1.5", 1.5),  # numeric string from the UI is coerced
        (0.0, 2.0),  # below range -> inherit, never a no-op setback
        (99.0, 2.0),  # above range -> inherit
        ("abc", 2.0),  # unparseable -> inherit instead of raising in the control loop
    ],
)
def test_get_idle_setback_offset_resolution(stored, expected):
    devices = [{"entity_id": "climate.trv1", "type": "trv", "idle_setback_offset": stored}]
    assert get_idle_setback_offset(devices, "climate.trv1", 2.0) == expected


def test_get_idle_setback_offset_missing_key_and_unknown_device():
    """Absent key and unknown entity both fall back to the global default."""
    assert get_idle_setback_offset([{"entity_id": "climate.trv1", "type": "trv"}], "climate.trv1", 2.0) == 2.0
    assert get_idle_setback_offset([], "climate.nope", 2.0) == 2.0


# ---------------------------------------------------------------------------
# staged-idle escalation: pins what idle_off_after_minutes = 0 actually means
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_off_after_minutes_keeps_setback_forever():
    """0 disables the escalation — the setback holds instead of turning off.

    Pinned because the README said the opposite ("0 = immediate off") for a
    while. For a sluggish radiator 0 is the value you want.
    """
    clear_command_cache()
    _idle_cfg["setback_offset"] = 1.0
    _idle_cfg["off_after_minutes"] = 0.0
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=21.0))

    await async_idle_device(
        hass,
        "climate.trv1",
        _trv(),
        area_id="bath",
        targets=TargetTemps(heat=20.0, cool=None),
    )

    temp_calls = _temp_calls(hass)
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 19.0  # 20.0 - 1.0, no turn-off
    assert _hvac_calls(hass) == []


@pytest.mark.asyncio
async def test_positive_off_after_minutes_escalates_once_elapsed():
    """A value > 0 turns the valve off after that many minutes of continuous setback."""
    import custom_components.roommind.control.mpc_controller as mpc

    clear_command_cache()
    _idle_cfg["setback_offset"] = 1.0
    _idle_cfg["off_after_minutes"] = 30.0
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_trv_state("heat", temperature=21.0))
    targets = TargetTemps(heat=20.0, cool=None)

    # First pass starts the timer and still sets back.
    mpc._idle_setback_since.pop("climate.trv1", None)
    await async_idle_device(hass, "climate.trv1", _trv(), area_id="bath", targets=targets)
    assert _temp_calls(hass)[0][0][2]["temperature"] == 19.0

    # Pretend 31 minutes of continuous setback have passed.
    # Note: clear_command_cache() also resets _idle_cfg to its defaults, so the
    # escalation window has to be re-applied afterwards.
    clear_command_cache()
    _idle_cfg["setback_offset"] = 1.0
    _idle_cfg["off_after_minutes"] = 30.0
    hass2 = build_hass()
    hass2.states.get = MagicMock(return_value=_trv_state("heat", temperature=19.0))
    mpc._idle_setback_since["climate.trv1"] = mpc.time.monotonic() - 31 * 60
    await async_idle_device(hass2, "climate.trv1", _trv(), area_id="bath", targets=targets)

    assert any(c[0][2].get("hvac_mode") == "off" for c in _hvac_calls(hass2))
