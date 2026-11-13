"""Lead and holding-power trim of rooms with direct valve control."""

from __future__ import annotations

import math
from typing import NamedTuple

from ..const import (
    MODE_HEATING,
    MODE_IDLE,
    VALVE_DEFAULT_LEAD_MINUTES,
    VALVE_INTEGRAL_LEADS,
    VALVE_LEAD_LEARN_RATE,
    VALVE_LEAD_MAX_MINUTES,
    VALVE_LEAD_MIN_MINUTES,
    VALVE_LEAD_RELEARN_SHARE,
    VALVE_LEAD_RELEARN_TURNS,
    VALVE_LEAD_TURN_K,
    VALVE_OVERSHOOT_STOP_K,
    VALVE_TREND_WINDOW_MINUTES,
    VALVE_TRIM_LIMIT,
)

# A trim change below this does not make the state worth saving again
_TRIM_SAVE_STEP = 0.01


class ValveLead(NamedTuple):
    """What the valve controller of one room gets from the tracker this cycle."""

    minutes: float  # dead time + lag of radiator and air
    trend: float  # K/min of the room reading over the trend window
    trim: float  # learned correction of the model's holding share


class _Turn(NamedTuple):
    """A valve start (the room still falls) or stop (it still rises) waiting for the turn."""

    at: float
    rising: bool
    extreme: float
    extreme_at: float


class ValveLeadTracker:
    """Learns per room how late the radiator answers and how much power holds the target.

    A first-order room model has no state for the heat on its way through valve,
    radiator and air: the Veranda kept falling ~9 min after the valve opened and rose
    another 7-15 min after it closed (13.11.2026). The lead is learned from those turning
    points, the trim integrates what stays off the target, so a room that overshot gets
    less heat the next time.

    Lead, trim and the number of turning points learned are kept across restarts
    (``get_state``/``load_state``, saved with the thermal data): a Home Assistant
    restart must not cost hours of relearning. They are relearned only after a thermal
    reset, or when ``VALVE_LEAD_RELEARN_TURNS`` turning points in a row miss the learned
    lead by more than ``VALVE_LEAD_RELEARN_SHARE`` on the same side (radiator, sensor or
    room changed): their mean then replaces the lead at once.
    """

    def __init__(self) -> None:
        self._lead: dict[str, float] = {}
        self._trim: dict[str, float] = {}
        self._turns: dict[str, int] = {}
        self._misses: dict[str, list[float]] = {}
        self._samples: dict[str, list[tuple[float, float]]] = {}
        self._turn: dict[str, _Turn] = {}
        self._mode: dict[str, str] = {}
        self._at: dict[str, float] = {}
        self._saved_trim: dict[str, float] = {}
        self.dirty = False

    def get(self, area_id: str) -> ValveLead:
        samples = self._samples.get(area_id, [])
        trend = 0.0
        if len(samples) >= 2 and samples[-1][0] - samples[0][0] >= VALVE_TREND_WINDOW_MINUTES * 60 * 2 / 3:
            trend = (samples[-1][1] - samples[0][1]) / ((samples[-1][0] - samples[0][0]) / 60)
        return ValveLead(
            self._lead.get(area_id, VALVE_DEFAULT_LEAD_MINUTES),
            trend,
            self._trim.get(area_id, 0.0),
        )

    def update(
        self,
        area_id: str,
        now: float,
        current_temp: float,
        mode: str,
        target: float | None,
        *,
        band: float,
        raw_demand: float,
    ) -> None:
        """Feed one cycle: the reading, the mode chosen, the heat target, and the controller's
        band and unclamped demand (``MPCController.valve_feedback``)."""
        samples = self._samples.setdefault(area_id, [])
        samples.append((now, current_temp))
        while samples and now - samples[0][0] > VALVE_TREND_WINDOW_MINUTES * 60:
            samples.pop(0)
        self._learn_lead(area_id, now, current_temp, mode)
        last = self._at.get(area_id)
        self._at[area_id] = now
        if target is None or last is None or mode not in (MODE_HEATING, MODE_IDLE):
            return
        error = target - current_temp
        # Integrate while the valve holds the room, and right past the target where an
        # overshoot shows, not through a sunny afternoon; not into a saturated valve
        if mode != MODE_HEATING and abs(error) > VALVE_OVERSHOOT_STOP_K:
            return
        if (raw_demand >= 1.0 and error > 0) or (raw_demand <= 0.0 and error < 0):
            return
        lead = self._lead.get(area_id, VALVE_DEFAULT_LEAD_MINUTES)
        step = error / band * ((now - last) / 60) / (VALVE_INTEGRAL_LEADS * lead)
        trim = max(-VALVE_TRIM_LIMIT, min(VALVE_TRIM_LIMIT, self._trim.get(area_id, 0.0) + step))
        self._trim[area_id] = trim
        if abs(trim - self._saved_trim.get(area_id, 0.0)) >= _TRIM_SAVE_STEP:
            self._saved_trim[area_id] = trim
            self.dirty = True

    def _learn_lead(self, area_id: str, now: float, current_temp: float, mode: str) -> None:
        previous = self._mode.get(area_id)
        self._mode[area_id] = mode
        if previous is not None and previous != mode and MODE_HEATING in (previous, mode):
            # Start: the room still falls until it turns; stop: it still rises
            self._turn[area_id] = _Turn(now, mode != MODE_HEATING, current_temp, now)
            return
        turn = self._turn.get(area_id)
        if turn is None:
            return
        if (current_temp > turn.extreme) if turn.rising else (current_temp < turn.extreme):
            self._turn[area_id] = turn._replace(extreme=current_temp, extreme_at=now)
            return
        if abs(current_temp - turn.extreme) >= VALVE_LEAD_TURN_K:
            delay = (turn.extreme_at - turn.at) / 60
            if delay > 0:
                self._learn_delay(area_id, delay)
            self._turn.pop(area_id, None)
        elif now - turn.at > VALVE_LEAD_MAX_MINUTES * 60 * 4 / 3:
            self._turn.pop(area_id, None)

    def _learn_delay(self, area_id: str, delay: float) -> None:
        lead = self._lead.get(area_id, VALVE_DEFAULT_LEAD_MINUTES)
        misses = self._misses.setdefault(area_id, [])
        if abs(delay - lead) > VALVE_LEAD_RELEARN_SHARE * lead:
            if misses and (misses[-1] > lead) != (delay > lead):
                misses.clear()
            misses.append(delay)
        else:
            misses.clear()
        if len(misses) >= VALVE_LEAD_RELEARN_TURNS:
            # The room no longer answers as learned: start over from what it does now
            lead = sum(misses) / len(misses)
            misses.clear()
        else:
            lead += VALVE_LEAD_LEARN_RATE * (delay - lead)
        self._lead[area_id] = max(VALVE_LEAD_MIN_MINUTES, min(VALVE_LEAD_MAX_MINUTES, lead))
        self._turns[area_id] = self._turns.get(area_id, 0) + 1
        self.dirty = True

    def get_state(self) -> dict:
        """Persistable state: per room the lead (min), trim and turning points learned."""
        rooms = set(self._lead) | set(self._trim)
        return {
            area_id: {
                "lead": round(self._lead.get(area_id, VALVE_DEFAULT_LEAD_MINUTES), 2),
                "trim": round(self._trim.get(area_id, 0.0), 4),
                "turns": self._turns.get(area_id, 0),
            }
            for area_id in sorted(rooms)
        }

    def load_state(self, data: dict) -> None:
        """Restore persisted lead and trim, skipping malformed or out-of-range entries."""
        self.clear_all()
        for area_id, value in (data or {}).items():
            if not isinstance(value, dict):
                continue
            try:
                lead = float(value.get("lead", VALVE_DEFAULT_LEAD_MINUTES))
                trim = float(value.get("trim", 0.0))
                turns = int(value.get("turns", 0))
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(lead) and math.isfinite(trim)):
                continue
            if VALVE_LEAD_MIN_MINUTES <= lead <= VALVE_LEAD_MAX_MINUTES:
                self._lead[area_id] = lead
                self._turns[area_id] = max(0, turns)
            if abs(trim) <= VALVE_TRIM_LIMIT:
                self._trim[area_id] = self._saved_trim[area_id] = trim
        self.dirty = False

    def prune(self, known_area_ids: set[str]) -> None:
        """Drop rooms that are no longer configured."""
        stale = [area_id for area_id in set(self._lead) | set(self._trim) if area_id not in known_area_ids]
        for area_id in stale:
            self.remove_room(area_id)

    def remove_room(self, area_id: str) -> None:
        """Clean up state for a removed room."""
        had_state = area_id in self._lead or area_id in self._trim
        for state in self._states():
            state.pop(area_id, None)
        if had_state:
            self.dirty = True

    def clear_room(self, area_id: str) -> None:
        """Clear state for a room (thermal reset): it learns from the default again."""
        self.remove_room(area_id)

    def clear_all(self) -> None:
        """Clear state for all rooms."""
        had_state = bool(self._lead or self._trim)
        for state in self._states():
            state.clear()
        if had_state:
            self.dirty = True

    def _states(self) -> tuple[dict, ...]:
        return (
            self._lead,
            self._trim,
            self._turns,
            self._misses,
            self._samples,
            self._turn,
            self._mode,
            self._at,
            self._saved_trim,
        )
