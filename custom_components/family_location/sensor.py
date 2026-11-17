"""Sensors: where each member is, whether they move, how fast, their trips and battery."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfSpeed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FamilyLocationConfigEntry
from .const import AWAY, STATUSES
from .entity import CircleEntity, MemberEntity, PlaceEntity


async def async_setup_entry(hass: HomeAssistant, entry: FamilyLocationConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    engine = entry.runtime_data
    for member in engine.members.values():
        async_add_entities([
            PlaceSensor(engine, member),
            StatusSensor(engine, member),
            SpeedSensor(engine, member),
            BatterySensor(engine, member),
            DistanceTodaySensor(engine, member),
            LastTripSensor(engine, member),
            DistanceWeekSensor(engine, member),
            TopSpeedWeekSensor(engine, member),
            SpeedingWeekSensor(engine, member),
        ], config_subentry_id=member.id)
    if engine.members:
        async_add_entities([LeaderboardSensor(engine)])
    for place in engine.places.values():
        async_add_entities([PeopleSensor(engine, place)], config_subentry_id=place.id)


class PlaceSensor(MemberEntity, SensorEntity):
    """Place where they are; otherwise the Home Assistant zone they are in, the approximate address, or «away»."""

    _attr_icon = "mdi:map-marker-account"

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "place")

    @property
    def native_value(self) -> str | None:
        name = self.engine.current_place_name(self.member.id)
        if name:
            return name
        if zone := self.engine.current_zone_name(self.member.id):
            return zone
        if self.tracker.trip is None and (address := self.engine.addresses.get(self.member.id)):
            return address[:255]
        return AWAY[self.engine.language]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self.tracker
        ids = t.current_place_ids()
        since = t.places.get(ids[0]) if ids else t.away_since
        fix = t.last_fix
        return {
            "tracked_entity": self.member.entity_id,
            "in_place": bool(ids),
            "zone": zone.entity_id if (zone := self.engine.current_zone(self.member.id)) else None,
            "place_id": ids[0] if ids else None,
            "places": [self.engine.places[i].name for i in ids if i in self.engine.places],
            "since": since.isoformat() if since else None,
            "address": self.engine.addresses.get(self.member.id),
            "latitude": fix.lat if fix else None,
            "longitude": fix.lon if fix else None,
            "gps_accuracy": fix.accuracy if fix else None,
            "last_seen": fix.time.isoformat() if fix else None,
        }


class StatusSensor(MemberEntity, SensorEntity):
    """Still, moving or driving; the trip in progress in the attributes."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "status")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        return self.tracker.status

    @property
    def icon(self) -> str:
        return {"still": "mdi:human-handsdown", "moving": "mdi:walk",
                "driving": "mdi:car"}.get(self.tracker.status, "mdi:help-circle-outline")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self.tracker
        trip = t.trip
        if trip is None:
            return {"since": t.still_since.isoformat() if t.still_since else None}
        return {
            "since": trip.start.isoformat(),
            "trip_from": trip.start_place,
            "trip_distance_km": round(trip.distance_m / 1000, 2),
            "trip_duration_min": round(trip.duration_min, 1),
            "trip_max_speed_kmh": round(trip.max_speed),
            "speeding": t.speeding,
        }


class SpeedSensor(MemberEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.SPEED
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "speed")

    @property
    def native_value(self) -> float | None:
        if self.tracker.trip is None:
            return 0.0
        speed = self.tracker.speed_kmh
        return round(speed, 1) if speed is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"speed_limit_kmh": self.member.speed_limit or None,
                "highway_speed_limit_kmh": self.member.highway_limit or None}


class BatterySensor(MemberEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "battery")

    @property
    def available(self) -> bool:
        return self.tracker.battery is not None

    @property
    def native_value(self) -> int | None:
        return self.tracker.battery


class DistanceTodaySensor(MemberEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "distance_today")

    @property
    def native_value(self) -> float:
        return round(self.tracker.distance_today_m / 1000, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"trips_today": self.tracker.trips_today}


class LastTripSensor(MemberEntity, SensorEntity):
    """Distance of the last finished trip; origin, destination, duration and top speed in the attributes."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:car-clock"

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "last_trip")

    @property
    def available(self) -> bool:
        return self.tracker.last_trip is not None

    @property
    def native_value(self) -> float | None:
        trip = self.tracker.last_trip
        return trip.get("distance_km") if trip else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self.tracker.last_trip or {})


class PeopleSensor(PlaceEntity, SensorEntity):
    """How many members are at the place and who they are."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:account-group"

    def __init__(self, engine: Any, place: Any) -> None:
        super().__init__(engine, place, "people")

    def _here(self) -> list[str]:
        return [self.engine.members[mid].name for mid, t in self.engine.trackers.items()
                if self.place.id in t.places]

    @property
    def native_value(self) -> int:
        return len(self._here())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        places = {p.id: p for p in self.engine.place_list()}
        p = places.get(self.place.id)
        return {
            "people": self._here(),
            "latitude": p.lat if p else None,
            "longitude": p.lon if p else None,
            "radius": p.radius if p else None,
            "zone": self.place.zone,
        }


# ---------------------------------------------------------------------- weekly stats (Monday to Sunday)
class _WeekSensor(MemberEntity, SensorEntity):
    @property
    def available(self) -> bool:
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"week": self.tracker.week, **self.tracker.week_summary(), "last_week": self.tracker.last_week}


class DistanceWeekSensor(_WeekSensor):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "distance_week")

    @property
    def native_value(self) -> float:
        return self.tracker.week_summary()["distance_km"]


class TopSpeedWeekSensor(_WeekSensor):
    _attr_device_class = SensorDeviceClass.SPEED
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:speedometer"

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "top_speed_week")

    @property
    def native_value(self) -> int:
        return self.tracker.week_summary()["max_speed_kmh"]


class SpeedingWeekSensor(_WeekSensor):
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:speedometer-medium"

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "speeding_week")

    @property
    def native_value(self) -> int:
        return self.tracker.week_summary()["speeding"]


class LeaderboardSensor(CircleEntity, SensorEntity):
    """Who drove the most this week; the full ranking (with every weekly stat) is in the attributes."""

    _attr_icon = "mdi:podium-gold"

    def __init__(self, engine: Any) -> None:
        super().__init__(engine, "leaderboard")

    def _ranking(self) -> list[dict[str, Any]]:
        rows = [{"name": self.engine.members[mid].name, "entity_id": self.engine.members[mid].entity_id,
                 **t.week_summary()} for mid, t in self.engine.trackers.items() if mid in self.engine.members]
        rows.sort(key=lambda r: (-r["distance_km"], r["name"]))
        for position, row in enumerate(rows, start=1):
            row["position"] = position
        return rows

    @property
    def native_value(self) -> str | None:
        ranking = self._ranking()
        return ranking[0]["name"] if ranking and ranking[0]["distance_km"] > 0 else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ranking = self._ranking()
        weeks = [t.week for t in self.engine.trackers.values() if t.week]
        return {
            "week": max(weeks) if weeks else None,
            "ranking": ranking,
            "most_distance": ranking[0]["name"] if ranking and ranking[0]["distance_km"] > 0 else None,
            "fastest": max(ranking, key=lambda r: r["max_speed_kmh"])["name"]
            if ranking and any(r["max_speed_kmh"] for r in ranking) else None,
            "most_speeding": max(ranking, key=lambda r: r["speeding"])["name"]
            if ranking and any(r["speeding"] for r in ranking) else None,
        }
