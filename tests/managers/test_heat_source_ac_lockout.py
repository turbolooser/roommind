"""Locking an AC out of heating via heat_source_ac_min_outdoor.

Fork change: upstream caps the field at 5 °C, where it means "a heat pump below
this is too inefficient to bother". Everything else in the orchestrator is a
*preference* — outdoor_threshold and primary_delta only shift which source is
favoured — so this bound is the only hard "do not heat with this AC" switch
there is. Raising the cap to 30 °C lets a value above any realistic heating
weather keep a heat-capable AC out of the plan entirely, which is what you want
when a room's AC hangs in the wrong place or should simply never heat.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import voluptuous as vol

from custom_components.roommind.const import MODE_HEATING
from custom_components.roommind.managers.heat_source_orchestrator import evaluate_heat_sources
from custom_components.roommind.websocket_api import websocket_save_room


def _hass(ac_modes=("heat", "cool", "off")) -> MagicMock:
    hass = MagicMock()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": list(ac_modes)}
    hass.states.get = MagicMock(return_value=state)
    return hass


def _room(ac_min_outdoor: float) -> dict:
    return {
        "devices": [
            {"entity_id": "climate.trv1", "type": "trv", "role": "auto"},
            {"entity_id": "climate.ac1", "type": "ac", "role": "auto"},
        ],
        "heat_source_orchestration": True,
        "heat_source_primary_delta": 5.0,
        "heat_source_outdoor_threshold": 25.0,
        "heat_source_ac_min_outdoor": ac_min_outdoor,
    }


def _plan(ac_min_outdoor: float, outdoor: float | None, delta_t: float, prev: str = "none"):
    return evaluate_heat_sources(
        room_config=_room(ac_min_outdoor),
        mode=MODE_HEATING,
        power_fraction=1.0,
        current_temp=20.0 - delta_t,
        target_temp=20.0,
        outdoor_temp=outdoor,
        previous_active_sources=prev,
        hass=_hass(),
    )


def _ac_active(plan) -> bool:
    return any(c.entity_id == "climate.ac1" and c.active for c in plan.commands)


def _trv_active(plan) -> bool:
    return any(c.entity_id == "climate.trv1" and c.active for c in plan.commands)


# ---------------------------------------------------------------------------
# the raised bound actually locks the AC out
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("outdoor", [-10.0, 0.0, 8.0, 15.0, 19.0])
@pytest.mark.parametrize("delta_t", [0.5, 3.0, 12.0])
def test_ac_never_heats_with_high_min_outdoor(outdoor, delta_t):
    """At 20 °C the AC stays out across every realistic heating situation.

    delta_t 12 matters: that is past the "both sources" threshold, where the AC
    would otherwise be pulled in regardless of the weather preference.
    """
    plan = _plan(20.0, outdoor, delta_t)
    assert not _ac_active(plan), f"AC heated at outdoor={outdoor}, delta_t={delta_t}"
    assert _trv_active(plan), "TRV must carry the heating alone"


def test_upstream_default_still_lets_the_ac_help():
    """Unchanged behaviour at the old bound — this is an opt-in, not a new default."""
    plan = _plan(-15.0, 8.0, 12.0)  # mild weather, large gap -> "both"
    assert _ac_active(plan)
    assert _trv_active(plan)


def test_lockout_holds_when_the_ac_was_previously_running():
    """The hysteresis path must not sneak a locked-out AC back in."""
    plan = _plan(20.0, 8.0, 6.0, prev="secondary")
    assert not _ac_active(plan)
    plan = _plan(20.0, 8.0, 6.0, prev="both")
    assert not _ac_active(plan)


def test_reason_names_the_lockout():
    """The plan says why, so the diagnostic is readable."""
    plan = _plan(20.0, 8.0, 3.0)
    assert "AC disabled" in plan.reason


# ---------------------------------------------------------------------------
# schema bounds
# ---------------------------------------------------------------------------


def _save_schema():
    return websocket_save_room._ws_schema


@pytest.mark.parametrize("value", [-30.0, -15.0, 0.0, 5.0, 20.0, 30.0])
def test_schema_accepts_up_to_30(value):
    msg = {
        "id": 1,
        "type": "roommind/rooms/save",
        "area_id": "office",
        "heat_source_ac_min_outdoor": value,
    }
    assert _save_schema()(msg)["heat_source_ac_min_outdoor"] == value


@pytest.mark.parametrize("value", [30.1, 50.0, -31.0])
def test_schema_still_rejects_out_of_range(value):
    msg = {
        "id": 1,
        "type": "roommind/rooms/save",
        "area_id": "office",
        "heat_source_ac_min_outdoor": value,
    }
    with pytest.raises(vol.Invalid):
        _save_schema()(msg)


# ---------------------------------------------------------------------------
# the known gap, pinned so nobody mistakes it for a guarantee
# ---------------------------------------------------------------------------


def test_lockout_does_not_apply_without_outdoor_data():
    """Documented limit: the lockout needs a known outdoor temperature.

    ``ac_disabled`` is guarded by ``outdoor_temp is not None``, so with the
    sensor unavailable the orchestrator falls back to its delta heuristic and
    can still pick the AC. Deliberately left as upstream has it — changing it
    would alter behaviour for every orchestrated room, not just a locked-out AC.
    """
    plan = _plan(20.0, None, 1.0)
    assert _ac_active(plan), "sensor-outage fallback still reaches the AC (known gap)"
