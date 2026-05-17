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
    AC_SETPOINT_STRATEGIES,
    DEFAULT_AC_COOL_OFFSET_MAX,
    DEFAULT_AC_HEAT_OFFSET_MAX,
    DEFAULT_AC_SETPOINT_STRATEGY,
    DEFAULT_DEMAND_CONTROL_ENABLED,
    DEFAULT_DEMAND_DOWN_HOLD_MINUTES,
    DEFAULT_DEMAND_HYSTERESIS,
    DEFAULT_DEMAND_MAX,
    DEFAULT_DEMAND_MIN,
    DEFAULT_DEMAND_MIN_HOLD_MINUTES,
    DEFAULT_IDLE_OFF_AFTER_MINUTES,
    DEFAULT_PV_BATTERY_SOC_MIN,
    DEFAULT_PV_BOOST_COOL_PERCENT,
    DEFAULT_PV_BOOST_ENABLED,
    DEFAULT_PV_BOOST_HEAT_PERCENT,
    DEFAULT_PV_SURPLUS_MIN_DURATION_MINUTES,
    DEFAULT_PV_SURPLUS_MIN_W,
    DEFAULT_VACATION_ACTION,
    DEFAULT_VACATION_FROST_TEMP,
    DOMAIN,
    VACATION_ACTIONS,
)
from .utils.device_utils import DEFAULT_IDLE_SETBACK_OFFSET


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
        """Manage RoomMind options (vacation behaviour, AC setpoint strategy)."""
        store = self.hass.data.get(DOMAIN, {}).get("store")

        if user_input is not None:
            if store is not None:
                await store.async_save_settings(
                    {
                        "vacation_action": user_input["vacation_action"],
                        "vacation_frost_temp": user_input["vacation_frost_temp"],
                        "idle_off_after_minutes": user_input["idle_off_after_minutes"],
                        "idle_setback_offset": user_input["idle_setback_offset"],
                        "demand_control_enabled": user_input["demand_control_enabled"],
                        "demand_select_entities": user_input["demand_select_entities"],
                        "demand_min": user_input["demand_min"],
                        "demand_max": user_input["demand_max"],
                        "demand_hysteresis": user_input["demand_hysteresis"],
                        "demand_min_hold_minutes": user_input["demand_min_hold_minutes"],
                        "demand_down_hold_minutes": user_input["demand_down_hold_minutes"],
                        "pv_boost_enabled": user_input["pv_boost_enabled"],
                        "pv_surplus_sensor": user_input.get("pv_surplus_sensor", ""),
                        "pv_surplus_min_w": user_input["pv_surplus_min_w"],
                        "pv_surplus_min_duration_minutes": user_input["pv_surplus_min_duration_minutes"],
                        "pv_battery_soc_sensor": user_input.get("pv_battery_soc_sensor", ""),
                        "pv_battery_soc_min": user_input["pv_battery_soc_min"],
                        "pv_boost_cool_percent": user_input["pv_boost_cool_percent"],
                        "pv_boost_heat_percent": user_input["pv_boost_heat_percent"],
                        "ac_setpoint_strategy": user_input["ac_setpoint_strategy"],
                        "ac_cool_offset_max": user_input["ac_cool_offset_max"],
                        "ac_heat_offset_max": user_input["ac_heat_offset_max"],
                    }
                )
            return self.async_create_entry(title="", data={})

        settings = store.get_settings() if store is not None else {}
        current_action = settings.get("vacation_action", DEFAULT_VACATION_ACTION)
        current_frost = settings.get("vacation_frost_temp", DEFAULT_VACATION_FROST_TEMP)
        current_idle_off = settings.get("idle_off_after_minutes", DEFAULT_IDLE_OFF_AFTER_MINUTES)
        current_setback_offset = settings.get("idle_setback_offset", DEFAULT_IDLE_SETBACK_OFFSET)
        current_demand_enabled = settings.get("demand_control_enabled", DEFAULT_DEMAND_CONTROL_ENABLED)
        current_demand_selects = settings.get("demand_select_entities", [])
        current_demand_min = settings.get("demand_min", DEFAULT_DEMAND_MIN)
        current_demand_max = settings.get("demand_max", DEFAULT_DEMAND_MAX)
        current_demand_hyst = settings.get("demand_hysteresis", DEFAULT_DEMAND_HYSTERESIS)
        current_demand_hold = settings.get("demand_min_hold_minutes", DEFAULT_DEMAND_MIN_HOLD_MINUTES)
        current_demand_down_hold = settings.get("demand_down_hold_minutes", DEFAULT_DEMAND_DOWN_HOLD_MINUTES)
        current_pv_boost_enabled = settings.get("pv_boost_enabled", DEFAULT_PV_BOOST_ENABLED)
        current_pv_surplus_sensor = settings.get("pv_surplus_sensor", "")
        current_pv_surplus_min_w = settings.get("pv_surplus_min_w", DEFAULT_PV_SURPLUS_MIN_W)
        current_pv_surplus_min_duration = settings.get(
            "pv_surplus_min_duration_minutes", DEFAULT_PV_SURPLUS_MIN_DURATION_MINUTES
        )
        current_pv_soc_sensor = settings.get("pv_battery_soc_sensor", "")
        current_pv_soc_min = settings.get("pv_battery_soc_min", DEFAULT_PV_BATTERY_SOC_MIN)
        current_pv_boost_cool = settings.get("pv_boost_cool_percent", DEFAULT_PV_BOOST_COOL_PERCENT)
        current_pv_boost_heat = settings.get("pv_boost_heat_percent", DEFAULT_PV_BOOST_HEAT_PERCENT)
        current_sp_strategy = settings.get("ac_setpoint_strategy", DEFAULT_AC_SETPOINT_STRATEGY)
        current_cool_offset = settings.get("ac_cool_offset_max", DEFAULT_AC_COOL_OFFSET_MAX)
        current_heat_offset = settings.get("ac_heat_offset_max", DEFAULT_AC_HEAT_OFFSET_MAX)

        offset_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.5,
                max=6.0,
                step=0.5,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        )

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
                vol.Required("idle_setback_offset", default=current_setback_offset): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=10.0,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required("demand_control_enabled", default=current_demand_enabled): selector.BooleanSelector(),
                vol.Optional("demand_select_entities", default=current_demand_selects): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="select", multiple=True)
                ),
                vol.Required("demand_min", default=current_demand_min): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=100, step=5, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required("demand_max", default=current_demand_max): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=100, step=5, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required("demand_hysteresis", default=current_demand_hyst): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=50, step=5, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required("demand_min_hold_minutes", default=current_demand_hold): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=60, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required("demand_down_hold_minutes", default=current_demand_down_hold): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=60, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required("pv_boost_enabled", default=current_pv_boost_enabled): selector.BooleanSelector(),
                vol.Optional("pv_surplus_sensor", default=current_pv_surplus_sensor): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required("pv_surplus_min_w", default=current_pv_surplus_min_w): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=20000, step=100, unit_of_measurement="W", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    "pv_surplus_min_duration_minutes", default=current_pv_surplus_min_duration
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=240, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional("pv_battery_soc_sensor", default=current_pv_soc_sensor): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required("pv_battery_soc_min", default=current_pv_soc_min): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=100, step=5, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required("pv_boost_cool_percent", default=current_pv_boost_cool): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=50, step=5, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required("pv_boost_heat_percent", default=current_pv_boost_heat): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=50, step=5, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required("ac_setpoint_strategy", default=current_sp_strategy): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(AC_SETPOINT_STRATEGIES),
                        translation_key="ac_setpoint_strategy",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("ac_cool_offset_max", default=current_cool_offset): offset_selector,
                vol.Required("ac_heat_offset_max", default=current_heat_offset): offset_selector,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
