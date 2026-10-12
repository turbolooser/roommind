"""Window sensors that only pause in one mode (fork feature).

Upstream pauses climate control whenever a window is open, full stop.  That is
wrong for a room cooling against a deliberately open terrace door in summer,
while the same room absolutely wants the pause in winter.  ``window_pause_mode``
makes the pause conditional on what the room is actually doing.

The important invariant, pinned below: lifting the *control* pause must never
lift the *learning* pause.  An open window skews the heat balance regardless of
mode, so the EKF has to stay frozen either way.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    WINDOW_PAUSE_ALWAYS,
    WINDOW_PAUSE_COOLING_ONLY,
    WINDOW_PAUSE_HEATING_ONLY,
)
from custom_components.roommind.coordinator import _window_pause_applies

from .conftest import ROOM_LIVING, make_hass_states, setup_room

WINDOW = "binary_sensor.window_living"
ROOM_WITH_WINDOW = {
    **ROOM_LIVING,
    "window_sensors": [WINDOW],
    "window_open_delay": 0,
    "window_close_delay": 0,
}


# ---------------------------------------------------------------------------
# the decision itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [MODE_HEATING, MODE_COOLING, MODE_IDLE])
def test_always_pauses_in_every_mode(mode):
    """The default must behave exactly as upstream."""
    assert _window_pause_applies({"window_pause_mode": WINDOW_PAUSE_ALWAYS}, mode) is True


@pytest.mark.parametrize("mode", [MODE_HEATING, MODE_COOLING, MODE_IDLE])
def test_missing_field_is_always(mode):
    """A room saved before this feature existed keeps the old behaviour."""
    assert _window_pause_applies({}, mode) is True


@pytest.mark.parametrize(
    ("setting", "mode", "expected"),
    [
        (WINDOW_PAUSE_HEATING_ONLY, MODE_HEATING, True),
        (WINDOW_PAUSE_HEATING_ONLY, MODE_COOLING, False),
        (WINDOW_PAUSE_HEATING_ONLY, MODE_IDLE, False),
        (WINDOW_PAUSE_COOLING_ONLY, MODE_COOLING, True),
        (WINDOW_PAUSE_COOLING_ONLY, MODE_HEATING, False),
        (WINDOW_PAUSE_COOLING_ONLY, MODE_IDLE, False),
    ],
)
def test_conditional_settings(setting, mode, expected):
    assert _window_pause_applies({"window_pause_mode": setting}, mode) is expected


@pytest.mark.parametrize("junk", ["", "heating", "HEATING_ONLY", None, 0, "nonsense"])
def test_unknown_value_falls_back_to_pausing(junk):
    """A corrupted store must never silently disable the window pause."""
    assert _window_pause_applies({"window_pause_mode": junk}, MODE_HEATING) is True
    assert _window_pause_applies({"window_pause_mode": junk}, MODE_COOLING) is True


# ---------------------------------------------------------------------------
# through the coordinator, with a real open window
# ---------------------------------------------------------------------------


async def _cycle(coordinator, real_store, room_extra, *, window="on", temp="18.0", outdoor="5.0"):
    await setup_room(real_store, {**ROOM_WITH_WINDOW, **room_extra})
    coordinator.hass.states.get = MagicMock(
        side_effect=make_hass_states(temp=temp, outdoor_temp=outdoor, extra={WINDOW: window})
    )
    data = await coordinator._async_update_data()
    return data["rooms"]["living_room"]


class TestThroughCoordinator:
    @pytest.mark.asyncio
    async def test_heating_only_still_pauses_when_heating(self, coordinator, real_store):
        room = await _cycle(coordinator, real_store, {"window_pause_mode": WINDOW_PAUSE_HEATING_ONLY})
        assert room["mode"] == MODE_IDLE
        assert room["window_open"] is True

    @pytest.mark.asyncio
    async def test_cooling_only_ignores_the_window_while_heating(self, coordinator, real_store):
        """The room is cold and wants heat; with cooling_only the window is ignored."""
        room = await _cycle(coordinator, real_store, {"window_pause_mode": WINDOW_PAUSE_COOLING_ONLY})
        assert room["mode"] != MODE_IDLE, "heating should continue despite the open window"
        assert room["window_open"] is False, "the pause is lifted, so the room is not reported as paused"

    @pytest.mark.asyncio
    async def test_default_room_is_unchanged(self, coordinator, real_store):
        """No setting at all: identical to upstream."""
        room = await _cycle(coordinator, real_store, {})
        assert room["mode"] == MODE_IDLE
        assert room["window_open"] is True


# ---------------------------------------------------------------------------
# the invariant that must not break
# ---------------------------------------------------------------------------


class TestLearningStaysFrozen:
    @pytest.mark.asyncio
    async def test_ekf_is_not_trained_while_the_window_is_open(self, coordinator, real_store):
        """Even with the control pause lifted, raw_open must freeze the model.

        Checked at the seam: the training manager receives raw_open=True, which
        is what gates the update — not the (now cleared) window_open flag.
        """
        trainer = coordinator._ekf_training
        seen = []
        original = trainer.process

        def spy(*args, **kwargs):
            seen.append(kwargs.get("raw_open"))
            return original(*args, **kwargs)

        trainer.process = MagicMock(side_effect=spy)
        await _cycle(coordinator, real_store, {"window_pause_mode": WINDOW_PAUSE_COOLING_ONLY})
        assert seen, "training path was not reached at all"
        assert all(x is True for x in seen), f"raw_open must stay True, got {seen}"
