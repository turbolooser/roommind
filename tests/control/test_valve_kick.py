"""Fork: valve kick of the SONOFF TRV-ZBT, after the quirk sonoff_trv_zbt of bontiv/vtherm_quirks."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control import direct_valve
from custom_components.roommind.control.direct_valve import async_release_valve, async_set_valve
from custom_components.roommind.control.mpc_controller import MODE_HEATING, MODE_IDLE

from .test_direct_valve import CLOSE, OPEN, TRV, _climate_calls, _controller, _hass, _number, _trv, _valve_room

EXT = "number.trv_external_temperature_input"
SEL = "select.trv_temperature_sensor_select"


@pytest.fixture(autouse=True)
def _clean():
    direct_valve.clear_valve_cache()
    yield
    direct_valve.clear_valve_cache()


def _select(option="remote_temperature"):
    s = MagicMock()
    s.state = option
    return s


def _trv_at(setpoint, hvac="heat"):
    s = _trv(hvac)
    s.attributes = {**s.attributes, "temperature": setpoint}
    return s


def _kick_room():
    room = _valve_room()
    room["devices"][0]["valve_closing_mode"] = "idle_opening"
    room["devices"][0]["valve_kick"] = True
    return room


def _writes(hass):
    """Every number/select/climate call in order, as (entity, value)."""
    out = []
    for c in hass.services.async_call.call_args_list:
        domain, service, data = c[0][0], c[0][1], c[0][2]
        value = data.get("value", data.get("option", data.get("hvac_mode", data.get("temperature"))))
        out.append((f"{domain}.{service}", data["entity_id"], value))
    return out


def _entities(_hass, _climate, domain, name):
    return {"number": EXT, "select": SEL}[domain]


# --- holding: idle = opening - 1, one kick per new opening ----------------------------------


@pytest.mark.asyncio
async def test_kick_holds_idle_one_below_the_opening_and_asks_for_a_kick():
    hass = _hass({OPEN: _number(), CLOSE: _number(0)})
    with patch.object(direct_valve, "request_kick") as kick:
        await async_set_valve(hass, TRV, OPEN, CLOSE, 40, area_id="a", idle_opening=True, kick=True)

    assert [(e, v) for _, e, v in _writes(hass)] == [(OPEN, 40.0), (CLOSE, 39.0)]
    kick.assert_called_once_with(hass, TRV, 40, "a")


@pytest.mark.asyncio
async def test_kick_idle_never_goes_below_zero():
    hass = _hass({OPEN: _number(), CLOSE: _number(50)})
    with patch.object(direct_valve, "request_kick"):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 0, area_id="a", idle_opening=True, kick=True)

    assert [(e, v) for _, e, v in _writes(hass)] == [(OPEN, 0.0), (CLOSE, 0.0)]


@pytest.mark.asyncio
async def test_without_kick_the_hold_is_unchanged():
    hass = _hass({OPEN: _number(), CLOSE: _number(0)})
    with patch.object(direct_valve, "request_kick") as kick:
        await async_set_valve(hass, TRV, OPEN, CLOSE, 40, area_id="a", idle_opening=True)

    assert [(e, v) for _, e, v in _writes(hass)] == [(OPEN, 40.0), (CLOSE, 40.0)]
    kick.assert_not_called()


@pytest.mark.asyncio
async def test_release_with_kick_closes_idle_and_kicks():
    hass = _hass({OPEN: _number(40), CLOSE: _number(39)})
    with patch.object(direct_valve, "request_kick"):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 40, area_id="a", idle_opening=True, kick=True)
    hass.services.async_call.reset_mock()
    with patch.object(direct_valve, "request_kick") as kick:
        await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a", idle_opening=True, kick=True)

    assert [(e, v) for _, e, v in _writes(hass)] == [(OPEN, 100.0), (CLOSE, 0.0)]
    kick.assert_called_once_with(hass, TRV, 100, "a", force=True)


def test_the_same_opening_is_not_kicked_again_and_asks_during_a_kick_merge():
    hass = MagicMock()
    running = MagicMock()
    running.done.return_value = False
    hass.async_create_background_task = MagicMock(side_effect=lambda coro, name: (coro.close(), running)[1])

    direct_valve.request_kick(hass, TRV, 40, "a")
    direct_valve.request_kick(hass, TRV, 40, "a")  # same opening: nothing
    assert hass.async_create_background_task.call_count == 1
    assert TRV not in direct_valve._kick_pending

    direct_valve.request_kick(hass, TRV, 50, "a")  # during the kick: one pending
    direct_valve.request_kick(hass, TRV, 60, "a")
    assert hass.async_create_background_task.call_count == 1
    assert TRV in direct_valve._kick_pending


# --- one kick ---------------------------------------------------------------------------


async def _no_sleep(_s):
    return None


@pytest.mark.asyncio
async def test_kick_feeds_cold_then_hot_then_the_saved_room_temperature():
    states = {TRV: _trv_at(29.5), EXT: _number(18.4, hi=99.9, step=0.1), SEL: _select()}
    hass = _hass(states)

    def write(domain, service, data, **_kw):
        if data["entity_id"] == EXT:
            states[EXT] = _number(data["value"], hi=99.9, step=0.1)

    hass.services.async_call.side_effect = write
    with (
        patch.object(direct_valve, "_device_entity", _entities),
        patch.object(direct_valve.asyncio, "sleep", _no_sleep),
    ):
        await direct_valve._async_kick_once(hass, TRV, "a")

    assert [(e, v) for _, e, v in _writes(hass)] == [(EXT, 3.0), (EXT, 32.0), (EXT, 18.4)]


@pytest.mark.asyncio
async def test_kick_pulses_beyond_the_setpoint_range_whatever_setpoint_ha_still_shows():
    """17.11.2026: RoomMind's new setpoint reached HA after the kick started; the kick pulsed around the old one."""
    for stale in (5.0, 15.0, 29.5):
        states = {TRV: _trv_at(stale), EXT: _number(18.4, hi=99.9, step=0.1), SEL: _select()}
        hass = _hass(states)
        with (
            patch.object(direct_valve, "_device_entity", _entities),
            patch.object(direct_valve.asyncio, "sleep", _no_sleep),
        ):
            await direct_valve._async_kick_once(hass, TRV, "a")
        assert [v for _, e, v in _writes(hass)][:2] == [3.0, 32.0]


@pytest.mark.asyncio
async def test_kick_keeps_a_room_temperature_someone_else_fed_meanwhile():
    """Klima_18 writes the real room temperature: the kick must not put an older one back."""
    states = {TRV: _trv_at(20.0), EXT: _number(18.4, hi=99.9, step=0.1), SEL: _select()}
    hass = _hass(states)

    def write(domain, service, data, **_kw):
        if data["entity_id"] == EXT:
            # the automation lands right after the hot pulse
            states[EXT] = _number(18.5 if data["value"] == 32.0 else data["value"], hi=99.9, step=0.1)

    hass.services.async_call.side_effect = write
    with (
        patch.object(direct_valve, "_device_entity", _entities),
        patch.object(direct_valve.asyncio, "sleep", _no_sleep),
    ):
        await direct_valve._async_kick_once(hass, TRV, "a")

    assert [(e, v) for _, e, v in _writes(hass)] == [(EXT, 3.0), (EXT, 32.0)]


@pytest.mark.asyncio
async def test_kick_on_the_built_in_sensor_switches_to_remote_and_back():
    states = {TRV: _trv_at(20.0), EXT: _number(0, hi=99.9, step=0.1), SEL: _select("local_temperature")}
    hass = _hass(states)
    with (
        patch.object(direct_valve, "_device_entity", _entities),
        patch.object(direct_valve.asyncio, "sleep", _no_sleep),
    ):
        await direct_valve._async_kick_once(hass, TRV, "a")

    assert [(e, v) for _, e, v in _writes(hass)] == [
        (EXT, 3.0),
        (SEL, "remote_temperature"),
        (EXT, 32.0),
        (SEL, "local_temperature"),
    ]


@pytest.mark.asyncio
async def test_kick_restores_on_cancel():
    states = {TRV: _trv_at(20.0), EXT: _number(18.4, hi=99.9, step=0.1), SEL: _select()}
    hass = _hass(states)

    def write(domain, service, data, **_kw):
        if data["entity_id"] == EXT:
            states[EXT] = _number(data["value"], hi=99.9, step=0.1)

    hass.services.async_call.side_effect = write
    started = asyncio.Event()

    async def sleep(_s):
        started.set()
        await asyncio.Event().wait()

    with patch.object(direct_valve, "_device_entity", _entities), patch.object(direct_valve.asyncio, "sleep", sleep):
        task = asyncio.ensure_future(direct_valve._async_kick_once(hass, TRV, "a"))
        await started.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert [(e, v) for _, e, v in _writes(hass)] == [(EXT, 3.0), (EXT, 18.4)]


@pytest.mark.asyncio
async def test_no_kick_while_the_trv_is_off():
    states = {TRV: _trv_at(5.0, "off"), EXT: _number(18.4, hi=99.9, step=0.1), SEL: _select()}
    hass = _hass(states)
    with (
        patch.object(direct_valve, "_device_entity", _entities),
        patch.object(direct_valve.asyncio, "sleep", _no_sleep),
    ):
        await direct_valve._async_kick_once(hass, TRV, "a")

    assert _writes(hass) == []


@pytest.mark.asyncio
async def test_leaving_off_the_kick_waits_for_the_trv_state():
    states = {TRV: _trv_at(29.5, "off"), EXT: _number(18.4, hi=99.9, step=0.1), SEL: _select()}
    hass = _hass(states)
    slept = []

    async def sleep(s):
        slept.append(s)
        states[TRV] = _trv_at(29.5, "heat")  # the TRV reports heat after the first second

    with patch.object(direct_valve, "_device_entity", _entities), patch.object(direct_valve.asyncio, "sleep", sleep):
        await direct_valve._async_kick_once(hass, TRV, "a")

    assert slept[0] == 1.0
    assert [v for _, e, v in _writes(hass) if e == EXT][:2] == [3.0, 32.0]


# --- controller: idle 0 before off ----------------------------------------------------------


@pytest.mark.asyncio
async def test_kick_trv_gets_idle_zero_before_it_goes_off():
    states = {TRV: _trv_at(29.5), OPEN: _number(), CLOSE: _number(0)}
    hass = _hass(states)
    ctrl = _controller(hass, _kick_room())
    with patch.object(direct_valve, "request_kick"):
        await ctrl.async_apply(
            MODE_HEATING,
            TargetTemps(heat=21.0, cool=24.0),
            power_fraction=0.35,
            current_temp=20.6,
            heating_boost_target=30.0,
        )
        states[OPEN], states[CLOSE] = _number(35), _number(34)
        hass.services.async_call.reset_mock()
        await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=21.0, cool=24.0), power_fraction=0.0, current_temp=21.3)

    calls = [(s, e, v) for s, e, v in _writes(hass) if s in ("number.set_value", "climate.set_hvac_mode")]
    assert calls[:3] == [
        ("number.set_value", OPEN, 100.0),
        ("number.set_value", CLOSE, 0.0),
        ("climate.set_hvac_mode", TRV, "off"),
    ]


@pytest.mark.asyncio
async def test_without_kick_the_off_comes_first_as_before():
    room = _valve_room()
    room["devices"][0]["valve_closing_mode"] = "idle_opening"
    states = {TRV: _trv_at(29.5), OPEN: _number(35), CLOSE: _number(35)}
    hass = _hass(states)
    ctrl = _controller(hass, room)
    await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=21.0, cool=24.0), power_fraction=0.0, current_temp=21.3)

    assert [c["hvac_mode"] for c in _climate_calls(hass, "set_hvac_mode")] == ["off"]
    services = [s for s, _e, _v in _writes(hass)]
    assert services.index("climate.set_hvac_mode") < services.index("number.set_value")
