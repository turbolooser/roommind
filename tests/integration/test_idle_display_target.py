"""Tests for the idle display-target selection (auto climate_mode).

While idle there is no single active setpoint. Naively showing comfort_heat
makes the displayed target snap down on every idle gap during cooling season,
which reads as the room flapping between heat and cool. The coordinator picks
the setpoint matching the room's actual direction instead.
"""

from __future__ import annotations

import pytest

from custom_components.roommind.const import MODE_COOLING, MODE_HEATING, TargetTemps

TARGETS = TargetTemps(heat=20.0, cool=24.0)


class TestIdleDisplayTarget:
    @pytest.mark.asyncio
    async def test_last_active_cooling_shows_cool(self, coordinator):
        """After cooling has run, an idle gap keeps showing the cool setpoint."""
        coordinator._last_active_mode["living_room"] = MODE_COOLING
        # Both directions allowed (shoulder season) -> last active wins.
        result = coordinator._idle_display_target("living_room", TARGETS, can_heat=True, can_cool=True)
        assert result == 24.0

    @pytest.mark.asyncio
    async def test_last_active_heating_shows_heat(self, coordinator):
        """After heating has run, an idle gap keeps showing the heat setpoint."""
        coordinator._last_active_mode["living_room"] = MODE_HEATING
        result = coordinator._idle_display_target("living_room", TARGETS, can_heat=True, can_cool=True)
        assert result == 20.0

    @pytest.mark.asyncio
    async def test_no_history_cool_season_shows_cool(self, coordinator):
        """No active history yet: the capability/season gate decides (cool-only)."""
        result = coordinator._idle_display_target("living_room", TARGETS, can_heat=False, can_cool=True)
        assert result == 24.0

    @pytest.mark.asyncio
    async def test_no_history_heat_season_shows_heat(self, coordinator):
        """No active history yet: the capability/season gate decides (heat-only)."""
        result = coordinator._idle_display_target("living_room", TARGETS, can_heat=True, can_cool=False)
        assert result == 20.0

    @pytest.mark.asyncio
    async def test_ambiguous_falls_back_to_heat(self, coordinator):
        """No history and both directions allowed: fall back to the heat setpoint."""
        result = coordinator._idle_display_target("living_room", TARGETS, can_heat=True, can_cool=True)
        assert result == 20.0

    @pytest.mark.asyncio
    async def test_last_active_cooling_but_no_cool_target_falls_through(self, coordinator):
        """A stale cooling history with no cool target must not return None."""
        coordinator._last_active_mode["living_room"] = MODE_COOLING
        result = coordinator._idle_display_target(
            "living_room", TargetTemps(heat=20.0, cool=None), can_heat=True, can_cool=False
        )
        assert result == 20.0
