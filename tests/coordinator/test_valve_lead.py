"""Coordinator wiring of the learned valve lead (controller, persistence, pruning)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind import coordinator as coordinator_module
from custom_components.roommind.const import MODE_HEATING

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get
from .test_valve_release import CLOSE, NUMBER_ATTRS, OPEN, VALVE_ROOM

AREA = SAMPLE_ROOM["area_id"]


def _setup(hass, mock_config_entry, settings):
    store = _make_store_mock({AREA: VALVE_ROOM})
    store.get_settings.return_value = {"outdoor_temp_sensor": "sensor.outdoor_temp", **settings}
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp="18.0", humidity="55.0", extra={OPEN: ("40", NUMBER_ATTRS), CLOSE: ("60", NUMBER_ATTRS)}
        )
    )
    hass.services.async_call = AsyncMock()
    return store, _create_coordinator(hass, mock_config_entry)


@pytest.mark.asyncio
async def test_learned_lead_survives_a_restart(hass, mock_config_entry):
    saved = {AREA: {"lead": 11.5, "trim": -0.2, "turns": 7}, "gone_room": {"lead": 20.0, "trim": 0.1, "turns": 3}}
    store, coordinator = _setup(hass, mock_config_entry, {"valve_lead": saved})
    await coordinator._async_update_data()
    lead = coordinator._valve_lead_tracker.get(AREA)
    assert (lead.minutes, lead.trim) == (11.5, -0.2)
    # A room that is no longer configured is dropped, and the change is saved
    assert set(coordinator._valve_lead_tracker.get_state()) == {AREA}
    coordinator._thermal_save_count = coordinator_module.THERMAL_SAVE_CYCLES - 1
    await coordinator._async_update_data()
    calls = [c.args[0] for c in store.async_save_settings.call_args_list if "valve_lead" in c.args[0]]
    assert calls and calls[-1]["valve_lead"] == {AREA: {"lead": 11.5, "trim": -0.2, "turns": 7}}
    assert coordinator._valve_lead_tracker.dirty is False


@pytest.mark.asyncio
async def test_controller_gets_the_lead_and_feeds_it_back(hass, mock_config_entry, monkeypatch):
    seen = {}
    real = coordinator_module.MPCController

    class Spy(real):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            seen["lead"] = kwargs.get("valve_lead")
            super().__init__(*args, **kwargs)

        async def async_evaluate(self, current_temp, targets):
            self.valve_feedback = (2.0, 0.4)
            return MODE_HEATING, 0.4

    monkeypatch.setattr(coordinator_module, "MPCController", Spy)
    _, coordinator = _setup(hass, mock_config_entry, {"valve_lead": {AREA: {"lead": 12.0, "trim": 0.0, "turns": 1}}})
    await coordinator._async_update_data()
    assert seen["lead"].minutes == 12.0
    coordinator._valve_lead_tracker._at[AREA] -= 600  # ten minutes of a room below its target
    await coordinator._async_update_data()
    assert coordinator._valve_lead_tracker.get(AREA).trim != 0.0


@pytest.mark.asyncio
async def test_thermal_reset_forgets_the_lead(hass, mock_config_entry):
    _, coordinator = _setup(hass, mock_config_entry, {"valve_lead": {AREA: {"lead": 12.0, "trim": 0.3, "turns": 4}}})
    await coordinator._async_update_data()
    coordinator.reset_thermal_room(AREA)
    assert coordinator._valve_lead_tracker.get_state() == {}
    coordinator._valve_lead_tracker.load_state({AREA: {"lead": 12.0, "trim": 0.3, "turns": 4}})
    coordinator.reset_thermal_all()
    assert coordinator._valve_lead_tracker.get_state() == {}
