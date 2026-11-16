"""Lógica de seguimiento de un integrante, sin dependencias de Home Assistant.

Recibe posiciones (``Fix``) y devuelve eventos (``Event``): llegadas y salidas de lugares, inicio y fin de
viajes, excesos de velocidad y batería baja. Todo se calcula localmente; así se puede probar sin HA.
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
    """Distancia en metros entre dos puntos (fórmula del semiverseno)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True)
class Fix:
    """Una posición informada por el teléfono."""

    lat: float
    lon: float
    time: datetime
    accuracy: float | None = None
    speed_kmh: float | None = None   # velocidad informada por el teléfono, si la hay
    battery: int | None = None


@dataclass(frozen=True)
class Place:
    """Un lugar con su círculo."""

    id: str
    name: str
    lat: float
    lon: float
    radius: float
    instant: bool = False   # True: avisa apenas entra (Casa). False: espera a que se quede detenido ahí

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
    speed_limit: float = 0   # km/h, 0 = sin aviso


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


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class MemberTracker:
    """Estado de un integrante: dónde está, si se mueve, su viaje actual y el último."""

    def __init__(self) -> None:
        self.initialized = False
        self.places: dict[str, datetime] = {}   # id del lugar -> desde cuándo está ahí (llegada confirmada)
        self.pending: dict[str, datetime] = {}  # entró al radio pero aún no se confirma que se quedó ahí
        self.last_fix: Fix | None = None
        self.speed_kmh: float | None = None
        self.anchor: tuple[float, float] | None = None   # punto de reposo
        self.still_since: datetime | None = None
        self.trip: Trip | None = None
        self.last_trip: dict[str, Any] | None = None
        self.day: date | None = None
        self.distance_today_m = 0.0
        self.trips_today = 0
        self.over_limit = 0             # lecturas seguidas sobre el límite
        self.speeding = False
        self.last_speeding_alert: datetime | None = None
        self.battery: int | None = None
        self.battery_alerted = False
        self.away_since: datetime | None = None   # desde cuándo no está en ningún lugar

    # ------------------------------------------------------------------ estado derivado
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
        """Lugares donde está, el más reciente primero."""
        return [pid for pid, _ in sorted(self.places.items(), key=lambda kv: kv[1], reverse=True)]

    # ------------------------------------------------------------------ entrada
    def process(self, fix: Fix, places: list[Place], settings: Settings) -> list[Event]:
        """Procesa una posición nueva y devuelve los eventos que genera."""
        self._driving_speed = settings.driving_speed
        events: list[Event] = []
        self._roll_day(fix.time)
        events += self._battery(fix, settings)

        if fix.accuracy is not None and fix.accuracy > settings.max_accuracy:
            return events   # posición demasiado imprecisa: solo se usa la batería

        prev = self.last_fix
        if prev is not None and fix.time <= prev.time and (fix.lat, fix.lon) == (prev.lat, prev.lon):
            return events   # misma posición repetida

        speed = self._speed(prev, fix)
        self.speed_kmh = speed

        if not self.initialized:
            # Primera posición (o tras reiniciar sin estado): se toma tal cual, sin avisos.
            for place in places:
                if place.distance(fix.lat, fix.lon) <= place.radius:
                    self.places[place.id] = fix.time
            self.anchor = (fix.lat, fix.lon)
            self.still_since = fix.time
            self.away_since = None if self.places else fix.time
            self.initialized = True
            self.last_fix = fix
            return events

        # Lugares que ya no existen
        known = {p.id for p in places}
        for pid in [pid for pid in self.places if pid not in known]:
            del self.places[pid]
        for pid in [pid for pid in self.pending if pid not in known]:
            del self.pending[pid]

        # --- lugares
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
                # si solo estaba de paso (sin confirmar) no se avisa nada

        # --- viaje
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
            move_dist = distance_m(self.trip.move_lat, self.trip.move_lon, fix.lat, fix.lon)
            if (speed or 0) >= settings.moving_speed / 2 or move_dist > 100:
                self.trip.last_move = fix.time
                self.trip.move_lat, self.trip.move_lon = fix.lat, fix.lon

        if self.trip is not None:
            if speed is not None:
                self.trip.max_speed = max(self.trip.max_speed, speed)
            events += self._speeding(fix, speed, settings)

        # Llegadas: a Casa (lugar «inmediato») o sin viaje en curso se confirma al tiro; en los demás
        # lugares queda pendiente hasta que se quede detenido ahí (pasar por fuera o parar en un semáforo
        # dentro del radio no cuenta como llegar).
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
        """Revisión periódica: un viaje termina solo tras ``stop_minutes`` sin moverse (un semáforo o un
        taco no lo cortan) y recién ahí se confirma la llegada a un lugar que no sea inmediato."""
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
        # Detenido el tiempo suficiente: las llegadas pendientes se confirman antes de cerrar el viaje.
        events = self._confirm_pending(now, places, settings, force=True)
        place = self._place_name_at((lat, lon), places)
        events.append(self._end_trip(trip.last_move, lat, lon, place))
        self._update_away(now)
        return events

    def _confirm_pending(self, now: datetime, places: list[Place], settings: Settings,
                         force: bool = False) -> list[Event]:
        """Confirma las llegadas pendientes: sin viaje en curso, al cerrar el viaje, o tras llevar
        ``stop_minutes`` dentro del lugar."""
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

    # ------------------------------------------------------------------ piezas
    def _end_trip(self, when: datetime, lat: float, lon: float, place: str | None) -> Event:
        trip = self.trip
        assert trip is not None
        trip.end, trip.end_place, trip.end_lat, trip.end_lon = when, place, lat, lon
        summary = trip.summary()
        self.last_trip = summary
        self.trips_today += 1
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
            return None   # salto de GPS
        if seconds > 600:
            return None   # demasiado tiempo entre posiciones para decir algo de la velocidad actual
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
        return [Event(EV_SPEEDING, fix.time, data={
            "speed_kmh": round(speed), "limit_kmh": round(limit),
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

    # ------------------------------------------------------------------ persistencia
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
            "last_fix": fix,
            "anchor": list(self.anchor) if self.anchor else None,
            "still_since": self.still_since.isoformat() if self.still_since else None,
            "away_since": self.away_since.isoformat() if self.away_since else None,
            "trip": trip,
            "last_trip": self.last_trip,
            "day": self.day.isoformat() if self.day else None,
            "distance_today_m": self.distance_today_m,
            "trips_today": self.trips_today,
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
            self.battery = data.get("battery")
            self.battery_alerted = bool(data.get("battery_alerted"))
        except (AttributeError, KeyError, TypeError, ValueError):
            return cls()   # estado guardado dañado: se parte de cero, sin avisos falsos
        return self
