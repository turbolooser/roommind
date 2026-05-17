"""Config flow for RoomMind integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DEFAULT_IDLE_OFF_AFTER_MINUTES,
    DEFAULT_VACATION_ACTION,
    DEFAULT_VACATION_FROST_TEMP,
    DOMAIN,
    VACATION_ACTIONS,
)


class RoomMindConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle the config flow for RoomMind."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, str] | None = None) -> ConfigFlowResult:
        """Handle the initial step – just confirm setup."""
        if user_input is not None:
            # Prevent multiple instances
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="RoomMind", data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RoomMindOptionsFlow:
        """Return the options flow handler."""
        return RoomMindOptionsFlow()


class RoomMindOptionsFlow(OptionsFlow):
    """Handle RoomMind options.

    Settings are persisted to the RoomMind store (the single source of truth
    shared with the panel WebSocket API), not to ``config_entry.options``.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage RoomMind options (vacation behaviour)."""
        store = self.hass.data.get(DOMAIN, {}).get("store")

        if user_input is not None:
            if store is not None:
                await store.async_save_settings(
                    {
                        "vacation_action": user_input["vacation_action"],
                        "vacation_frost_temp": user_input["vacation_frost_temp"],
                        "idle_off_after_minutes": user_input["idle_off_after_minutes"],
                    }
                )
            return self.async_create_entry(title="", data={})

        settings = store.get_settings() if store is not None else {}
        current_action = settings.get("vacation_action", DEFAULT_VACATION_ACTION)
        current_frost = settings.get("vacation_frost_temp", DEFAULT_VACATION_FROST_TEMP)
        current_idle_off = settings.get("idle_off_after_minutes", DEFAULT_IDLE_OFF_AFTER_MINUTES)

        schema = vol.Schema(
            {
                vol.Required("vacation_action", default=current_action): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(VACATION_ACTIONS),
                        translation_key="vacation_action",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("vacation_frost_temp", default=current_frost): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=3.0,
                        max=15.0,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required("idle_off_after_minutes", default=current_idle_off): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=240,
                        step=5,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
