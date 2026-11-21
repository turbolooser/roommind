"""Integration: an open window sets heating setbacks to the frost floor (fork feature)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import DEFAULT_WINDOW_FROST_TEMP
from custom_components.roommind.coordinator import RoomMindCoordinator, _window_frost_temp

from .conftest import DEFAULT_SETTINGS, ROOM_LIVING, make_hass_states, setup_room

TRV = "climate.living_room"
WINDOW = "binary_sensor.window_living"

ROOM_WITH_WINDOW = {
    **ROOM_LIVING,
    "devices": [
        {
            "entity_id": TRV,
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "setback",
            "idle_fan_mode": "",
        }
    ],
    "window_sensors": [WINDOW],
    "window_open_delay": 0,
    "window_close_delay": 0,
}

TRV_ATTRS = {
    "hvac_modes": ["off", "heat"],
    "hvac_action": "idle",
    "min_temp": 5.0,
    "max_temp": 30.0,
    "target_temp_step": 0.5,
    "temperature": 19.0,
}


def _states(window: str, temp: str = "18.0", setpoint: float = 19.0):
    return make_hass_states(
        temp=temp,
        extra={WINDOW: (window, {}), TRV: ("heat", {**TRV_ATTRS, "temperature": setpoint})},
    )


def _setpoints(hass) -> list[float]:
    return [
        c[0][2]["temperature"]
        for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == TRV
    ]


async def _cycle(coordinator, states) -> dict:
    coordinator.hass.services.async_call.reset_mock()
    coordinator.hass.states.get = MagicMock(side_effect=states)
    data = await coordinator._async_update_data()
    return data["rooms"]["living_room"]


class TestWindowFrost:
    @pytest.mark.asyncio
    async def test_open_window_sets_frost(self, coordinator, real_store):
        await setup_room(real_store, ROOM_WITH_WINDOW)

        room = await _cycle(coordinator, _states("on"))

        assert room["window_open"] is True
        assert room["mode"] == "idle"
        assert _setpoints(coordinator.hass) == [DEFAULT_WINDOW_FROST_TEMP]

    @pytest.mark.asyncio
    async def test_close_window_resumes_normal_control(self, coordinator, real_store):
        await setup_room(real_store, ROOM_WITH_WINDOW)
        await _cycle(coordinator, _states("on"))

        # Window closed, the TRV still holds the frost setpoint: normal heating takes over.
        room = await _cycle(coordinator, _states("off", setpoint=DEFAULT_WINDOW_FROST_TEMP))

        assert room["window_open"] is False
        assert room["mode"] == "heating"
        sent = _setpoints(coordinator.hass)
        assert sent
        assert all(t > DEFAULT_WINDOW_FROST_TEMP for t in sent)

    @pytest.mark.asyncio
    async def test_close_window_idle_returns_to_plain_setback(self, coordinator, real_store):
        """Room warm enough after closing: back to target - offset, not stuck at frost."""
        await setup_room(real_store, ROOM_WITH_WINDOW)
        await _cycle(coordinator, _states("on", temp="22.5"))

        room = await _cycle(coordinator, _states("off", temp="22.5", setpoint=DEFAULT_WINDOW_FROST_TEMP))

        assert room["mode"] == "idle"
        sent = _setpoints(coordinator.hass)
        assert sent
        assert DEFAULT_WINDOW_FROST_TEMP not in sent

    @pytest.mark.asyncio
    async def test_restart_with_window_open_sets_frost(self, hass, mock_config_entry, real_store):
        """A fresh coordinator (HA restart) with the window already open goes to frost on its first cycle."""
        await setup_room(real_store, ROOM_WITH_WINDOW)
        hass.data = {"roommind": {"store": real_store}}
        hass.services.async_call = AsyncMock()
        hass.config.latitude = 50.0
        hass.config.longitude = 10.0
        hass.config.units = MagicMock()
        hass.config.units.temperature_unit = "°C"
        with patch("homeassistant.helpers.frame.report_usage"):
            fresh = RoomMindCoordinator(hass, mock_config_entry)

        room = await _cycle(fresh, _states("on"))

        assert room["window_open"] is True
        assert _setpoints(hass) == [DEFAULT_WINDOW_FROST_TEMP]

    @pytest.mark.asyncio
    async def test_restart_window_sensor_unavailable_sends_nothing_then_frost(self, coordinator, real_store):
        await setup_room(real_store, ROOM_WITH_WINDOW)

        await _cycle(coordinator, _states("unavailable"))
        assert _setpoints(coordinator.hass) == []

        room = await _cycle(coordinator, _states("on"))
        assert room["window_open"] is True
        assert _setpoints(coordinator.hass) == [DEFAULT_WINDOW_FROST_TEMP]

    @pytest.mark.asyncio
    async def test_configured_frost_temp(self, coordinator, real_store):
        await setup_room(real_store, ROOM_WITH_WINDOW, settings={**DEFAULT_SETTINGS, "window_frost_temp": 9.0})

        await _cycle(coordinator, _states("on"))

        assert _setpoints(coordinator.hass) == [9.0]

    @pytest.mark.asyncio
    async def test_zero_keeps_plain_setback(self, coordinator, real_store):
        await setup_room(real_store, ROOM_WITH_WINDOW, settings={**DEFAULT_SETTINGS, "window_frost_temp": 0})

        await _cycle(coordinator, _states("on", setpoint=21.0))

        assert _setpoints(coordinator.hass) == [21.0 - 2.0]  # comfort 21 - default offset 2

    @pytest.mark.asyncio
    async def test_room_without_window_sensor_untouched(self, coordinator, real_store):
        room_cfg = {**ROOM_WITH_WINDOW, "window_sensors": []}
        await setup_room(real_store, room_cfg)

        room = await _cycle(coordinator, _states("on", temp="22.5", setpoint=21.0))

        assert room["window_open"] is False
        assert DEFAULT_WINDOW_FROST_TEMP not in _setpoints(coordinator.hass)


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({}, DEFAULT_WINDOW_FROST_TEMP),
        ({"window_frost_temp": 8.5}, 8.5),
        ({"window_frost_temp": 0}, None),
        ({"window_frost_temp": -1}, None),
        ({"window_frost_temp": "x"}, DEFAULT_WINDOW_FROST_TEMP),
        ({"window_frost_temp": None}, DEFAULT_WINDOW_FROST_TEMP),
    ],
)
def test_window_frost_temp_setting(settings, expected):
    assert _window_frost_temp(settings) == expected
