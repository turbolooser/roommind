"""Direct valve control: hold a TRV valve at a set opening through number entities (#413).

TRVs like the SONOFF TRVZB expose an opening degree (how far the valve opens when the TRV
wants heat) and a closing degree (how far it closes when it does not). Opening X with
closing 100 - X pins the valve at X % whatever the TRV's own controller decides. Both at
their maximum is the device default, a normal TRV.

The SONOFF TRV-ZBT names the second value the opening while idle (#482): X and X pin the
valve, 100 and 0 hand it back as a normal TRV.

Fork: the TRV-ZBT only moves its motor when its own thermostat changes state (idle <->
heat); a new opening written in either state is ignored (hand test 17.11.2026). With
``kick`` the valve gets the "kick" of the vtherm_quirks quirk ``sonoff_trv_zbt``
(bontiv/vtherm_quirks a64b9330): idle = opening - 1, then a fake cold and hot room
temperature on ``external_temperature_input`` for a few seconds each, then the saved value.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import NamedTuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..const import VALVE_DEADBAND_PCT, VALVE_DWELL_SECONDS, make_roommind_context
from ..utils.device_utils import ValveEntities
from ..utils.temp_utils import celsius_to_ha_temp

_LOGGER = logging.getLogger(__name__)


class _Held(NamedTuple):
    at: float  # monotonic
    pct: int
    target: float | None
    opening_eid: str
    closing_eid: str
    idle_opening: bool = False

    @property
    def valve(self) -> ValveEntities:
        return ValveEntities(self.opening_eid, self.closing_eid, self.idle_opening)


# climate entity -> last position that reached the device
_valve_sent: dict[str, _Held] = {}
# climate entity -> closing mode its degrees were checked in since the start without RoomMind holding them
_checked: dict[str, bool] = {}
# set on unload: a cycle still running must not pin a valve again
_stopped = False

# Kick (fork, quirk sonoff_trv_zbt): options at the quirk's defaults, hot_step on
KICK_DELTA = 2.0  # K
KICK_PULSE_SECONDS = 5.0
KICK_SETTLE_SECONDS = 2.0  # the cycle's setpoint/mode calls land first
KICK_WAIT_HEAT_SECONDS = 15.0  # leaving off: the kick waits for the TRV state (quirk _wait_heat)
KICK_EXTERNAL_RANGE = (0.0, 99.9)
KICK_REMOTE_OPTION = "remote_temperature"
KICK_LOCAL_OPTION = "local_temperature"
# climate entity -> running kick task / opening of the last kick / a kick asked during one
_kick_tasks: dict[str, asyncio.Task] = {}
_kick_opening: dict[str, int] = {}
_kick_pending: set[str] = set()


def _now() -> float:
    return time.monotonic()


def held_opening(climate_eid: str) -> float | None:
    """Opening (0-1) RoomMind holds the valve at, None when it does not hold it."""
    held = _valve_sent.get(climate_eid)
    return held.pct / 100.0 if held is not None else None


def clear_valve_cache() -> None:
    """Forget sent positions (tests, integration setup)."""
    global _stopped  # noqa: PLW0603
    _valve_sent.clear()
    _checked.clear()
    _stopped = False
    for task in _kick_tasks.values():
        task.cancel()
    _kick_tasks.clear()
    _kick_opening.clear()
    _kick_pending.clear()


def _number_range(hass: HomeAssistant, entity_id: str) -> tuple[float, float, float] | None:
    """(min, max, step) of a number entity, None while it has no usable state."""
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    attrs = state.attributes
    try:
        lo = float(attrs.get("min", 0))
        hi = float(attrs.get("max", 100))
        step = float(attrs.get("step", 1) or 1)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return None
    return lo, hi, step


def _scaled(pct: int, lo: float, hi: float, step: float) -> float:
    """Percent of the entity's range, on its step (an entity may run 0-99)."""
    value = lo + (hi - lo) * pct / 100.0
    value = lo + round((value - lo) / step) * step
    return round(min(hi, max(lo, value)), 3)


def _current(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    try:
        return float(state.state) if state is not None else None
    except (TypeError, ValueError):
        return None


async def _async_set_number(
    hass: HomeAssistant, entity_id: str, pct: int, area_id: str, *, force: bool = False
) -> bool | None:
    """Set a number entity to ``pct`` % of its range.

    True when sent, False when it already holds the value, None when it has no usable
    state or the call failed. ``force`` sends even if the state shows the value: right
    after a send the state may not have caught up with the device yet.
    """
    limits = _number_range(hass, entity_id)
    if limits is None:
        return None
    value = _scaled(pct, *limits)
    current = _current(hass, entity_id)
    if not force and current is not None and abs(current - value) < limits[2] / 2:
        return False
    try:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
            context=make_roommind_context(),
        )
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Area '%s': number.set_value(%s) failed on '%s'", area_id, value, entity_id, exc_info=True)
        return None
    return True


async def async_set_valve(
    hass: HomeAssistant,
    climate_eid: str,
    opening_eid: str,
    closing_eid: str,
    opening_pct: float,
    *,
    area_id: str,
    target: float | None = None,
    urgent: bool = False,
    idle_opening: bool = False,
    kick: bool = False,
) -> None:
    """Hold the valve at ``opening_pct`` (0-100).

    A position that reached the device stays for ``VALVE_DWELL_SECONDS`` unless the room
    target (``target``) moved or the caller marks the change ``urgent``, and changes below
    ``VALVE_DEADBAND_PCT`` never go out. Every move costs motor noise and battery, while
    the radiator takes minutes to follow anyway; a 0.2 K sensor step alone moves the
    demand by 20 %. ``idle_opening``: the second entity is the opening while idle (#482).
    ``kick`` (fork, TRV-ZBT): idle = opening - 1 and a kick after every new opening.
    """
    if _stopped:
        return
    pct = int(round(min(100.0, max(0.0, opening_pct))))
    held = _valve_sent.get(climate_eid)
    if held is not None and (held.opening_eid, held.closing_eid, held.idle_opening) == (
        opening_eid,
        closing_eid,
        idle_opening,
    ):
        target_moved = target is not None and (held.target is None or abs(target - held.target) > 0.05)
        if abs(pct - held.pct) < VALVE_DEADBAND_PCT or (
            not urgent and not target_moved and _now() - held.at < VALVE_DWELL_SECONDS
        ):
            if target_moved:
                # The position stays, the target it is held for does not (hand_back sends it)
                _valve_sent[climate_eid] = held._replace(target=target)
            return
    # Whatever reaches the device from here on has to be released again
    _checked.pop(climate_eid, None)
    if kick and idle_opening:
        idle = max(0, pct - 1)
    else:
        idle = pct if idle_opening else 100 - pct
    results = [
        await _async_set_number(hass, opening_eid, pct, area_id),
        await _async_set_number(hass, closing_eid, idle, area_id),
    ]
    if None in results:
        # Try again next cycle; a half-applied position is not remembered as held
        _valve_sent.pop(climate_eid, None)
        return
    _valve_sent[climate_eid] = _Held(_now(), pct, target, opening_eid, closing_eid, idle_opening)
    if kick and idle_opening:
        request_kick(hass, climate_eid, pct, area_id)


async def async_release_valve(
    hass: HomeAssistant,
    climate_eid: str,
    opening_eid: str,
    closing_eid: str,
    *,
    area_id: str,
    hand_back: bool = False,
    idle_opening: bool = False,
    kick: bool = False,
) -> None:
    """Hand the valve back to the TRV: both degrees to their maximum, the device default.

    With ``idle_opening`` (#482) the second entity goes to 0 instead: closed while idle.

    A valve RoomMind holds is always sent (its state may still show the old degrees or
    lag behind the last send) and stays on record until the entities answered. One it
    does not hold is checked once after the start (a restart forgets what was held), so
    degrees set by hand while RoomMind does not control the TRV stay. ``hand_back``
    (RoomMind lets go for good: climate control off, room removed, unload) also sets the
    TRV to the room target it was pinned for; its proportional setpoint would otherwise
    heat the room flat out once the valve is free.
    ``kick`` (fork, TRV-ZBT): the new degrees are kicked in too, unless the TRV is off.
    """
    held = _valve_sent.get(climate_eid)
    # Checked in the other closing mode does not count: its hand-back would open a TRV-ZBT while idle
    if held is None and _checked.get(climate_eid) == idle_opening:
        return
    force = held is not None
    results = [
        await _async_set_number(hass, opening_eid, 100, area_id, force=force),
        await _async_set_number(hass, closing_eid, 0 if idle_opening else 100, area_id, force=force),
    ]
    if None in results:
        return
    _valve_sent.pop(climate_eid, None)
    _checked[climate_eid] = idle_opening
    if kick and idle_opening and True in results:
        request_kick(hass, climate_eid, 100, area_id, force=True)
    if hand_back and held is not None and held.target is not None:
        try:
            await hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": climate_eid, "temperature": celsius_to_ha_temp(hass, held.target)},
                blocking=True,
                context=make_roommind_context(),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Area '%s': handing the setpoint back to '%s' failed", area_id, climate_eid, exc_info=True)


async def async_release_orphaned_valves(hass: HomeAssistant, configured: dict[str, ValveEntities]) -> None:
    """Release valves RoomMind still holds but no longer has in its config.

    A cycle that started before a save or delete can pin a valve again after the save
    released it; from then on no config names its number entities. A changed closing
    mode alone is no orphan: the next cycle writes the valve in the new mode.
    """
    for climate_eid, held in list(_valve_sent.items()):
        valve = configured.get(climate_eid)
        if valve is None or valve[:2] != (held.opening_eid, held.closing_eid):
            await async_release_valve(
                hass,
                climate_eid,
                held.opening_eid,
                held.closing_eid,
                area_id="unconfigured",
                hand_back=True,
                idle_opening=held.idle_opening,
            )


async def async_release_all_valves(hass: HomeAssistant, configured: dict[str, ValveEntities]) -> None:
    """Unload: stop pinning and hand every configured or still held valve back."""
    global _stopped  # noqa: PLW0603
    _stopped = True
    valves = {eid: held.valve for eid, held in _valve_sent.items()} | configured
    for climate_eid, valve in valves.items():
        try:
            await async_release_valve(
                hass,
                climate_eid,
                valve.opening,
                valve.closing,
                area_id="unload",
                hand_back=True,
                idle_opening=valve.idle_opening,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Releasing the valve of '%s' on unload failed", climate_eid, exc_info=True)


# --- kick (fork): quirk sonoff_trv_zbt of bontiv/vtherm_quirks -----------------------------


def _device_entity(hass: HomeAssistant, climate_eid: str, domain: str, name: str) -> str | None:
    """Entity ``name`` (Z2M expose) of the climate's device, like the quirk's role discovery."""
    registry = er.async_get(hass)
    entry = registry.async_get(climate_eid)
    if entry is None or entry.device_id is None:
        return None
    for candidate in er.async_entries_for_device(registry, entry.device_id, include_disabled_entities=True):
        uid = candidate.unique_id or ""
        if candidate.domain == domain and (f"_{name}_" in uid or uid.endswith(f"_{name}")):
            return str(candidate.entity_id)
    return None


def request_kick(hass: HomeAssistant, climate_eid: str, opening: int, area_id: str, *, force: bool = False) -> None:
    """Ask for a kick. The same opening is not kicked twice; asks during a kick make one pending kick."""
    if not force and _kick_opening.get(climate_eid) == opening:
        return
    _kick_opening[climate_eid] = opening
    task = _kick_tasks.get(climate_eid)
    if task is not None and not task.done():
        _kick_pending.add(climate_eid)
        return
    _kick_tasks[climate_eid] = hass.async_create_background_task(
        _async_kick_loop(hass, climate_eid, area_id), f"roommind valve kick {climate_eid}"
    )


async def async_cancel_kick(climate_eid: str) -> None:
    """Cancel the kick and the pending one, return once the temperature is restored."""
    _kick_pending.discard(climate_eid)
    _kick_opening.pop(climate_eid, None)
    task = _kick_tasks.pop(climate_eid, None)
    if task is not None and not task.done():
        task.cancel()
        await asyncio.wait([task])


async def _async_kick_loop(hass: HomeAssistant, climate_eid: str, area_id: str) -> None:
    while True:
        _kick_pending.discard(climate_eid)
        await asyncio.sleep(KICK_SETTLE_SECONDS)
        await _async_kick_once(hass, climate_eid, area_id)
        if climate_eid not in _kick_pending:
            return


async def _async_write(hass: HomeAssistant, domain: str, service: str, data: dict, area_id: str) -> bool:
    try:
        await hass.services.async_call(domain, service, data, blocking=True, context=make_roommind_context())
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Area '%s': valve kick %s.%s(%s) failed", area_id, domain, service, data, exc_info=True)
        return False
    return True


async def _async_kick_once(hass: HomeAssistant, climate_eid: str, area_id: str) -> None:
    """One kick: a fake cold room, then a fake warm one, so the TRV changes state and moves.

    The quirk's cold pulse alone (hot_step off) moves a TRV that idles. RoomMind holds the
    valve with a setpoint above the room, so the TRV already heats: the hot step (quirk
    option ``hot_step``) makes it idle, the restored room makes it heat again.
    """
    waited = 0.0
    state = hass.states.get(climate_eid)
    while state is not None and state.state == "off" and waited < KICK_WAIT_HEAT_SECONDS:
        await asyncio.sleep(1.0)
        waited += 1.0
        state = hass.states.get(climate_eid)
    try:
        setpoint = float(state.attributes.get("temperature")) if state is not None else None
    except (TypeError, ValueError):
        setpoint = None
    external = _device_entity(hass, climate_eid, "number", "external_temperature_input")
    select = _device_entity(hass, climate_eid, "select", "temperature_sensor_select")
    if (
        state is None
        or state.state in ("off", "unavailable", "unknown")
        or setpoint is None
        or external is None
        or select is None
    ):
        _LOGGER.debug(
            "Area '%s': kick of '%s' aborted (state %s, setpoint %s, external %s, select %s)",
            area_id,
            climate_eid,
            None if state is None else state.state,
            setpoint,
            external,
            select,
        )
        _kick_opening.pop(climate_eid, None)
        return
    select_state = hass.states.get(select)
    was_external = select_state is not None and select_state.state == KICK_REMOTE_OPTION
    saved = None
    if was_external:
        saved = _current(hass, external)
    lo, hi = KICK_EXTERNAL_RANGE
    cold = round(min(hi, max(lo, setpoint - KICK_DELTA)), 1)
    hot = round(min(hi, max(lo, setpoint + KICK_DELTA)), 1)
    written: float | None = None
    _LOGGER.debug("Area '%s': kick of '%s', setpoint %s", area_id, climate_eid, setpoint)
    # From the first write on the finally restores the temperature, whatever happens
    try:
        if await _async_write(hass, "number", "set_value", {"entity_id": external, "value": cold}, area_id):
            written = cold
        if not was_external:
            await _async_write(
                hass, "select", "select_option", {"entity_id": select, "option": KICK_REMOTE_OPTION}, area_id
            )
        await asyncio.sleep(KICK_PULSE_SECONDS)
        if await _async_write(hass, "number", "set_value", {"entity_id": external, "value": hot}, area_id):
            written = hot
        await asyncio.sleep(KICK_PULSE_SECONDS)
    finally:
        if not was_external:
            await _async_write(
                hass, "select", "select_option", {"entity_id": select, "option": KICK_LOCAL_OPTION}, area_id
            )
        elif saved is not None:
            current = _current(hass, external)
            # Someone else fed a newer room temperature meanwhile: that one stays
            if written is None or current is None or abs(current - written) < 0.05:
                await _async_write(hass, "number", "set_value", {"entity_id": external, "value": saved}, area_id)
