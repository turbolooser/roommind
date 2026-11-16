"""Tests for the fork why-log (managers/decision_log.py)."""

from __future__ import annotations

import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import (
    CLIMATE_MODE_COOL_ONLY,
    CLIMATE_MODE_HEAT_ONLY,
    DOMAIN,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    TARGET_REASON_AWAY,
    TARGET_REASON_OVERRIDE,
    TARGET_REASON_VACANT,
    TARGET_REASON_VACATION,
)
from custom_components.roommind.managers import decision_log as dl
from custom_components.roommind.managers.decision_log import (
    DECISION_LOG_DAYS,
    REASONS,
    TARGET_REASONS,
    DecisionFacts,
    DecisionLog,
    classify_reason,
    classify_target,
)

# Room at 20.0 with targets 21/24: below the heat target, inside the cool target
BASE = DecisionFacts(mode=MODE_IDLE, heat=21.0, cool=24.0, current_temp=20.0, outdoor_temp=5.0)
WARM = replace(BASE, current_temp=25.0)  # above the cool target
OK = replace(BASE, current_temp=22.0)  # inside the band

REASON_CASES = {
    dl.REASON_CLIMATE_OFF: replace(BASE, climate_active=False, window_open=True),
    dl.REASON_WAITING_SENSOR: replace(BASE, waiting_for_temp=True, window_open=True),
    dl.REASON_WINDOW_PENDING: replace(BASE, window_pending=True, force_off=True),
    dl.REASON_WINDOW_OPEN: replace(BASE, window_open=True, force_off=True),
    dl.REASON_OFF_OVERRIDE: replace(BASE, force_off=True, target_reason=TARGET_REASON_OVERRIDE),
    dl.REASON_OFF_VACATION: replace(BASE, force_off=True, target_reason=TARGET_REASON_VACATION),
    dl.REASON_OFF_AWAY: replace(BASE, force_off=True, target_reason=TARGET_REASON_AWAY),
    dl.REASON_OFF_SCHEDULE: replace(BASE, force_off=True),
    dl.REASON_COMPRESSOR_MIN_OFF: replace(BASE, compressor_blocked=True),
    dl.REASON_MANAGED: replace(BASE, has_external_sensor=False, mode=MODE_HEATING),
    dl.REASON_PREHEAT: replace(OK, mode=MODE_HEATING, preheat=True, mpc=True),
    dl.REASON_MIN_RUN: replace(OK, mode=MODE_HEATING),
    dl.REASON_MPC_RUN: replace(BASE, mode=MODE_HEATING, mpc=True),
    dl.REASON_HYSTERESIS_RUN: replace(WARM, mode=MODE_COOLING),
    dl.REASON_COMPRESSOR_MIN_RUN: replace(OK, compressor_hold=True, setback=True),
    dl.REASON_SETBACK: replace(BASE, setback=True),
    dl.REASON_HEAT_ONLY: replace(WARM, climate_mode=CLIMATE_MODE_HEAT_ONLY),
    dl.REASON_COOL_ONLY: replace(BASE, climate_mode=CLIMATE_MODE_COOL_ONLY),
    dl.REASON_OUTDOOR_GATE: replace(BASE, can_heat=False),
    dl.REASON_RESIDUAL_HEAT: replace(BASE, residual_heat=0.3),
    dl.REASON_MPC_IDLE: replace(OK, mpc=True),
    dl.REASON_IN_BAND: OK,
}


def _count(log: DecisionLog, area_id: str) -> int:
    """Stored lines of a room, regardless of the wall clock the tests' timestamps ignore."""
    return len(log._rooms.get(area_id, ()))


@pytest.mark.parametrize("reason", REASONS)
def test_each_reason_key(reason):
    """Every reason key has a case that yields exactly it."""
    assert classify_reason(REASON_CASES[reason]) == reason


def test_reason_cases_cover_all_keys():
    assert set(REASON_CASES) == set(REASONS)
    assert len(REASONS) == len(set(REASONS))


def test_min_run_cooling_and_tiny_residual():
    assert classify_reason(replace(OK, mode=MODE_COOLING, mpc=True)) == dl.REASON_MIN_RUN
    # Barely any afterglow does not explain the idle room
    assert classify_reason(replace(BASE, residual_heat=0.01)) == dl.REASON_IN_BAND


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (replace(BASE, target_reason=TARGET_REASON_OVERRIDE, mold_boost=1.0), TARGET_REASON_OVERRIDE),
        (replace(BASE, target_reason=TARGET_REASON_VACATION), TARGET_REASON_VACATION),
        (replace(BASE, target_reason=TARGET_REASON_AWAY), TARGET_REASON_AWAY),
        (replace(BASE, target_reason=TARGET_REASON_VACANT), TARGET_REASON_VACANT),
        (BASE, dl.TARGET_SCHEDULE),
        (replace(BASE, mold_boost=2.0, price_shifted=True), dl.TARGET_MOLD),
        (replace(BASE, price_shifted=True), dl.TARGET_PRICE),
    ],
)
def test_each_target_key(facts, expected):
    assert classify_target(facts) == expected


def test_target_cases_cover_all_keys():
    assert set(TARGET_REASONS) == {
        TARGET_REASON_OVERRIDE,
        TARGET_REASON_VACATION,
        TARGET_REASON_AWAY,
        TARGET_REASON_VACANT,
        dl.TARGET_SCHEDULE,
        dl.TARGET_MOLD,
        dl.TARGET_PRICE,
    }


def test_same_decision_adds_no_line():
    log = DecisionLog()
    now = 1_000_000.0
    assert log.record("r", BASE, now) is not None
    # Same mode, targets and reasons: only the reading moved
    assert log.record("r", replace(BASE, current_temp=20.3, outdoor_temp=6.0), now + 60) is None
    assert log.record("r", BASE, now + 120) is None
    assert _count(log, "r") == 1


@pytest.mark.parametrize(
    "change",
    [
        {"mode": MODE_HEATING},
        {"heat": 21.5},
        {"cool": 25.0},
        {"window_open": True},
        {"target_reason": TARGET_REASON_AWAY},
    ],
)
def test_change_adds_line(change):
    log = DecisionLog()
    log.record("r", BASE, 1000.0)
    assert log.record("r", replace(BASE, **change), 1060.0) is not None
    assert _count(log, "r") == 2


def test_target_rounding_hides_float_noise():
    log = DecisionLog()
    log.record("r", BASE, 1000.0)
    assert log.record("r", replace(BASE, heat=21.0000001), 1060.0) is None


def test_line_content_and_windows():
    log = DecisionLog()
    line = log.record(
        "r",
        replace(BASE, window_open=True, open_windows=("binary_sensor.fenster",), current_temp=19.96),
        1000.0,
    )
    assert line == {
        "ts": 1000.0,
        "mode": MODE_IDLE,
        "reason": dl.REASON_WINDOW_OPEN,
        "target_reason": dl.TARGET_SCHEDULE,
        "heat": 21.0,
        "cool": 24.0,
        "current": 20.0,
        "outdoor": 5.0,
        "windows": ["binary_sensor.fenster"],
    }
    # Window entities only on window lines
    assert "windows" not in log.record("r", replace(BASE, open_windows=("binary_sensor.fenster",)), 1060.0)


def test_entries_newest_first_filter_and_limit():
    log = DecisionLog()
    now = time.time()
    log.record("a", BASE, now - 300)
    log.record("b", BASE, now - 200)
    log.record("a", replace(BASE, mode=MODE_HEATING), now - 100)
    all_lines = log.entries()
    assert [(ln["area_id"], ln["ts"]) for ln in all_lines] == [
        ("a", round(now - 100, 1)),
        ("b", round(now - 200, 1)),
        ("a", round(now - 300, 1)),
    ]
    assert [ln["area_id"] for ln in log.entries("a")] == ["a", "a"]
    assert len(log.entries(limit=1)) == 1
    assert len(log.entries(start_ts=now - 250, end_ts=now - 150)) == 1
    assert log.entries("unknown") == []


def test_fourteen_day_retention():
    log = DecisionLog()
    day = 86400
    now = 100 * day
    log.record("r", BASE, now - 20 * day)
    log.record("r", replace(BASE, heat=22.0), now - 15 * day)
    log.record("r", replace(BASE, heat=23.0), now - 13 * day)
    log.record("r", replace(BASE, heat=24.0), now)
    lines = list(log._rooms["r"])
    assert [ln["heat"] for ln in lines] == [23.0, 24.0]
    assert DECISION_LOG_DAYS == 14


def test_retention_keeps_baseline_but_hides_it():
    """An unchanged room keeps its last line as baseline (no duplicate), but it is not shown."""
    log = DecisionLog()
    old = time.time() - 20 * 86400
    log.record("r", BASE, old)
    log.prune(time.time())
    assert len(log._rooms["r"]) == 1
    assert log.entries("r") == []
    assert log.record("r", BASE) is None


def test_forget_room():
    log = DecisionLog()
    log.record("r", BASE, 1000.0)
    log.forget("r")
    assert _count(log, "r") == 0


class _FakeStore:
    """In-memory stand-in for homeassistant.helpers.storage.Store."""

    saved: dict | None = None
    instances: list[_FakeStore] = []

    def __init__(self, hass, version, key):
        self.version = version
        self.key = key
        self.delay_calls = 0
        _FakeStore.instances.append(self)

    async def async_load(self):
        return _FakeStore.saved

    def async_delay_save(self, data_func, delay):
        self.delay_calls += 1
        self.delay = delay
        _FakeStore.saved = data_func()

    async def async_save(self, data):
        _FakeStore.saved = data


@pytest.mark.asyncio
async def test_persistence_round_trip():
    _FakeStore.saved = None
    _FakeStore.instances = []
    with patch("homeassistant.helpers.storage.Store", _FakeStore):
        log = DecisionLog(MagicMock())
        await log.async_load()
        store = _FakeStore.instances[0]
        assert store.key == "roommind_decision_log"
        assert store.version == 1
        now = time.time()
        log.record("r", BASE, now - 60)
        log.record("r", replace(BASE, window_open=True, open_windows=("binary_sensor.w",)), now)
        assert store.delay_calls == 2
        assert store.delay == dl.DECISION_LOG_SAVE_DELAY
        # Unchanged decision: no save scheduled
        log.record("r", replace(BASE, window_open=True), now + 1)
        assert store.delay_calls == 2
        await log.async_flush()

        restored = DecisionLog(MagicMock())
        await restored.async_load()
        assert restored.entries("r") == log.entries("r")
        # The restored baseline suppresses a duplicate after a restart
        assert restored.record("r", replace(BASE, window_open=True), now + 30) is None


@pytest.mark.asyncio
async def test_broken_saved_data_starts_empty():
    _FakeStore.saved = {"rooms": {"r": [{"no_ts": 1}, "junk"], "x": "junk"}}
    with patch("homeassistant.helpers.storage.Store", _FakeStore):
        log = DecisionLog(MagicMock())
        await log.async_load()
    assert log.entries() == []


@pytest.mark.asyncio
async def test_main_storage_version_untouched():
    from custom_components.roommind import store

    assert store.STORAGE_VERSION == 1
    assert dl.DECISION_LOG_STORE_KEY != store.STORAGE_KEY


# ---------------------------------------------------------------------------
# WebSocket command
# ---------------------------------------------------------------------------


def _ws_hass(coordinator):
    hass = MagicMock()
    hass.data = {DOMAIN: {"coordinator": coordinator}} if coordinator is not None else {DOMAIN: {}}
    return hass


def test_ws_decision_log_get():
    from custom_components.roommind.websocket_api import websocket_get_decision_log

    log = DecisionLog()
    now = time.time()
    log.record("a", BASE, now - 100)
    log.record("b", replace(BASE, window_open=True), now - 50)
    coordinator = MagicMock()
    coordinator.decision_log = log
    conn = MagicMock()

    websocket_get_decision_log(_ws_hass(coordinator), conn, {"id": 1, "type": "roommind/decision_log/get"})
    result = conn.send_result.call_args[0][1]
    assert [e["area_id"] for e in result["entries"]] == ["b", "a"]

    websocket_get_decision_log(
        _ws_hass(coordinator), conn, {"id": 2, "type": "roommind/decision_log/get", "area_id": "a"}
    )
    result = conn.send_result.call_args[0][1]
    assert [e["area_id"] for e in result["entries"]] == ["a"]

    websocket_get_decision_log(
        _ws_hass(coordinator),
        conn,
        {"id": 3, "type": "roommind/decision_log/get", "start_ts": now - 60, "limit": 5},
    )
    result = conn.send_result.call_args[0][1]
    assert [e["area_id"] for e in result["entries"]] == ["b"]


def test_ws_decision_log_without_coordinator():
    from custom_components.roommind.websocket_api import websocket_get_decision_log

    conn = MagicMock()
    websocket_get_decision_log(_ws_hass(None), conn, {"id": 1, "type": "roommind/decision_log/get"})
    conn.send_result.assert_called_once_with(1, {"entries": []})


def test_ws_decision_log_schema():
    import voluptuous as vol

    from custom_components.roommind.websocket_api import websocket_get_decision_log

    schema = websocket_get_decision_log._ws_schema
    schema({"id": 1, "type": "roommind/decision_log/get", "area_id": "a", "start_ts": "1", "limit": 10})
    with pytest.raises(vol.Invalid):
        schema({"id": 1, "type": "roommind/decision_log/get", "limit": 0})


# ---------------------------------------------------------------------------
# Coordinator: a real cycle writes the line
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_logs_open_window_once(hass, mock_config_entry):
    from .coordinator.conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

    room = {**SAMPLE_ROOM, "window_sensors": ["binary_sensor.living_room_window"]}
    store = _make_store_mock({"living_room_abc12345": room})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(window_sensors={"binary_sensor.living_room_window": "on"})
    )
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator.decision_log = DecisionLog()  # in memory only
    await coordinator._async_update_data()
    await coordinator._async_update_data()

    lines = coordinator.decision_log.entries("living_room_abc12345")
    assert len(lines) == 1
    assert lines[0]["mode"] == MODE_IDLE
    assert lines[0]["reason"] == dl.REASON_WINDOW_OPEN
    assert lines[0]["windows"] == ["binary_sensor.living_room_window"]


@pytest.mark.asyncio
async def test_coordinator_forget_room_drops_log(hass, mock_config_entry):
    from .coordinator.conftest import _create_coordinator

    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator.decision_log = DecisionLog()
    coordinator.decision_log.record("gone", BASE)
    with patch("homeassistant.helpers.entity_registry.async_get"):
        coordinator._forget_room("gone")
    assert coordinator.decision_log.entries("gone") == []


# ---------------------------------------------------------------------------
# Panel texts: every key the backend sends has a German and English text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["de", "en"])
def test_panel_texts_for_every_key(lang):
    import json
    from pathlib import Path

    texts = json.loads(
        (Path(__file__).parent.parent / "frontend" / "src" / "locales" / f"{lang}.json").read_text(encoding="utf-8")
    )
    missing = [f"decision_log.reason.{r}" for r in REASONS if f"decision_log.reason.{r}" not in texts]
    missing += [
        f"decision_log.target_reason.{t}" for t in TARGET_REASONS if f"decision_log.target_reason.{t}" not in texts
    ]
    assert missing == []
    assert texts["decision_log.tab"]
