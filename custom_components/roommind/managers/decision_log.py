"""Why-log (fork): one line per room whenever its mode, target or reason changes.

The coordinator hands over the facts of each cycle's decision; ``classify_reason``
turns them into a fixed reason key, ``DecisionLog`` keeps a line only when the
mode, the heat/cool target or one of the reasons differs from the room's last
line. Lines older than ``DECISION_LOG_DAYS`` fall out. The log lives in its own
HA ``Store`` (``roommind_decision_log``), so the main storage stays untouched.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..const import (
    CLIMATE_MODE_COOL_ONLY,
    CLIMATE_MODE_HEAT_ONLY,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    TARGET_REASON_AWAY,
    TARGET_REASON_OVERRIDE,
    TARGET_REASON_VACANT,
    TARGET_REASON_VACATION,
)

_LOGGER = logging.getLogger(__name__)

DECISION_LOG_DAYS = 14
DECISION_LOG_STORE_KEY = "roommind_decision_log"
DECISION_LOG_STORE_VERSION = 1
# Seconds a change waits before it is written; HA writes pending data on shutdown
DECISION_LOG_SAVE_DELAY = 300
# Safety cap: a room flapping every cycle still keeps the log small
DECISION_LOG_MAX_PER_ROOM = 2000
# Afterglow below this (model units) does not explain an idle room
RESIDUAL_HEAT_MIN = 0.05

# Mode reasons, in the order classify_reason checks them
REASON_CLIMATE_OFF = "climate_off"
REASON_WAITING_SENSOR = "waiting_sensor"
REASON_WINDOW_PENDING = "window_pending"
REASON_WINDOW_OPEN = "window_open"
REASON_OFF_OVERRIDE = "off_override"
REASON_OFF_VACATION = "off_vacation"
REASON_OFF_AWAY = "off_away"
REASON_OFF_SCHEDULE = "off_schedule"
REASON_COMPRESSOR_MIN_OFF = "compressor_min_off"
REASON_MANAGED = "managed"
REASON_PREHEAT = "preheat"
REASON_MIN_RUN = "min_run"
REASON_MPC_RUN = "mpc_run"
REASON_HYSTERESIS_RUN = "hysteresis_run"
REASON_COMPRESSOR_MIN_RUN = "compressor_min_run"
REASON_SETBACK = "setback"
REASON_HEAT_ONLY = "heat_only"
REASON_COOL_ONLY = "cool_only"
REASON_OUTDOOR_GATE = "outdoor_gate"
REASON_RESIDUAL_HEAT = "residual_heat"
REASON_MPC_IDLE = "mpc_idle"
REASON_IN_BAND = "in_band"

REASONS: tuple[str, ...] = (
    REASON_CLIMATE_OFF,
    REASON_WAITING_SENSOR,
    REASON_WINDOW_PENDING,
    REASON_WINDOW_OPEN,
    REASON_OFF_OVERRIDE,
    REASON_OFF_VACATION,
    REASON_OFF_AWAY,
    REASON_OFF_SCHEDULE,
    REASON_COMPRESSOR_MIN_OFF,
    REASON_MANAGED,
    REASON_PREHEAT,
    REASON_MIN_RUN,
    REASON_MPC_RUN,
    REASON_HYSTERESIS_RUN,
    REASON_COMPRESSOR_MIN_RUN,
    REASON_SETBACK,
    REASON_HEAT_ONLY,
    REASON_COOL_ONLY,
    REASON_OUTDOOR_GATE,
    REASON_RESIDUAL_HEAT,
    REASON_MPC_IDLE,
    REASON_IN_BAND,
)

# Target reasons: what set the heat/cool target
TARGET_SCHEDULE = "schedule"
TARGET_MOLD = "mold"
TARGET_PRICE = "price"
TARGET_REASONS: tuple[str, ...] = (
    TARGET_REASON_OVERRIDE,
    TARGET_REASON_VACATION,
    TARGET_REASON_AWAY,
    TARGET_REASON_VACANT,
    TARGET_SCHEDULE,
    TARGET_MOLD,
    TARGET_PRICE,
)

_OFF_BY_TARGET = {
    TARGET_REASON_OVERRIDE: REASON_OFF_OVERRIDE,
    TARGET_REASON_VACATION: REASON_OFF_VACATION,
    TARGET_REASON_AWAY: REASON_OFF_AWAY,
}


@dataclass(frozen=True)
class DecisionFacts:
    """What the coordinator knew when it settled a room's mode this cycle."""

    mode: str
    heat: float | None
    cool: float | None
    target_reason: str = ""
    current_temp: float | None = None
    outdoor_temp: float | None = None
    climate_mode: str = "auto"
    climate_active: bool = True
    has_external_sensor: bool = True
    waiting_for_temp: bool = False
    window_pending: bool = False
    window_open: bool = False
    open_windows: tuple[str, ...] = field(default_factory=tuple)
    force_off: bool = False
    compressor_blocked: bool = False
    compressor_hold: bool = False
    mpc: bool = False
    preheat: bool = False
    can_heat: bool = True
    can_cool: bool = True
    residual_heat: float = 0.0
    setback: bool = False
    mold_boost: float = 0.0
    price_shifted: bool = False


def classify_target(facts: DecisionFacts) -> str:
    """Key of what set the target: override/vacation/away/vacant, or schedule moved by mold or price."""
    if facts.target_reason:
        return facts.target_reason
    if facts.mold_boost > 0:
        return TARGET_MOLD
    if facts.price_shifted:
        return TARGET_PRICE
    return TARGET_SCHEDULE


def classify_reason(facts: DecisionFacts) -> str:
    """Key of why the room runs in its mode (first match wins)."""
    if not facts.climate_active:
        return REASON_CLIMATE_OFF
    if facts.waiting_for_temp:
        return REASON_WAITING_SENSOR
    if facts.window_pending:
        return REASON_WINDOW_PENDING
    if facts.window_open:
        return REASON_WINDOW_OPEN
    if facts.force_off:
        return _OFF_BY_TARGET.get(facts.target_reason, REASON_OFF_SCHEDULE)
    if facts.compressor_blocked:
        return REASON_COMPRESSOR_MIN_OFF
    if not facts.has_external_sensor:
        return REASON_MANAGED
    t = facts.current_temp
    if facts.mode in (MODE_HEATING, MODE_COOLING):
        if facts.preheat:
            return REASON_PREHEAT
        if t is not None and (
            (facts.mode == MODE_HEATING and facts.heat is not None and t >= facts.heat)
            or (facts.mode == MODE_COOLING and facts.cool is not None and t <= facts.cool)
        ):
            return REASON_MIN_RUN
        return REASON_MPC_RUN if facts.mpc else REASON_HYSTERESIS_RUN
    if facts.compressor_hold:
        return REASON_COMPRESSOR_MIN_RUN
    if facts.setback:
        return REASON_SETBACK
    too_cold = t is not None and facts.heat is not None and t < facts.heat
    too_warm = t is not None and facts.cool is not None and t > facts.cool
    if too_warm and facts.climate_mode == CLIMATE_MODE_HEAT_ONLY:
        return REASON_HEAT_ONLY
    if too_cold and facts.climate_mode == CLIMATE_MODE_COOL_ONLY:
        return REASON_COOL_ONLY
    if (too_cold and not facts.can_heat) or (too_warm and not facts.can_cool):
        return REASON_OUTDOOR_GATE
    if too_cold and facts.residual_heat >= RESIDUAL_HEAT_MIN:
        return REASON_RESIDUAL_HEAT
    return REASON_MPC_IDLE if facts.mpc else REASON_IN_BAND


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 1)


def _line_key(line: dict[str, Any]) -> tuple:
    """What makes two lines the same decision: mode, targets and both reasons."""
    return (line["mode"], line.get("heat"), line.get("cool"), line["reason"], line["target_reason"])


class DecisionLog:
    """Per-room ring buffer of decision changes, kept for ``DECISION_LOG_DAYS``."""

    def __init__(self, hass: Any = None, *, days: int = DECISION_LOG_DAYS) -> None:
        self._hass = hass
        self._max_age = days * 86400
        self._rooms: dict[str, deque[dict[str, Any]]] = {}
        self._store: Any = None
        self._loaded = False

    async def async_load(self) -> None:
        """Read the saved log once; without a usable store the log only lives in memory."""
        if self._loaded:
            return
        self._loaded = True
        if self._hass is None:
            return
        from homeassistant.helpers.storage import Store

        try:
            store = Store(self._hass, DECISION_LOG_STORE_VERSION, DECISION_LOG_STORE_KEY)
            data = await store.async_load()
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Why-log could not be read, starting empty", exc_info=True)
            data = None
            store = None
        self._store = store
        if isinstance(data, dict):
            self.load_state(data)

    def load_state(self, data: dict[str, Any]) -> None:
        rooms = data.get("rooms", {}) if isinstance(data, dict) else {}
        self._rooms = {}
        for area_id, lines in rooms.items():
            if not isinstance(lines, list):
                continue
            valid = [ln for ln in lines if isinstance(ln, dict) and isinstance(ln.get("ts"), (int, float))]
            valid.sort(key=lambda ln: ln["ts"])
            self._rooms[area_id] = deque(valid[-DECISION_LOG_MAX_PER_ROOM:], maxlen=DECISION_LOG_MAX_PER_ROOM)
        self.prune(time.time())

    def get_state(self) -> dict[str, Any]:
        return {"rooms": {area_id: list(lines) for area_id, lines in self._rooms.items() if lines}}

    def _schedule_save(self) -> None:
        if self._store is None:
            return
        try:
            self._store.async_delay_save(self.get_state, DECISION_LOG_SAVE_DELAY)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Why-log save could not be scheduled", exc_info=True)

    async def async_flush(self) -> None:
        """Write now (unload), instead of waiting for the delayed save."""
        if self._store is not None:
            await self._store.async_save(self.get_state())

    def record(self, area_id: str, facts: DecisionFacts, now: float | None = None) -> dict[str, Any] | None:
        """Add a line when the decision differs from the room's last one; returns the new line."""
        now = time.time() if now is None else now
        line: dict[str, Any] = {
            "ts": round(now, 1),
            "mode": facts.mode if facts.mode in (MODE_HEATING, MODE_COOLING) else MODE_IDLE,
            "reason": classify_reason(facts),
            "target_reason": classify_target(facts),
            "heat": _round(facts.heat),
            "cool": _round(facts.cool),
            "current": _round(facts.current_temp),
            "outdoor": _round(facts.outdoor_temp),
        }
        if line["reason"] in (REASON_WINDOW_OPEN, REASON_WINDOW_PENDING) and facts.open_windows:
            line["windows"] = list(facts.open_windows)
        lines = self._rooms.setdefault(area_id, deque(maxlen=DECISION_LOG_MAX_PER_ROOM))
        pruned = self._prune_room(lines, now)
        if lines and _line_key(lines[-1]) == _line_key(line):
            if pruned:
                self._schedule_save()
            return None
        lines.append(line)
        self._schedule_save()
        return line

    def _prune_room(self, lines: deque[dict[str, Any]], now: float) -> bool:
        """Drop lines past the retention.

        The newest line stays as the baseline for the change check, so an unchanged
        room does not log its old decision again; ``entries`` hides it all the same.
        """
        cutoff = now - self._max_age
        dropped = False
        while len(lines) > 1 and lines[0]["ts"] < cutoff:
            lines.popleft()
            dropped = True
        return dropped

    def prune(self, now: float) -> None:
        for lines in self._rooms.values():
            self._prune_room(lines, now)

    def forget(self, area_id: str) -> None:
        if self._rooms.pop(area_id, None) is not None:
            self._schedule_save()

    def entries(
        self,
        area_id: str | None = None,
        start_ts: float | None = None,
        end_ts: float | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Lines of one room (or all), newest first, within ``start_ts``..``end_ts``."""
        now = time.time()
        cutoff = now - self._max_age
        start = cutoff if start_ts is None else max(start_ts, cutoff)
        rooms = [area_id] if area_id is not None else list(self._rooms)
        out: list[dict[str, Any]] = []
        for aid in rooms:
            for ln in self._rooms.get(aid, ()):
                if ln["ts"] < start or (end_ts is not None and ln["ts"] > end_ts):
                    continue
                out.append({"area_id": aid, **ln})
        out.sort(key=lambda ln: ln["ts"], reverse=True)
        return out[:limit] if limit is not None else out
