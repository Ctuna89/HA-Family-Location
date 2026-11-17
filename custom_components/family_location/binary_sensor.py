"""Binary sensors: moving, speeding and «occupied» for each place."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FamilyLocationConfigEntry
from .entity import MemberEntity, PlaceEntity


async def async_setup_entry(hass: HomeAssistant, entry: FamilyLocationConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    engine = entry.runtime_data
    for member in engine.members.values():
        entities: list[BinarySensorEntity] = [MovingBinarySensor(engine, member)]
        if member.speed_limit:
            entities.append(SpeedingBinarySensor(engine, member))
        async_add_entities(entities, config_subentry_id=member.id)
    for place in engine.places.values():
        async_add_entities([OccupiedBinarySensor(engine, place)], config_subentry_id=place.id)


class MovingBinarySensor(MemberEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.MOVING

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "moving")

    @property
    def is_on(self) -> bool:
        return self.tracker.moving


class SpeedingBinarySensor(MemberEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:speedometer-medium"

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "speeding")

    @property
    def is_on(self) -> bool:
        return self.tracker.speeding

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"speed_limit_kmh": self.member.speed_limit,
                "highway_speed_limit_kmh": self.member.highway_limit or None}


class OccupiedBinarySensor(PlaceEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, engine: Any, place: Any) -> None:
        super().__init__(engine, place, "occupied")

    @property
    def is_on(self) -> bool:
        return any(self.place.id in t.places for t in self.engine.trackers.values())
