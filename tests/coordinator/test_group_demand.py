"""Tests for compressor-group demand control (_async_apply_group_demand)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import _create_coordinator

GID = "g1"
AC = "climate.ac1"
SEL = "select.ac1_demand"


def _group():
    return {
        "id": GID,
        "name": "G",
        "members": [AC],
        "min_run_minutes": 20,
        "min_off_minutes": 10,
        "master_entity": "",
        "conflict_resolution": "outdoor_temp",
        "action_script": "",
        "enforce_uniform_mode": True,
    }


def _rooms():
    return {"r1": {"climate_control_enabled": True, "devices": [{"entity_id": AC}]}}


def _room_states(mode="heating", delta=0.0):
    """delta = sign-normalised temp error fed to the trim band.

    Heating: target − current. current pinned at 20, target = 20 + delta.
    """
    return {
        "r1": {
            "commanded_mode": mode,
            "current_temp": 20.0,
            "target_temp": 20.0 + delta,
        }
    }


def _sel_state(val):
    s = MagicMock()
    s.state = str(val)
    return s


def _demand_calls(hass):
    return [c for c in hass.services.async_call.call_args_list if c[0][0] == "select" and c[0][1] == "select_option"]


def _setup(hass, mock_config_entry, sel_current="30"):
    c = _create_coordinator(hass, mock_config_entry)
    c._compressor_manager.load_groups([_group()])
    c.outdoor_temp_effective = 10.0
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=_sel_state(sel_current))
    return c


@pytest.mark.asyncio
async def test_disabled_by_default_no_select_calls(hass, mock_config_entry):
    c = _setup(hass, mock_config_entry)
    await c._async_apply_group_demand(_room_states(), _rooms(), {})
    assert not _demand_calls(hass)


@pytest.mark.asyncio
async def test_enabled_sets_demand_from_aggregate(hass, mock_config_entry):
    s = {"demand_control_enabled": True, "demand_select_entities": [SEL], "demand_min": 30, "demand_max": 95}
    c = _setup(hass, mock_config_entry)
    await c._async_apply_group_demand(_room_states(mode="heating", delta=2.0), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls
    assert calls[0][0][2]["option"] == "60"  # outdoor 10 → base 35; Σδ 2.0 → +25


@pytest.mark.asyncio
async def test_idle_group_sets_min(hass, mock_config_entry):
    s = {"demand_control_enabled": True, "demand_select_entities": [SEL], "demand_min": 30, "demand_max": 95}
    c = _setup(hass, mock_config_entry, sel_current="60")  # not already at min
    await c._async_apply_group_demand(_room_states(mode="idle"), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "30"


@pytest.mark.asyncio
async def test_redundant_skip_when_already_at_value(hass, mock_config_entry):
    s = {"demand_control_enabled": True, "demand_select_entities": [SEL], "demand_min": 30, "demand_max": 95}
    c = _create_coordinator(hass, mock_config_entry)
    c._compressor_manager.load_groups([_group()])
    c.outdoor_temp_effective = 10.0
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=_sel_state("60"))  # already at target
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), s)
    assert not _demand_calls(hass)


@pytest.mark.asyncio
async def test_hysteresis_holds_small_change_vs_device(hass, mock_config_entry):
    """Device already within hysteresis of target → no write (anti-thrash)."""
    s = {
        "demand_control_enabled": True,
        "demand_select_entities": [SEL],
        "demand_min": 30,
        "demand_max": 95,
        "demand_hysteresis": 10,
        "demand_min_hold_minutes": 0,
    }
    c = _setup(hass, mock_config_entry, sel_current="65")  # device at 65
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), s)  # target 60, |60-65|=5 < 10
    assert not _demand_calls(hass)


@pytest.mark.asyncio
async def test_device_drift_is_corrected(hass, mock_config_entry):
    """Regression: pure device drift is corrected *immediately*.

    RoomMind last applied 35 (unchanged target); the Faikin drifted to 50
    on its own. Old intent-vs-intent gate froze forever. min_hold must NOT
    delay this — re-asserting an unchanged target is not a short-cycle —
    so it corrects even with a large min_hold window still open.
    """
    s = {
        "demand_control_enabled": True,
        "demand_select_entities": [SEL],
        "demand_min": 30,
        "demand_max": 95,
        "demand_hysteresis": 10,
        "demand_min_hold_minutes": 10,  # wide open, must be bypassed
    }
    c = _setup(hass, mock_config_entry, sel_current="50")  # drifted
    c._group_demand_state[GID] = (35, time.monotonic())  # last applied 35, just now
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)  # target 35
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"


@pytest.mark.asyncio
async def test_min_hold_blocks_genuine_change_then_releases(hass, mock_config_entry):
    """A *genuine* demand change too soon → held by min_hold, then released."""
    s = {
        "demand_control_enabled": True,
        "demand_select_entities": [SEL],
        "demand_min": 30,
        "demand_max": 95,
        "demand_hysteresis": 10,
        "demand_min_hold_minutes": 10,
        "demand_down_hold_minutes": 0,  # isolate min_hold from the slew gate
    }
    c = _setup(hass, mock_config_entry, sel_current="50")  # device at 50
    c._group_demand_state[GID] = (50, time.monotonic())  # last applied 50, just now
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)  # target 35 ≠ 50
    assert not _demand_calls(hass)  # genuine change, min_hold not elapsed
    # min-hold elapsed → the new demand level is released
    c._group_demand_state[GID] = (50, time.monotonic() - 11 * 60)
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"


# --- asymmetric slew (anti ping-pong) ---------------------------------------

_SLEW = {
    "demand_control_enabled": True,
    "demand_select_entities": [SEL],
    "demand_min": 30,
    "demand_max": 95,
    "demand_hysteresis": 10,
    "demand_min_hold_minutes": 0,  # isolate the slew gate
    "demand_down_hold_minutes": 5,
}


@pytest.mark.asyncio
async def test_slew_rise_is_immediate(hass, mock_config_entry):
    """A demand *rise* is never delayed by the slew (cover heat need now)."""
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_demand_state[GID] = (30, time.monotonic())  # last applied low
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), _SLEW)  # → 60
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "60"
    assert c._demand_debug[GID]["slew"] == "none"


@pytest.mark.asyncio
async def test_slew_holds_governing_value_until_sustained(hass, mock_config_entry):
    """Step-down is withheld until the zones stay satisfied long enough.

    While held, the *governing* (previous, higher) value is what gets
    re-asserted — so a drifted device is pulled back up, not down.
    """
    c = _setup(hass, mock_config_entry, sel_current="30")  # device drifted low
    c._group_demand_state[GID] = (60, time.monotonic())  # last applied 60
    # Satisfied (Σδ 0 ≤ 0.3, no heating_power → mean_hp 0) but hold not elapsed.
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), _SLEW)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "60"  # held high, not 35
    assert c._demand_debug[GID]["slew"] == "down_hold"

    # Hold window elapsed → the lower value is released.
    hass.services.async_call.reset_mock()
    hass.states.get = MagicMock(return_value=_sel_state("60"))
    c._group_demand_state[GID] = (60, time.monotonic())
    c._group_demand_downhold[GID] = time.monotonic() - (5 * 60 + 1)
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), _SLEW)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"
    assert c._demand_debug[GID]["slew"] == "down_release"


@pytest.mark.asyncio
async def test_slew_down_wait_when_zones_not_satisfied(hass, mock_config_entry):
    """Zones still need work → cap stays up regardless of the hold timer."""
    c = _setup(hass, mock_config_entry, sel_current="30")  # drifted low
    c._group_demand_state[GID] = (60, time.monotonic())
    # Σδ 0.5 > 0.3 → not settled, even though raw target (43) < 60.
    await c._async_apply_group_demand(_room_states(delta=0.5), _rooms(), _SLEW)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "60"
    assert c._demand_debug[GID]["slew"] == "down_wait"
    assert GID not in c._group_demand_downhold  # timer reset while unsettled


@pytest.mark.asyncio
async def test_slew_release_ignores_bangbang_heating_power(hass, mock_config_entry):
    """Regression (live 2026-05-19): heating_power must NOT gate the step-down.

    heating_power = MPC power_fraction × 100 is bang-bang ≈100 whenever the
    zone heats at all, so an hp gate pinned the cap high until full idle.
    Σδ-sustained is the sole release gate; hp is telemetry only.
    """
    c = _setup(hass, mock_config_entry, sel_current="60")
    c._group_demand_state[GID] = (60, time.monotonic())
    c._group_demand_downhold[GID] = time.monotonic() - (5 * 60 + 1)  # hold elapsed
    # Zone satisfied (Σδ 0) but compressor pf saturated at 100.
    rs = {"r1": {"commanded_mode": "heating", "current_temp": 20.0, "target_temp": 20.0, "heating_power": 100}}
    await c._async_apply_group_demand(rs, _rooms(), _SLEW)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"
    assert c._demand_debug[GID]["slew"] == "down_release"
    assert c._demand_debug[GID]["mean_hp"] == 100.0  # logged, not gated


@pytest.mark.asyncio
async def test_slew_disabled_allows_immediate_down(hass, mock_config_entry):
    """demand_down_hold_minutes = 0 → legacy immediate step-down."""
    s = dict(_SLEW, demand_down_hold_minutes=0)
    c = _setup(hass, mock_config_entry, sel_current="60")
    c._group_demand_state[GID] = (60, time.monotonic())
    await c._async_apply_group_demand(_room_states(delta=0.0), _rooms(), s)  # → 35
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "35"
    assert c._demand_debug[GID]["slew"] == "none"


@pytest.mark.asyncio
async def test_flap_counter_tracks_applied_changes(hass, mock_config_entry):
    """The rolling 1 h flap count increments only on applied value changes."""
    s = dict(_SLEW, demand_down_hold_minutes=0)
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_demand_state[GID] = (30, time.monotonic())
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), s)  # 30→60
    assert c._demand_debug[GID]["flaps_1h"] == 1
    # Re-assert the same value (device already at 60) → no change counted.
    hass.states.get = MagicMock(return_value=_sel_state("60"))
    await c._async_apply_group_demand(_room_states(delta=2.0), _rooms(), s)
    assert c._demand_debug[GID]["flaps_1h"] == 1


# --- PV-surplus boost --------------------------------------------------------

PV_SENSOR = "sensor.pv_surplus"
SOC_SENSOR = "sensor.battery_soc"

_PV_BASE = {
    "demand_control_enabled": True,
    "demand_select_entities": [SEL],
    "demand_min": 30,
    "demand_max": 95,
    "demand_hysteresis": 10,
    "demand_min_hold_minutes": 0,
    "demand_down_hold_minutes": 0,
    "pv_boost_enabled": True,
    "pv_surplus_sensor": PV_SENSOR,
    "pv_surplus_min_w": 1500,
    "pv_surplus_min_duration_minutes": 30,
    "pv_battery_soc_sensor": SOC_SENSOR,
    "pv_battery_soc_min": 90,
    "pv_boost_cool_percent": 15,
    "pv_boost_heat_percent": 10,
}


def _state_router(states: dict[str, str | None]):
    """Build a hass.states.get side_effect that routes by entity_id."""

    def _get(eid: str):
        if eid not in states:
            return None
        val = states[eid]
        if val is None:
            return None
        return _sel_state(val)

    return _get


def _cool_room_states(delta_pos: float = 0.0):
    """Cooling-mode room_states: positive ``delta_pos`` = room above target.

    The coordinator sign-normalises cooling errors as ``cur - tgt``, so
    setting ``current=20, target=20 - delta_pos`` lands the same positive
    Σδ in the trim band that a heating room reaches with ``tgt > cur``.
    Lets the boost tests exercise the cooling branch without inverting
    the trim semantics.
    """
    return {
        "r1": {
            "commanded_mode": "cooling",
            "current_temp": 20.0,
            "target_temp": 20.0 - delta_pos,
        }
    }


# PV boost is heating-only now (cooling uses the linear room-overshoot model
# and ignores it), so the PV-gate tests exercise the heating branch. Heat curve
# at the default outdoor 10 °C → base 35; pv_boost_heat_percent = 10.
@pytest.mark.asyncio
async def test_pv_boost_disabled_no_effect(hass, mock_config_entry):
    """pv_boost_enabled=False → byte-identical to the legacy controller."""
    s = dict(_PV_BASE, pv_boost_enabled=False)
    c = _setup(hass, mock_config_entry, sel_current="30")
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "100"}))
    await c._async_apply_group_demand(_room_states(mode="heating", delta=1.0), _rooms(), s)
    # Σδ 1.0 → trim +15 → 35+15=50. No boost on top.
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "50"
    assert c._demand_debug[GID]["pv_boost"] == 0
    assert c._demand_debug[GID]["pv_reason"] == "disabled"


@pytest.mark.asyncio
async def test_pv_boost_warming_up_then_engages_heating(hass, mock_config_entry):
    """First cycle starts the timer (boost=0); after duration elapsed → heat_percent."""
    c = _setup(hass, mock_config_entry, sel_current="30")
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "100"}))
    # Cycle 1: conditions met but warming up → no boost yet.
    await c._async_apply_group_demand(_room_states(mode="heating", delta=0.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_boost"] == 0
    assert c._demand_debug[GID]["pv_reason"] == "warming_up"
    assert GID in c._group_pv_boost_since  # timer running

    # Force the timer to look elapsed → boost engages with heat_percent.
    c._group_pv_boost_since[GID] = time.monotonic() - (30 * 60 + 1)
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "100"}))
    await c._async_apply_group_demand(_room_states(mode="heating", delta=0.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_boost"] == 10
    assert c._demand_debug[GID]["pv_reason"] == "heat"
    # base 35 + boost 10 = 45.
    calls = _demand_calls(hass)
    assert calls and calls[-1][0][2]["option"] == "45"


@pytest.mark.asyncio
async def test_pv_boost_heat_amount_separate(hass, mock_config_entry):
    """Heating mode uses pv_boost_heat_percent (not cool_percent)."""
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_pv_boost_since[GID] = time.monotonic() - 3600  # already armed
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "100"}))
    await c._async_apply_group_demand(_room_states(mode="heating", delta=0.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_boost"] == 10  # heat percent
    assert c._demand_debug[GID]["pv_reason"] == "heat"


@pytest.mark.asyncio
async def test_pv_boost_surplus_drop_resets_immediately(hass, mock_config_entry):
    """Surplus below threshold → boost off *and* timer reset (no carry-over)."""
    c = _setup(hass, mock_config_entry, sel_current="50")
    c._group_pv_boost_since[GID] = time.monotonic() - 3600  # was armed long ago
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "50", PV_SENSOR: "200", SOC_SENSOR: "100"}))
    await c._async_apply_group_demand(_room_states(mode="heating", delta=0.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_boost"] == 0
    assert c._demand_debug[GID]["pv_reason"] == "surplus_low"
    assert GID not in c._group_pv_boost_since


@pytest.mark.asyncio
async def test_pv_boost_soc_gate_blocks(hass, mock_config_entry):
    """SoC below min while surplus is plenty → boost stays off."""
    c = _setup(hass, mock_config_entry, sel_current="30")
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "70"}))
    await c._async_apply_group_demand(_room_states(mode="heating", delta=0.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_boost"] == 0
    assert c._demand_debug[GID]["pv_reason"] == "soc_low"
    assert GID not in c._group_pv_boost_since


@pytest.mark.asyncio
async def test_pv_boost_no_soc_sensor_skips_soc_check(hass, mock_config_entry):
    """Empty SoC sensor → boost engages on surplus alone (no battery in system)."""
    s = dict(_PV_BASE, pv_battery_soc_sensor="")
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_pv_boost_since[GID] = time.monotonic() - 3600
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000"}))
    await c._async_apply_group_demand(_room_states(mode="heating", delta=0.0), _rooms(), s)
    assert c._demand_debug[GID]["pv_boost"] == 10
    assert c._demand_debug[GID]["pv_reason"] == "heat"


@pytest.mark.asyncio
async def test_pv_boost_idle_group_no_boost(hass, mock_config_entry):
    """No active zone → boost short-circuits to 0 (nothing to boost)."""
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_pv_boost_since[GID] = time.monotonic() - 3600
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "100"}))
    await c._async_apply_group_demand(_room_states(mode="idle"), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_boost"] == 0
    assert c._demand_debug[GID]["pv_reason"] == "no_active"
    assert GID not in c._group_pv_boost_since  # reset when idle


@pytest.mark.asyncio
async def test_pv_boost_invalid_sensor_state(hass, mock_config_entry):
    """Surplus sensor unavailable/non-numeric → boost off, no crash."""
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_pv_boost_since[GID] = time.monotonic() - 3600
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "unavailable", SOC_SENSOR: "100"}))
    await c._async_apply_group_demand(_room_states(mode="heating", delta=0.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_boost"] == 0
    assert c._demand_debug[GID]["pv_reason"] == "sensor_invalid"


@pytest.mark.asyncio
async def test_pv_boost_clamps_to_demand_max(hass, mock_config_entry):
    """Boost cannot lift the cap past demand_max (safety ceiling holds)."""
    s = dict(_PV_BASE, demand_max=70)
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_pv_boost_since[GID] = time.monotonic() - 3600
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "100"}))
    # heating: base 35 + trim +25 (Σ2.0) + boost +10 → raw 70 → clamp 70.
    await c._async_apply_group_demand(_room_states(mode="heating", delta=2.0), _rooms(), s)
    calls = _demand_calls(hass)
    assert calls and calls[0][0][2]["option"] == "70"
    assert c._demand_debug[GID]["pv_boost"] == 10


@pytest.mark.asyncio
async def test_cool_never_adds_additive_boost(hass, mock_config_entry):
    """Cooling uses the linear room-overshoot model → the *additive* PV boost
    never applies (it verpufft against the ceiling). PV surplus lifts the
    *ceiling* instead, so the shared gate timer stays armed while cooling.
    """
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_pv_boost_since[GID] = time.monotonic() - 3600  # armed from a prior cycle
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "100"}))
    await c._async_apply_group_demand(_cool_room_states(delta_pos=1.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_boost"] == 0  # no additive boost, ever, while cooling
    assert c._demand_debug[GID]["pv_reason"] == "cool_ceiling"
    assert GID in c._group_pv_boost_since  # ceiling path shares + keeps the timer
    # At mild outdoor 10° the cap (FLOOR 40 + SLOPE·1.0 = 65) sits below either
    # ceiling, so the lift to 100 doesn't change the sent value here.
    assert c._demand_debug[GID]["demand_max_eff"] == 100
    calls = _demand_calls(hass)
    assert calls and calls[-1][0][2]["option"] == "65"


@pytest.mark.asyncio
async def test_cool_ceiling_lifts_cap_to_100_in_heatwave(hass, mock_config_entry):
    """Heatwave + sustained surplus → ceiling lifts 95→100 and the cap follows."""
    c = _setup(hass, mock_config_entry, sel_current="30")
    c.outdoor_temp_effective = 34.0  # FLOOR 90
    c._group_pv_boost_since[GID] = time.monotonic() - 3600
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "100"}))
    # FLOOR 90 + SLOPE 25·1.0 = 115 → without lift clamp 95, with lift clamp 100.
    await c._async_apply_group_demand(_cool_room_states(delta_pos=1.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["demand_max_eff"] == 100
    assert c._demand_debug[GID]["pv_reason"] == "cool_ceiling"
    calls = _demand_calls(hass)
    assert calls and calls[-1][0][2]["option"] == "100"


@pytest.mark.asyncio
async def test_cool_ceiling_not_lifted_without_surplus(hass, mock_config_entry):
    """No surplus → ceiling stays at demand_max (95); cap clamps to 95."""
    c = _setup(hass, mock_config_entry, sel_current="30")
    c.outdoor_temp_effective = 34.0
    c._group_pv_boost_since[GID] = time.monotonic() - 3600
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "200", SOC_SENSOR: "100"}))
    await c._async_apply_group_demand(_cool_room_states(delta_pos=1.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["demand_max_eff"] == 95
    assert c._demand_debug[GID]["pv_reason"] == "surplus_low"
    assert GID not in c._group_pv_boost_since
    calls = _demand_calls(hass)
    assert calls and calls[-1][0][2]["option"] == "95"


@pytest.mark.asyncio
async def test_cool_ceiling_ignores_soc(hass, mock_config_entry):
    """The cool ceiling has NO SoC gate: a sustained surplus already implies a
    full battery, so even a low SoC (that would block the heat boost) lifts it.
    """
    c = _setup(hass, mock_config_entry, sel_current="30")
    c.outdoor_temp_effective = 34.0
    c._group_pv_boost_since[GID] = time.monotonic() - 3600
    # SoC 40: far below the heat gate (90) — cool ceiling lifts anyway.
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "40"}))
    await c._async_apply_group_demand(_cool_room_states(delta_pos=1.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_reason"] == "cool_ceiling"
    assert c._demand_debug[GID]["demand_max_eff"] == 100
    calls = _demand_calls(hass)
    assert calls and calls[-1][0][2]["option"] == "100"


@pytest.mark.asyncio
async def test_heat_boost_still_soc_gated(hass, mock_config_entry):
    """Regression: dropping the cool SoC gate must not weaken the heat gate —
    heating still blocks below pv_battery_soc_min (90).
    """
    c = _setup(hass, mock_config_entry, sel_current="30")
    c._group_pv_boost_since[GID] = time.monotonic() - 3600
    hass.states.get = MagicMock(side_effect=_state_router({SEL: "30", PV_SENSOR: "5000", SOC_SENSOR: "70"}))
    await c._async_apply_group_demand(_room_states(mode="heating", delta=0.0), _rooms(), _PV_BASE)
    assert c._demand_debug[GID]["pv_boost"] == 0
    assert c._demand_debug[GID]["pv_reason"] == "soc_low"
    assert GID not in c._group_pv_boost_since
