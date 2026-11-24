"""A modulating valve leads the radiator's dead time and learns its holding power.

The Veranda (13.11.2026, Eco 18.0) swung 17.5-19.3 every ~1.5 h: the valve opened at
17.9 and the room kept falling for ~9 min, then the valve stayed wide open until the
reading reached the target and the room rose another 7-15 min.
"""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace

import pytest

from custom_components.roommind.const import (
    MIN_POWER_FRACTION,
    MODE_HEATING,
    MODE_IDLE,
    VALVE_DEADBAND_PCT,
    VALVE_DEFAULT_LEAD_MINUTES,
    VALVE_DWELL_SECONDS,
    VALVE_LEAD_MAX_MINUTES,
    VALVE_PROPORTIONAL_BAND_K,
    VALVE_TRIM_LIMIT,
)
from custom_components.roommind.control.mpc_controller import (
    decide_mpc_action,
    valve_band,
    valve_demand,
    valve_holding_share,
    valve_lead_temp,
)
from custom_components.roommind.control.thermal_model import RCModel
from custom_components.roommind.managers.valve_lead_tracker import ValveLead, ValveLeadTracker

TARGET = 18.0
OUTDOOR = 2.0
# What RoomMind had learned for the Veranda: a strong radiator, holding share overrated
# (~0.55 against the ~0.35 the valve positions of the night show)
VERANDA_MODEL = RCModel(C=1.0, U=0.101, Q_heat=2.94, Q_solar=0.0, Q_occupancy=0.0)


class _Veranda:
    """Room fitted to the night 12./13.11. (proxy reading against valve position, 1 min).

    Valve -> radiator after a 12 min dead time and a 3.7 min lag, 4.3 K/h at a fully
    open valve, the air relaxing towards cold walls at 10.5 °C. The sensor reports every
    5 min in 0.01 K steps, RoomMind runs every 30 s.
    """

    DEAD_STEPS = 24
    LAG_STEPS = 7.4
    GAIN = 0.0717 / 2  # K per 30 s at a fully open valve
    LOSS = 0.00323 / 2
    WALLS = 10.53

    def __init__(self, temp: float) -> None:
        self.air = temp
        self.heat = 0.0
        self.valve = [0.0] * (self.DEAD_STEPS + 1)

    def step(self, opening: float) -> None:
        self.valve.append(opening)
        self.heat += (self.valve[-1 - self.DEAD_STEPS] - self.heat) / self.LAG_STEPS
        self.air += self.GAIN * self.heat - self.LOSS * (self.air - self.WALLS)


def _run(hours: float, *, lead: bool, start: float = 18.4, full_below: bool = True) -> list[float]:
    """Closed loop through decide_mpc_action; returns the room temperature per 30 s.

    full_below passes the reading, trend and opening like the controller does (below the target on a
    flat or falling trend the valve opens a step per lead, 24.11.2026); False is the throttle before that."""
    room = _Veranda(start)
    tracker = ValveLeadTracker()
    mode = MODE_IDLE
    held: tuple[float, int] | None = None
    reading = start
    temps = []
    for k in range(int(hours * 120)):
        now = k * 30.0
        if k % 10 == 0:
            reading = round(room.air, 2)
        info = tracker.get("veranda", now) if lead else None
        lead_temp = reading if info is None else valve_lead_temp(reading, info.trend, info.minutes)
        mode, power = decide_mpc_action(
            # The optimizer's closed form: full power below the target, nothing above
            MODE_HEATING if reading < TARGET else MODE_IDLE,
            1.0 if reading < TARGET else 0.0,
            reading,
            [TARGET] * 12,
            [27.0] * 12,
            guard_blocks=6,
            slow_heat=False,
            previous_mode=mode,
            heat_in_min_run=False,
            cool_in_min_run=False,
            can_heat=True,
            can_cool=False,
            heat_hysteresis=0.1,
            idle_drift=lambda minutes, temp=reading: temp,
            continuation_power=lambda m, t: MIN_POWER_FRACTION,
            valve_demand=partial(
                valve_demand,
                VERANDA_MODEL,
                lead_temp,
                OUTDOOR,
                q_solar=0.0,
                q_occupancy=0.0,
                lead_minutes=0.0 if info is None else info.minutes,
                trim=0.0 if info is None else info.trim,
                reading=reading if info is not None and full_below else None,
                trend=info.trend if info is not None and full_below else None,
                open_minutes=info.open_minutes if info is not None and full_below else None,
                opening=info.opening if info is not None and full_below else None,
                stepped=info.stepped if info is not None and full_below else False,
            ),
            valve_lead_temp=None if info is None else lead_temp,
        )
        if info is not None:
            band = valve_band(VERANDA_MODEL, info.minutes)
            hold = valve_holding_share(VERANDA_MODEL, OUTDOOR, TARGET, q_solar=0.0, q_occupancy=0.0)
            raw = hold + info.trim + (TARGET - lead_temp) / band
            tracker.update(
                "veranda",
                now,
                reading,
                mode,
                TARGET,
                band=band,
                raw_demand=raw,
                opening=power if mode == MODE_HEATING else None,
            )
        # async_set_valve: dwell and deadband while running, released when idle
        if mode == MODE_IDLE:
            held = None
        else:
            pct = round(power * 100)
            if held is None or (abs(pct - held[1]) >= VALVE_DEADBAND_PCT and now - held[0] >= VALVE_DWELL_SECONDS):
                held = (now, pct)
        room.step(0.0 if held is None else held[1] / 100)
        temps.append(room.air)
    return temps


def test_reading_driven_valve_swings_like_the_veranda():
    temps = _run(24, lead=False)[6 * 120 :]
    assert max(temps) - TARGET > 0.6
    assert max(temps) - min(temps) > 1.0


@pytest.mark.parametrize("full_below", [True, False])
@pytest.mark.parametrize("start", [18.4, 17.5])
def test_lead_and_trim_hold_the_veranda_within_the_band(start, full_below):
    temps = _run(24, lead=True, start=start, full_below=full_below)[6 * 120 :]
    assert max(temps) - TARGET <= 0.3
    assert max(temps) - min(temps) <= 0.6


def test_valve_band_widens_with_power_and_lead():
    assert valve_band(VERANDA_MODEL, 0.0) == VALVE_PROPORTIONAL_BAND_K
    assert valve_band(RCModel(Q_heat=0.42), 15.0) == VALVE_PROPORTIONAL_BAND_K  # a radiator that barely keeps up
    assert valve_band(VERANDA_MODEL, 15.0) == pytest.approx(2.94 / 60 * 15 / 0.4)


def test_lead_temp_follows_a_clamped_trend():
    assert valve_lead_temp(18.0, 0.01, 15.0) == pytest.approx(18.15)
    assert valve_lead_temp(18.0, -1.0, 10.0) == pytest.approx(17.5)


def test_valve_demand_takes_the_trim_and_the_wider_band():
    plain = valve_demand(VERANDA_MODEL, 17.8, OUTDOOR, TARGET, q_solar=0.0, q_occupancy=0.0)
    led = valve_demand(VERANDA_MODEL, 17.8, OUTDOOR, TARGET, q_solar=0.0, q_occupancy=0.0, lead_minutes=15.0, trim=-0.2)
    hold = valve_holding_share(VERANDA_MODEL, OUTDOOR, TARGET, q_solar=0.0, q_occupancy=0.0)
    assert plain == pytest.approx(hold + 0.2)
    assert led == pytest.approx(hold - 0.2 + 0.2 / valve_band(VERANDA_MODEL, 15.0))
    assert valve_holding_share(RCModel(Q_heat=0.0), OUTDOOR, TARGET, q_solar=0.0, q_occupancy=0.0) == 0.0


def _decide(previous, temp, lead_temp, *, demand=0.3, optimizer=MODE_IDLE):
    return decide_mpc_action(
        optimizer,
        0.0,
        temp,
        [21.0] * 12,
        [24.0] * 12,
        guard_blocks=6,
        slow_heat=False,
        previous_mode=previous,
        heat_in_min_run=False,
        cool_in_min_run=False,
        can_heat=True,
        can_cool=True,
        heat_hysteresis=0.1,
        idle_drift=lambda minutes: temp,
        continuation_power=lambda mode, target: MIN_POWER_FRACTION,
        valve_demand=lambda target: demand,
        valve_lead_temp=lead_temp,
    )


def test_falling_room_starts_the_valve_one_lead_early():
    # The optimizer still sees 21.1 above the target
    assert _decide(MODE_IDLE, 21.1, 20.85) == (MODE_HEATING, 0.3)
    assert _decide(MODE_IDLE, 21.1, 20.85, demand=0.0) == (MODE_HEATING, MIN_POWER_FRACTION)
    assert _decide(MODE_IDLE, 21.1, 20.95) == (MODE_IDLE, 0.0)
    # Not that far above the target, whatever the trend says
    assert _decide(MODE_IDLE, 21.5, 20.0) == (MODE_IDLE, 0.0)


def test_rising_room_waits_although_the_reading_is_below_the_start():
    assert _decide(MODE_IDLE, 20.8, 21.0, optimizer=MODE_HEATING) == (MODE_IDLE, 0.0)


def test_running_valve_keeps_the_minimum_only_while_the_lead_is_below_the_target():
    assert _decide(MODE_HEATING, 20.9, 20.95, demand=0.0) == (MODE_HEATING, MIN_POWER_FRACTION)
    assert _decide(MODE_HEATING, 20.9, 21.1, demand=0.0) == (MODE_IDLE, 0.0)
    assert _decide(MODE_HEATING, 20.9, 21.1, demand=0.2) == (MODE_HEATING, 0.2)


def _feed(tracker, readings, modes, *, start=0.0, step=60.0, band=2.0, raw=0.4, target=18.0):
    for i, (temp, mode) in enumerate(zip(readings, modes, strict=True)):
        tracker.update("r", start + i * step, temp, mode, target, band=band, raw_demand=raw)


def test_tracker_defaults_until_it_learns():
    assert ValveLeadTracker().get("r") == ValveLead(VALVE_DEFAULT_LEAD_MINUTES, 0.0, 0.0)


def test_tracker_learns_the_lead_from_the_trough_after_a_start():
    tracker = ValveLeadTracker()
    # Start at minute 1, the room falls to its trough at minute 8, then turns
    readings = [17.9, 17.9, 17.85, 17.8, 17.75, 17.7, 17.65, 17.62, 17.6, 17.6, 17.65, 17.72]
    _feed(tracker, readings, [MODE_IDLE] + [MODE_HEATING] * 11)
    assert tracker.get("r").minutes == pytest.approx(
        VALVE_DEFAULT_LEAD_MINUTES + 0.3 * (7 - VALVE_DEFAULT_LEAD_MINUTES)
    )


def test_tracker_learns_the_lead_from_the_peak_after_a_stop():
    tracker = ValveLeadTracker()
    readings = [18.0] + [18.0 + 0.05 * i for i in range(1, 21)] + [19.0, 18.95, 18.9]
    _feed(tracker, readings, [MODE_HEATING] + [MODE_IDLE] * 23)
    assert tracker.get("r").minutes == pytest.approx(
        VALVE_DEFAULT_LEAD_MINUTES + 0.3 * (19 - VALVE_DEFAULT_LEAD_MINUTES)
    )


def test_tracker_gives_up_on_a_turn_that_never_comes():
    tracker = ValveLeadTracker()
    readings = [18.0] + [18.0 - 0.001 * i for i in range(1, 80)]
    _feed(tracker, readings, [MODE_IDLE] + [MODE_HEATING] * 79)
    assert tracker.get("r").minutes == VALVE_DEFAULT_LEAD_MINUTES
    # A flat start does not count either
    _feed(tracker, [18.0, 18.0, 18.2], [MODE_IDLE, MODE_HEATING, MODE_HEATING], start=10_000.0)
    assert tracker.get("r").minutes == VALVE_DEFAULT_LEAD_MINUTES


def test_tracker_lead_stays_within_its_limits():
    tracker = ValveLeadTracker()
    for n in range(40):
        readings = [18.0] + [18.0 - 0.01 * i for i in range(1, 60)] + [17.0]
        _feed(tracker, readings, [MODE_IDLE] + [MODE_HEATING] * 60, start=n * 10_000.0)
    assert tracker.get("r").minutes <= VALVE_LEAD_MAX_MINUTES


def test_tracker_trend_needs_most_of_its_window():
    tracker = ValveLeadTracker()
    _feed(tracker, [18.0, 18.1, 18.2], [MODE_HEATING] * 3)
    assert tracker.get("r").trend == 0.0
    _feed(tracker, [18.0 + 0.01 * i for i in range(20)], [MODE_HEATING] * 20, start=1000.0)
    assert tracker.get("r").trend == pytest.approx(0.01)


def test_tracker_trim_learns_less_heat_after_an_overshoot():
    tracker = ValveLeadTracker()
    _feed(tracker, [18.3] * 31, [MODE_IDLE] * 31)
    lead = VALVE_DEFAULT_LEAD_MINUTES
    assert tracker.get("r").trim == pytest.approx(-0.3 / 2.0 * 30 / (3 * lead))


def test_tracker_trim_skips_saturation_far_targets_and_other_modes():
    tracker = ValveLeadTracker()
    _feed(tracker, [17.0] * 10, [MODE_HEATING] * 10, raw=1.2)  # valve already full
    _feed(tracker, [18.6] * 10, [MODE_IDLE] * 10, raw=-0.1, start=1000.0)  # valve already shut
    _feed(tracker, [19.5] * 10, [MODE_IDLE] * 10, start=2000.0)  # sunny afternoon
    _feed(tracker, [17.0] * 10, ["cooling"] * 10, start=3000.0)
    _feed(tracker, [17.0] * 10, [MODE_HEATING] * 10, target=None, start=4000.0)
    assert tracker.get("r").trim == 0.0


def test_tracker_trim_is_limited():
    tracker = ValveLeadTracker()
    _feed(tracker, [17.6] * 2000, [MODE_HEATING] * 2000, band=1.0)
    assert tracker.get("r").trim == VALVE_TRIM_LIMIT


def test_tracker_forgets_rooms():
    tracker = ValveLeadTracker()
    _feed(tracker, [17.8] * 5, [MODE_HEATING] * 5)
    tracker.clear_room("r")
    assert tracker.get("r") == ValveLead(VALVE_DEFAULT_LEAD_MINUTES, 0.0, 0.0)
    _feed(tracker, [17.8] * 5, [MODE_HEATING] * 5)
    tracker.clear_all()
    assert tracker.get("r").trim == 0.0
    assert SimpleNamespace(**tracker.get("r")._asdict()).minutes == VALVE_DEFAULT_LEAD_MINUTES


def _turn(tracker, delay, *, start):
    """One valve start followed by a trough ``delay`` minutes later."""
    readings = [18.0] + [18.0 - 0.01 * i for i in range(1, delay + 2)]
    readings.append(readings[-1] + 0.2)
    _feed(tracker, readings, [MODE_IDLE] + [MODE_HEATING] * (delay + 2), start=start)


def test_tracker_relearns_when_the_room_answers_differently():
    tracker = ValveLeadTracker()
    tracker.load_state({"r": {"lead": 10.0, "trim": 0.0, "turns": 20}})
    _turn(tracker, 40, start=0.0)
    _turn(tracker, 40, start=10_000.0)
    # Two misses only nudge the lead
    assert tracker.get("r").minutes == pytest.approx(19.0 + 0.3 * (40 - 19.0))
    _turn(tracker, 40, start=20_000.0)
    # The third miss in a row replaces it by what the room does now
    assert tracker.get("r").minutes == pytest.approx(40.0)
    assert tracker.get_state()["r"]["turns"] == 23


def test_tracker_misses_on_both_sides_do_not_add_up():
    tracker = ValveLeadTracker()
    tracker.load_state({"r": {"lead": 20.0, "trim": 0.0, "turns": 5}})
    _turn(tracker, 40, start=0.0)
    _turn(tracker, 5, start=10_000.0)
    _turn(tracker, 40, start=20_000.0)
    assert tracker._misses["r"] == [40]
    _turn(tracker, 20, start=30_000.0)  # a hit clears the misses
    assert tracker._misses["r"] == []


def test_tracker_state_round_trips_and_skips_bad_entries():
    tracker = ValveLeadTracker()
    _turn(tracker, 7, start=0.0)
    _feed(tracker, [17.8] * 30, [MODE_HEATING] * 30, start=10_000.0)
    assert tracker.dirty
    state = tracker.get_state()
    restored = ValveLeadTracker()
    restored.load_state(
        {
            **state,
            "bad": "x",
            "nan": {"lead": float("nan")},
            "wrong": {"lead": "abc"},
            "far": {"lead": 500.0, "trim": 5.0},
        }
    )
    assert restored.get_state() == state
    assert restored.dirty is False
    assert restored.get("r").minutes == pytest.approx(tracker.get("r").minutes, abs=0.01)


def test_tracker_saves_the_trim_only_once_it_moved():
    tracker = ValveLeadTracker()
    tracker.load_state({"r": {"lead": 15.0, "trim": 0.0, "turns": 0}})
    _feed(tracker, [18.01, 18.01], [MODE_HEATING] * 2)
    assert tracker.dirty is False
    _feed(tracker, [17.5] * 30, [MODE_HEATING] * 30, start=1000.0)
    assert tracker.dirty is True


def test_tracker_prunes_removed_rooms():
    tracker = ValveLeadTracker()
    tracker.load_state({"a": {"lead": 12.0, "trim": 0.1}, "b": {"lead": 14.0, "trim": 0.0}})
    tracker.prune({"a"})
    assert set(tracker.get_state()) == {"a"}
    assert tracker.dirty
    tracker.dirty = False
    tracker.prune({"a"})
    tracker.remove_room("unknown")
    assert tracker.dirty is False


# Veranda 24.11.2026 02:03-02:31 (diagnostics/get): 17.1 at a target of 17.5, lead 17 min, trim -0.10, the valve
# held 93 % while the room did not warm. Thomas 02:35/02:43: below the target without a rising trend -> more power,
# but only once the valve has held its opening longer than the learned dead time (before that the trend shows the
# radiator). Freigabe 09:30: step by step (+10 % per lead), a jump to 100 % overshot the simulation by 0.5-0.7 K.
VERANDA_2411 = RCModel(C=1.0, U=0.0558, Q_heat=1.392, Q_solar=0.0, Q_occupancy=0.0)
LEAD_2411 = 17.17


def _demand_2411(
    reading: float,
    trend: float,
    open_minutes: float | None = 30.0,
    trim: float = -0.101,
    opening: float | None = 0.8,
    stepped: bool = False,
) -> float:
    lead = valve_lead_temp(reading, trend, LEAD_2411)
    return valve_demand(
        VERANDA_2411,
        lead,
        -2.38,
        17.5,
        q_solar=0.0,
        q_occupancy=0.0,
        lead_minutes=LEAD_2411,
        trim=trim,
        reading=reading,
        trend=trend,
        open_minutes=open_minutes,
        opening=opening,
        stepped=stepped,
    )


def _throttle_2411(reading: float, trend: float, trim: float = -0.101) -> float:
    lead = valve_lead_temp(reading, trend, LEAD_2411)
    hold = valve_holding_share(VERANDA_2411, -2.38, 17.5, q_solar=0.0, q_occupancy=0.0)
    return min(1.0, hold + trim + (17.5 - lead) / valve_band(VERANDA_2411, LEAD_2411))


@pytest.mark.parametrize("trend", [0.0, -0.005, -0.05])
@pytest.mark.parametrize("reading", [17.1, 17.3, 17.45])
def test_past_the_dead_time_below_target_without_rising_trend_opens_one_step(reading, trend):
    assert _demand_2411(reading, trend, opening=0.8) == pytest.approx(
        max(0.9, min(1.0, _throttle_2411(reading, trend)))
    )
    assert _demand_2411(reading, trend, opening=0.93) == 1.0


def test_flat_trend_within_the_dead_time_keeps_the_throttle_unless_it_stepped():
    """The radiator has not answered yet: the trend is the dead time, not the room."""
    assert _demand_2411(17.3, 0.0, open_minutes=5.0) == pytest.approx(_throttle_2411(17.3, 0.0))
    assert _demand_2411(17.3, 0.0, open_minutes=5.0, opening=0.99) < 0.99
    # a step the rule made is kept through the next lead instead of falling back to the throttle
    assert _demand_2411(17.3, 0.0, open_minutes=5.0, opening=0.99, stepped=True) == pytest.approx(0.99)
    assert _demand_2411(17.3, 0.0, open_minutes=LEAD_2411, opening=0.8) == pytest.approx(0.9)


def test_flat_veranda_reaches_full_opening_within_three_leads():
    """Closed loop through the tracker: 17.1 flat at 17.5, the throttle at ~0.8 (trim -0.4) like the night."""
    tracker = ValveLeadTracker()
    tracker.load_state({"veranda": {"lead": LEAD_2411, "trim": 0.0}})
    openings = []
    for k in range(int(4 * LEAD_2411 * 2)):  # 30-s cycles
        now = k * 30.0
        info = tracker.get("veranda", now)
        lead = valve_lead_temp(17.1, info.trend, info.minutes)
        power = valve_demand(
            VERANDA_2411,
            lead,
            -2.38,
            17.5,
            q_solar=0.0,
            q_occupancy=0.0,
            lead_minutes=info.minutes,
            trim=-0.4,
            reading=17.1,
            trend=info.trend,
            open_minutes=info.open_minutes,
            opening=info.opening,
            stepped=info.stepped,
        )
        tracker.update("veranda", now, 17.1, MODE_HEATING, 17.5, band=1.0, raw_demand=power, opening=power)
        openings.append(power)
    assert openings[0] < 0.85  # the throttle the room started with
    assert openings == sorted(openings)  # never back to the throttle in between
    assert openings[-1] == 1.0
    first_full = openings.index(1.0) * 0.5
    assert 2 * LEAD_2411 <= first_full <= 3 * LEAD_2411 + 1.0  # three steps, one per lead (cycle rounding)


def test_rising_trend_below_target_keeps_the_lead_throttle():
    """Warming towards the target: lead and trim still throttle (the overshoot fix stays)."""
    assert _demand_2411(17.25, 0.008) == pytest.approx(_throttle_2411(17.25, 0.008))
    assert _demand_2411(17.25, 0.008) < 1.0


def test_at_or_above_target_flat_trend_is_not_forced_open():
    assert _demand_2411(17.5, 0.0) < 1.0
    assert _demand_2411(17.8, -0.01) == pytest.approx(max(0.0, _throttle_2411(17.8, -0.01)))


def test_valve_not_heating_or_unknown_keeps_the_old_rule():
    assert _demand_2411(17.3, 0.0, open_minutes=None) == pytest.approx(_throttle_2411(17.3, 0.0))
    assert _demand_2411(17.3, 0.0, opening=None) == pytest.approx(_throttle_2411(17.3, 0.0))
    lead = valve_lead_temp(17.3, 0.0, LEAD_2411)
    plain = valve_demand(
        VERANDA_2411, lead, -2.38, 17.5, q_solar=0.0, q_occupancy=0.0, lead_minutes=LEAD_2411, trim=-0.101
    )
    assert plain == pytest.approx(_throttle_2411(17.3, 0.0))


def test_tracker_counts_minutes_since_the_valve_opened():
    tracker = ValveLeadTracker()
    tracker.update("r", 0.0, 17.0, MODE_IDLE, 17.5, band=1.0, raw_demand=0.0)
    assert tracker.get("r", 60.0).open_minutes is None
    tracker.update("r", 60.0, 17.0, MODE_HEATING, 17.5, band=1.0, raw_demand=0.5)
    tracker.update("r", 600.0, 17.0, MODE_HEATING, 17.5, band=1.0, raw_demand=0.5)
    assert tracker.get("r", 960.0).open_minutes == pytest.approx(15.0)
    assert tracker.get("r").open_minutes is None
    tracker.update(
        "r", 960.0, 17.0, MODE_HEATING, 17.5, band=1.0, raw_demand=0.4, opening=0.4
    )  # closes a bit: clock runs
    assert tracker.get("r", 1020.0).open_minutes == pytest.approx(16.0)
    tracker.update(
        "r", 1020.0, 17.0, MODE_HEATING, 17.5, band=1.0, raw_demand=0.4, opening=1.0
    )  # opens further: restart
    assert tracker.get("r", 1080.0).open_minutes == pytest.approx(1.0)
    assert tracker.get("r", 1080.0).opening == pytest.approx(1.0)
    assert tracker.get("r", 1080.0).stepped is True  # 16 min held >= the default lead of 15
    tracker.update("r", 1100.0, 17.6, MODE_IDLE, 17.5, band=1.0, raw_demand=0.0)
    assert tracker.get("r", 1160.0).open_minutes is None
    assert tracker.get("r", 1160.0).opening is None and tracker.get("r", 1160.0).stepped is False


def test_tracker_marks_an_early_opening_as_not_stepped():
    tracker = ValveLeadTracker()
    tracker.update("r", 0.0, 17.0, MODE_HEATING, 17.5, band=1.0, raw_demand=0.5, opening=0.5)
    tracker.update("r", 300.0, 17.0, MODE_HEATING, 17.5, band=1.0, raw_demand=0.6, opening=0.6)  # 5 min < lead
    assert tracker.get("r", 360.0).stepped is False
