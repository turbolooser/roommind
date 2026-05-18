"""Sensor platform for RoomMind."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import RoomMindCoordinator


def _create_room_entities(coordinator: RoomMindCoordinator, area_id: str) -> list[SensorEntity]:
    """Create the standard set of sensor entities for a room."""
    return [
        RoomMindTargetTemperatureSensor(coordinator, area_id),
        RoomMindModeSensor(coordinator, area_id),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind sensor entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]

    # Store the callback on the coordinator so dynamic entity creation works
    coordinator.async_add_entities = async_add_entities

    # Create entities for rooms that already exist in the store
    rooms = store.get_rooms()
    entities: list[SensorEntity] = []
    for area_id in rooms:
        entities.extend(_create_room_entities(coordinator, area_id))
        coordinator._entity_areas.add(area_id)

    # One demand "flight recorder" sensor per compressor group. Groups
    # rarely change; new groups are picked up on a config-entry reload.
    for group in store.get_settings().get("compressor_groups", []):
        gid = group.get("id")
        if gid:
            entities.append(RoomMindDemandDebugSensor(coordinator, gid, group.get("name", "")))

    if entities:
        async_add_entities(entities)


class _RoomMindBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for all RoomMind room sensors."""

    _attr_has_entity_name = True
    _data_key: str  # Key in the room state dict (e.g. "current_temp")

    def __init__(
        self,
        coordinator: RoomMindCoordinator,
        area_id: str,
        suffix: str,
        name_label: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_{suffix}"
        self._attr_name = f"{area_id} {name_label}"
        self.entity_id = f"sensor.{DOMAIN}_{area_id}_{suffix}"

    @property
    def native_value(self) -> float | str | None:
        """Return the sensor value from the coordinator data."""
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get(self._data_key)
            return val if isinstance(val, (float, int, str)) else None
        return None


class RoomMindTargetTemperatureSensor(_RoomMindBaseSensor):
    """Sensor showing the target temperature for a RoomMind room."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _data_key = "target_temp"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "target_temp", "Target Temperature")


class RoomMindModeSensor(_RoomMindBaseSensor):
    """Sensor showing the current mode for a RoomMind room."""

    _data_key = "mode"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "mode", "Mode")

    @property
    def native_value(self) -> str | None:
        """Return the current mode, defaulting to 'idle'."""
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get("mode", "idle")
            return str(val) if val is not None else "idle"
        return "idle"


class RoomMindDemandDebugSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic flight recorder for one compressor group's demand control.

    The state is the controller's *computed intent* (target demand %) each
    cycle; the device's actually-applied value lives on the demand select
    entity. Recording both lets offline analysis separate cause (what the
    controller wanted) from effect (what the hardware did) — the data
    foundation for the demand-learning feature.
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator: RoomMindCoordinator, group_id: str, group_name: str) -> None:
        """Initialize the demand debug sensor for a compressor group."""
        super().__init__(coordinator)
        self._group_id = group_id
        slug = slugify(group_name) if group_name else group_id.split("-", 1)[0]
        self._attr_unique_id = f"{DOMAIN}_demand_{group_id}"
        self._attr_name = f"demand {slug} debug"
        self.entity_id = f"sensor.{DOMAIN}_demand_{slug}_debug"

    def _debug(self) -> dict | None:
        data = self.coordinator.data or {}
        entry = data.get("demand_debug", {}).get(self._group_id)
        return entry if isinstance(entry, dict) else None

    @property
    def native_value(self) -> int | None:
        """Return the controller's computed target demand %, or None."""
        entry = self._debug()
        if entry is None:
            return None
        val = entry.get("target")
        return int(val) if isinstance(val, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the intermediate control signals for offline analysis."""
        entry = self._debug()
        if entry is None:
            return {}
        return {k: v for k, v in entry.items() if k != "target"}
