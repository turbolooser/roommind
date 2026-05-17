"""Tests for the RoomMind config and options flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.config_flow import (
    RoomMindConfigFlow,
    RoomMindOptionsFlow,
)
from custom_components.roommind.const import DOMAIN


class TestConfigFlow:
    """Tests for the initial config flow."""

    @pytest.mark.asyncio
    async def test_user_step_shows_form(self, hass):
        """The initial step shows a confirmation form."""
        flow = RoomMindConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user()

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_user_step_creates_entry(self, hass):
        """Confirming the form creates the RoomMind entry."""
        flow = RoomMindConfigFlow()
        flow.hass = hass
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        result = await flow.async_step_user({})

        assert result["type"] == "create_entry"
        assert result["title"] == "RoomMind"
        flow.async_set_unique_id.assert_awaited_once_with(DOMAIN)

    def test_async_get_options_flow_returns_handler(self, mock_config_entry):
        """The config flow exposes the options flow handler."""
        flow = RoomMindConfigFlow.async_get_options_flow(mock_config_entry)
        assert isinstance(flow, RoomMindOptionsFlow)


class TestOptionsFlow:
    """Tests for the options flow (vacation behaviour)."""

    @pytest.mark.asyncio
    async def test_init_shows_form_with_current_values(self, hass):
        """The options form is shown, prefilled from the store."""
        store = MagicMock()
        store.get_settings.return_value = {
            "vacation_action": "off",
            "vacation_frost_temp": 9.0,
        }
        hass.data = {DOMAIN: {"store": store}}
        flow = RoomMindOptionsFlow()
        flow.hass = hass

        result = await flow.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_init_uses_defaults_when_store_missing(self, hass):
        """The form still renders when the store is not available yet."""
        hass.data = {}
        flow = RoomMindOptionsFlow()
        flow.hass = hass

        result = await flow.async_step_init()

        assert result["type"] == "form"

    @pytest.mark.asyncio
    async def test_submit_persists_to_store(self, hass):
        """Submitting the form writes the values to the RoomMind store."""
        store = MagicMock()
        store.get_settings.return_value = {}
        store.async_save_settings = AsyncMock()
        hass.data = {DOMAIN: {"store": store}}
        flow = RoomMindOptionsFlow()
        flow.hass = hass

        user_input = {
            "vacation_action": "off",
            "vacation_frost_temp": 8.0,
            "ac_setpoint_strategy": "offset",
            "ac_cool_offset_max": 2.5,
            "ac_heat_offset_max": 1.5,
            "idle_off_after_minutes": 30,
            "idle_setback_offset": 2.0,
            "demand_control_enabled": True,
            "demand_select_entities": ["select.ac_demand"],
            "demand_min": 30,
            "demand_max": 95,
            "demand_hysteresis": 10,
            "demand_min_hold_minutes": 10,
        }
        result = await flow.async_step_init(user_input)

        assert result["type"] == "create_entry"
        store.async_save_settings.assert_awaited_once_with(user_input)

    @pytest.mark.asyncio
    async def test_submit_without_store_does_not_crash(self, hass):
        """Submitting without an available store still completes cleanly."""
        hass.data = {}
        flow = RoomMindOptionsFlow()
        flow.hass = hass

        result = await flow.async_step_init(
            {
                "vacation_action": "setback",
                "vacation_frost_temp": 7.0,
                "ac_setpoint_strategy": "boost",
                "ac_cool_offset_max": 2.0,
                "ac_heat_offset_max": 2.0,
                "idle_off_after_minutes": 0,
                "idle_setback_offset": 3.0,
                "demand_control_enabled": False,
                "demand_select_entities": [],
                "demand_min": 30,
                "demand_max": 95,
                "demand_hysteresis": 10,
                "demand_min_hold_minutes": 10,
            }
        )

        assert result["type"] == "create_entry"
