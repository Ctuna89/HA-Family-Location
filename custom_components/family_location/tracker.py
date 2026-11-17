"""Tracking logic for one member, without Home Assistant dependencies.

Takes positions (``Fix``) and returns events (``Event``): place arrivals and departures, trip start and
end, speeding and low battery. Everything is computed locally, so it can be tested without HA.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .const import (
    BATTERY_HYSTERESIS,
    DEFAULT_DRIVING_SPEED,
    DEFAULT_LOW_BATTERY,
    DEFAULT_MAX_ACCURACY,
    DEFAULT_MOVING_SPEED,
    DEFAULT_START_DISTANCE,
    DEFAULT_STOP_MINUTES,
    EV_ARRIVE,
    EV_LEAVE,
    EV_LOW_BATTERY,
    EV_SPEEDING,
    EV_TRIP_END,
    EV_TRIP_START,
    MAX_PLAUSIBLE_KMH,
    SPEEDING_CONFIRM,
    SPEEDING_COOLDOWN_MIN,
    STATUS_DRIVING,
    STATUS_MOVING,
    STATUS_STILL,
    STATUS_UNKNOWN,
)

EARTH_RADIUS_M = 6_371_008.8


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two points (haversine formula)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True)
class Fix:
    """A position reported by the phone."""

    lat: float
    lon: float
    time: datetime
    accuracy: float | None = None
    speed_kmh: float | None = None   # speed reported by the phone, if any
    battery: int | None = None


@dataclass(frozen=True)
class Place:
    """A place with its radius."""

    id: str
    name: str
    lat: float
    lon: float
    radius: float
    instant: bool = False   # True: alert on entry (Home). False: wait until the person stays there

    def distance(self, lat: float, lon: float) -> float:
        return distance_m(self.lat, self.lon, lat, lon)


@dataclass(frozen=True)
class Settings:
    moving_speed: float = DEFAULT_MOVING_SPEED
    driving_speed: float = DEFAULT_DRIVING_SPEED
    stop_minutes: float = DEFAULT_STOP_MINUTES
    start_distance: float = DEFAULT_START_DISTANCE
    max_accuracy: float = DEFAULT_MAX_ACCURACY
    low_battery: int = DEFAULT_LOW_BATTERY
    speed_limit: float = 0   # km/h, 0 = no alert
    road: str | None = None  # road type the limit applies to («street» / «highway»), when known


@dataclass
class Event:
    type: str
    time: datetime
    place_id: str | None = None
    place_name: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trip:
    start: datetime
    start_lat: float
    start_lon: float
    start_place: str | None = None
    distance_m: float = 0.0
    max_speed: float = 0.0
    last_move: datetime | None = None
    move_lat: float | None = None
    move_lon: float | None = None
    speeding_count: int = 0
    end: datetime | None = None
    end_place: str | None = None
    end_lat: float | None = None
    end_lon: float | None = None

    @property
    def duration_min(self) -> float:
        end = self.end or self.last_move or self.start
        return max(0.0, (end - self.start).total_seconds() / 60)

    def summary(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "from": self.start_place,
            "to": self.end_place,
            "distance_km": round(self.distance_m / 1000, 2),
            "duration_min": round(self.duration_min, 1),
            "max_speed_kmh": round(self.max_speed),
            "speeding_count": self.speeding_count,
            "start_latitude": self.start_lat,
            "start_longitude": self.start_lon,
            "end_latitude": self.end_lat,
            "end_longitude": self.end_lon,
        }


def new_week_stats() -> dict[str, float]:
    return {"distance_m": 0.0, "trips": 0, "max_speed": 0.0, "speeding": 0}


def week_summary(stats: dict[str, float]) -> dict[str, Any]:
    return {
        "distance_km": round(stats["distance_m"] / 1000, 1),
        "trips": int(stats["trips"]),
        "max_speed_kmh": round(stats["max_speed"]),
        "speeding": int(stats["speeding"]),
    }


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class MemberTracker:
    """A member's state: where they are, whether they move, the current trip and the last one."""

    def __init__(self) -> None:
        self.initialized = False
        self.places: dict[str, datetime] = {}   # place id -> since when they are there (confirmed arrival)
        self.pending: dict[str, datetime] = {}  # entered the radius but not yet confirmed as staying
        self.known_places: set[str] | None = None   # places already taken into account (None: not recorded yet)
        self.last_fix: Fix | None = None
        self.speed_kmh: float | None = None
        self.anchor: tuple[float, float] | None = None   # resting point
        self.still_since: datetime | None = None
        self.trip: Trip | None = None
        self.last_trip: dict[str, Any] | None = None
        self.day: date | None = None
        self.distance_today_m = 0.0
        self.trips_today = 0
        self.week: str | None = None            # ISO week, e.g. «2026-W47»
        self.week_stats = new_week_stats()
        self.last_week: dict[str, Any] | None = None
        self.over_limit = 0             # consecutive readings over the limit
        self.speeding = False
        self.last_speeding_alert: datetime | None = None
        self.battery: int | None = None
        self.battery_alerted = False
        self.away_since: datetime | None = None   # since when they are at no place

    # ------------------------------------------------------------------ derived state
    @property
    def status(self) -> str:
        if not self.initialized:
            return STATUS_UNKNOWN
        if self.trip is None:
            return STATUS_STILL
        return STATUS_DRIVING if (self.speed_kmh or 0) >= self._driving_speed else STATUS_MOVING

    _driving_speed = DEFAULT_DRIVING_SPEED

    @property
    def moving(self) -> bool:
        return self.trip is not None

    def current_place_ids(self) -> list[str]:
        """Places where they are, most recent first."""
        return [pid for pid, _ in sorted(self.places.items(), key=lambda kv: kv[1], reverse=True)]

    # ------------------------------------------------------------------ input
    def adopt_places(self, places: list[Place]) -> bool:
        """Takes new places into account without alerts.

        A place created while someone is already inside it (for example adding «Work» from the office) is taken
        as where they are, as on the first position. Without this, their next position would be announced as an
        arrival hours after they really arrived. Returns True if the state changed.
        """
        ids = {p.id for p in places}
        changed = False
        if self.initialized and self.last_fix is not None:
            fix = self.last_fix
            for place in places:
                if self.known_places is not None and place.id in self.known_places:
                    continue
                if place.id in self.places or place.id in self.pending:
                    continue
                if place.distance(fix.lat, fix.lon) <= place.radius:
                    self.places[place.id] = fix.time
                    self.away_since = None
                    changed = True
        if self.known_places != ids:
            self.known_places = ids
            changed = True
        return changed

    def process(self, fix: Fix, places: list[Place], settings: Settings) -> list[Event]:
        """Processes a new position and returns the events it produces."""
        self._driving_speed = settings.driving_speed
        events: list[Event] = []
        self._roll_day(fix.time)
        events += self._battery(fix, settings)

        if fix.accuracy is not None and fix.accuracy > settings.max_accuracy:
            return events   # position too inaccurate: only the battery is used

        prev = self.last_fix
        if prev is not None and fix.time <= prev.time and (fix.lat, fix.lon) == (prev.lat, prev.lon):
            return events   # same position repeated

        speed = self._speed(prev, fix)
        self.speed_kmh = speed

        if not self.initialized:
            # First position (or after a restart without state): taken as is, without alerts.
            for place in places:
                if place.distance(fix.lat, fix.lon) <= place.radius:
                    self.places[place.id] = fix.time
            self.anchor = (fix.lat, fix.lon)
            self.still_since = fix.time
            self.away_since = None if self.places else fix.time
            self.initialized = True
            self.known_places = {p.id for p in places}
            self.last_fix = fix
            return events

        # Places created since the last position, where they already were: no arrival
        self.adopt_places(places)

        # Places that no longer exist
        known = {p.id for p in places}
        for pid in [pid for pid in self.places if pid not in known]:
            del self.places[pid]
        for pid in [pid for pid in self.pending if pid not in known]:
            del self.pending[pid]

        # --- places
        entered: list[Place] = []
        for place in places:
            dist = place.distance(fix.lat, fix.lon)
            inside = place.id in self.places or place.id in self.pending
            if not inside and dist <= place.radius:
                entered.append(place)
            elif inside and dist > place.radius + max(50.0, place.radius * 0.2):
                if self.pending.pop(place.id, None) is None:
                    del self.places[place.id]
                    events.append(Event(EV_LEAVE, fix.time, place.id, place.name, {"distance_m": round(dist)}))
                # if they were just passing through (unconfirmed) nothing is announced

        # --- trip
        anchor_dist = distance_m(*self.anchor, fix.lat, fix.lon) if self.anchor else 0.0
        moving_now = (speed or 0) >= settings.moving_speed or anchor_dist > settings.start_distance

        if self.trip is None and moving_now:
            start_place = self._place_name_at(self.anchor, places) if self.anchor else None
            if start_place is None:
                for ev in events:
                    if ev.type == EV_LEAVE:
                        start_place = ev.place_name
            start = self.still_since if self.still_since and self.still_since < fix.time else fix.time
            lat0, lon0 = self.anchor or (fix.lat, fix.lon)
            self.trip = Trip(start=start, start_lat=lat0, start_lon=lon0, start_place=start_place,
                             last_move=fix.time, move_lat=fix.lat, move_lon=fix.lon)
            self.trip.distance_m = anchor_dist
            self.distance_today_m += anchor_dist
            self.week_stats["distance_m"] += anchor_dist
            self.over_limit = 0
            self.speeding = False
            self.last_speeding_alert = None
            events.append(Event(EV_TRIP_START, start, data={"from": start_place}))
        elif self.trip is not None and prev is not None:
            seg = distance_m(prev.lat, prev.lon, fix.lat, fix.lon)
            noise = max(fix.accuracy or 0.0, 10.0) / 2
            if seg > noise or (speed or 0) >= settings.moving_speed:
                self.trip.distance_m += seg
                self.distance_today_m += seg
                self.week_stats["distance_m"] += seg
            move_dist = distance_m(self.trip.move_lat, self.trip.move_lon, fix.lat, fix.lon)
            if (speed or 0) >= settings.moving_speed / 2 or move_dist > 100:
                self.trip.last_move = fix.time
                self.trip.move_lat, self.trip.move_lon = fix.lat, fix.lon

        if self.trip is not None:
            if speed is not None:
                self.trip.max_speed = max(self.trip.max_speed, speed)
                self.week_stats["max_speed"] = max(self.week_stats["max_speed"], speed)
            events += self._speeding(fix, speed, settings)

        # Arrivals: at Home (an «instant» place) or with no trip in progress they are confirmed right away;
        # elsewhere they stay pending until the person stays stopped there (driving past or stopping at a
        # traffic light inside the radius is not an arrival).
        for place in entered:
            if place.instant or self.trip is None:
                self.places[place.id] = fix.time
                events.append(Event(EV_ARRIVE, fix.time, place.id, place.name))
            else:
                self.pending[place.id] = fix.time
        events += self._confirm_pending(fix.time, places, settings)
        self._update_away(fix.time)

        if self.trip is None:
            if moving_now:
                pass
            elif self.anchor is None or anchor_dist > settings.start_distance / 2:
                self.anchor = (fix.lat, fix.lon)
                self.still_since = fix.time

        self.last_fix = fix
        return events

    def tick(self, now: datetime, places: list[Place], settings: Settings) -> list[Event]:
        """Periodic check: a trip only ends after ``stop_minutes`` without moving (a traffic light or a
        jam doesn't end it), and only then is the arrival at a non-instant place confirmed."""
        self._roll_day(now)
        trip = self.trip
        if trip is None or trip.last_move is None:
            events = self._confirm_pending(now, places, settings)
            self._update_away(now)
            return events
        if now - trip.last_move < timedelta(minutes=settings.stop_minutes):
            events = self._confirm_pending(now, places, settings)
            self._update_away(now)
            return events
        lat, lon = trip.move_lat, trip.move_lon
        if self.last_fix is not None:
            lat, lon = self.last_fix.lat, self.last_fix.lon
        self.speed_kmh = 0.0
        # Stopped long enough: pending arrivals are confirmed before closing the trip.
        events = self._confirm_pending(now, places, settings, force=True)
        place = self._place_name_at((lat, lon), places)
        events.append(self._end_trip(trip.last_move, lat, lon, place))
        self._update_away(now)
        return events

    def _confirm_pending(self, now: datetime, places: list[Place], settings: Settings,
                         force: bool = False) -> list[Event]:
        """Confirms pending arrivals: with no trip in progress, when the trip ends, or after
        ``stop_minutes`` inside the place."""
        names = {p.id: p.name for p in places}
        events = []
        for pid, since in sorted(self.pending.items(), key=lambda kv: kv[1]):
            if force or self.trip is None or now - since >= timedelta(minutes=settings.stop_minutes):
                del self.pending[pid]
                self.places[pid] = since
                events.append(Event(EV_ARRIVE, since, pid, names.get(pid, pid)))
        return events

    def _update_away(self, now: datetime) -> None:
        if self.places:
            self.away_since = None
        elif self.away_since is None:
            self.away_since = now

    # ------------------------------------------------------------------ pieces
    def _end_trip(self, when: datetime, lat: float, lon: float, place: str | None) -> Event:
        trip = self.trip
        assert trip is not None
        trip.end, trip.end_place, trip.end_lat, trip.end_lon = when, place, lat, lon
        summary = trip.summary()
        self.last_trip = summary
        self.trips_today += 1
        self.week_stats["trips"] += 1
        self.trip = None
        self.speeding = False
        self.over_limit = 0
        self.anchor = (lat, lon)
        self.still_since = when
        return Event(EV_TRIP_END, when, data=summary)

    @staticmethod
    def _place_name_at(point: tuple[float, float] | None, places: list[Place]) -> str | None:
        if point is None:
            return None
        inside = [(p.distance(*point), p) for p in places if p.distance(*point) <= p.radius]
        return min(inside, key=lambda t: t[0])[1].name if inside else None

    def _speed(self, prev: Fix | None, fix: Fix) -> float | None:
        if fix.speed_kmh is not None and fix.speed_kmh >= 0:
            return min(fix.speed_kmh, MAX_PLAUSIBLE_KMH)
        if prev is None:
            return None
        seconds = (fix.time - prev.time).total_seconds()
        if seconds < 5:
            return self.speed_kmh
        dist = distance_m(prev.lat, prev.lon, fix.lat, fix.lon)
        noise = ((prev.accuracy or 20.0) + (fix.accuracy or 20.0)) / 2
        if dist <= noise:
            return 0.0
        kmh = (dist - noise) / seconds * 3.6
        if kmh > MAX_PLAUSIBLE_KMH:
            return None   # GPS jump
        if seconds > 600:
            return None   # too long between positions to say anything about current speed
        return kmh

    def _speeding(self, fix: Fix, speed: float | None, settings: Settings) -> list[Event]:
        limit = settings.speed_limit
        if not limit or speed is None:
            return []
        if speed <= limit:
            self.over_limit = 0
            self.speeding = False
            return []
        self.over_limit += 1
        if self.over_limit < SPEEDING_CONFIRM:
            return []
        self.speeding = True
        assert self.trip is not None
        if self.last_speeding_alert and fix.time - self.last_speeding_alert < timedelta(minutes=SPEEDING_COOLDOWN_MIN):
            return []
        self.last_speeding_alert = fix.time
        self.trip.speeding_count += 1
        self.week_stats["speeding"] += 1
        return [Event(EV_SPEEDING, fix.time, data={
            "speed_kmh": round(speed), "limit_kmh": round(limit), "road": settings.road,
            "latitude": fix.lat, "longitude": fix.lon,
        })]

    def _battery(self, fix: Fix, settings: Settings) -> list[Event]:
        if fix.battery is None:
            return []
        self.battery = fix.battery
        if fix.battery <= settings.low_battery:
            if not self.battery_alerted and self.initialized:
                self.battery_alerted = True
                return [Event(EV_LOW_BATTERY, fix.time, data={"battery": fix.battery})]
            self.battery_alerted = True
        elif fix.battery >= settings.low_battery + BATTERY_HYSTERESIS:
            self.battery_alerted = False
        return []

    def _roll_day(self, now: datetime) -> None:
        today = now.date()
        if self.day != today:
            self.day = today
            self.distance_today_m = 0.0
            self.trips_today = 0
        year, week, _ = today.isocalendar()
        key = f"{year}-W{week:02d}"
        if self.week != key:
            if self.week is not None:
                self.last_week = {"week": self.week, **week_summary(self.week_stats)}
            self.week = key
            self.week_stats = new_week_stats()

    def week_summary(self) -> dict[str, Any]:
        return week_summary(self.week_stats)

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> dict[str, Any]:
        trip = None
        if self.trip is not None:
            trip = asdict(self.trip)
            for key in ("start", "last_move", "end"):
                trip[key] = trip[key].isoformat() if trip[key] else None
        fix = None
        if self.last_fix is not None:
            fix = asdict(self.last_fix)
            fix["time"] = self.last_fix.time.isoformat()
        return {
            "initialized": self.initialized,
            "places": {k: v.isoformat() for k, v in self.places.items()},
            "pending": {k: v.isoformat() for k, v in self.pending.items()},
            "known_places": sorted(self.known_places) if self.known_places is not None else None,
            "last_fix": fix,
            "anchor": list(self.anchor) if self.anchor else None,
            "still_since": self.still_since.isoformat() if self.still_since else None,
            "away_since": self.away_since.isoformat() if self.away_since else None,
            "trip": trip,
            "last_trip": self.last_trip,
            "day": self.day.isoformat() if self.day else None,
            "distance_today_m": self.distance_today_m,
            "trips_today": self.trips_today,
            "week": self.week,
            "week_stats": self.week_stats,
            "last_week": self.last_week,
            "battery": self.battery,
            "battery_alerted": self.battery_alerted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemberTracker:
        self = cls()
        try:
            self.initialized = bool(data.get("initialized"))
            self.places = {k: datetime.fromisoformat(v) for k, v in (data.get("places") or {}).items()}
            self.pending = {k: datetime.fromisoformat(v) for k, v in (data.get("pending") or {}).items()}
            known = data.get("known_places")
            self.known_places = set(known) if known is not None else None
            if fix := data.get("last_fix"):
                self.last_fix = Fix(**{**fix, "time": datetime.fromisoformat(fix["time"])})
            if anchor := data.get("anchor"):
                self.anchor = (float(anchor[0]), float(anchor[1]))
            self.still_since = _dt(data.get("still_since"))
            self.away_since = _dt(data.get("away_since"))
            if trip := data.get("trip"):
                self.trip = Trip(**{**trip, **{k: _dt(trip.get(k)) for k in ("start", "last_move", "end")}})
            self.last_trip = data.get("last_trip")
            self.day = date.fromisoformat(data["day"]) if data.get("day") else None
            self.distance_today_m = float(data.get("distance_today_m") or 0)
            self.trips_today = int(data.get("trips_today") or 0)
            self.week = data.get("week")
            self.week_stats = {**new_week_stats(), **(data.get("week_stats") or {})}
            self.last_week = data.get("last_week")
            self.battery = data.get("battery")
            self.battery_alerted = bool(data.get("battery_alerted"))
        except (AttributeError, KeyError, TypeError, ValueError):
            return cls()   # corrupt saved state: start from scratch, without false alerts
        return self
