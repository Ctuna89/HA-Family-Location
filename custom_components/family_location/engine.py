"""Family Location engine: follows members, detects events and sends alerts."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event as HaEvent, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import geocode, messages
from .const import (
    CONF_DRIVING_SPEED,
    CONF_ENTITY,
    CONF_ICON,
    CONF_LOCATION,
    CONF_LOW_BATTERY,
    CONF_MAX_ACCURACY,
    CONF_MOVING_SPEED,
    CONF_NOTIFY,
    CONF_NOTIFY_ARRIVE,
    CONF_NOTIFY_BATTERY,
    CONF_NOTIFY_LEAVE,
    CONF_INSTANT,
    CONF_NOTIFY_SELF,
    CONF_NOTIFY_SPEEDING,
    CONF_NOTIFY_TRIPS,
    CONF_RADIUS,
    CONF_RECEIVE_ALERTS,
    CONF_RECIPIENTS,
    CONF_REVERSE_GEOCODE,
    CONF_SHOW_ZONES,
    CONF_SAFETY_RECIPIENTS,
    CONF_SPEED_LIMIT,
    CONF_HIGHWAY_SPEED_LIMIT,
    CONF_START_DISTANCE,
    CONF_STOP_MINUTES,
    CONF_WATCH,
    CONF_ZONE,
    DEFAULT_DRIVING_SPEED,
    DEFAULT_LOW_BATTERY,
    DEFAULT_MAX_ACCURACY,
    DEFAULT_MOVING_SPEED,
    DEFAULT_RADIUS,
    DEFAULT_START_DISTANCE,
    DEFAULT_STOP_MINUTES,
    DOMAIN,
    EV_ARRIVE,
    EV_CHECK_IN,
    EV_LEAVE,
    EV_LOW_BATTERY,
    EV_SOS,
    EV_SPEEDING,
    EV_TRIP_END,
    EV_TRIP_START,
    EVENT_NAME,
    SIGNAL_UPDATE,
    TOGETHER_GRACE_S,
    TOGETHER_M,
    TOGETHER_WINDOW_MIN,
    SUBENTRY_MEMBER,
    SUBENTRY_PLACE,
)
from .tracker import Event, Fix, MemberTracker, Place, Settings, distance_m

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 30
ROAD_CACHE_TTL = timedelta(days=30)
ROAD_CACHE_MAX = 5000
MEMBER_ROAD_TTL = timedelta(minutes=5)
TICK = timedelta(seconds=30)
# Alerts not sent to whoever is with the person (they already know).
COMPANION_EVENTS = {EV_ARRIVE, EV_LEAVE, EV_TRIP_START, EV_TRIP_END}


@dataclass
class MemberConfig:
    id: str
    name: str
    entity_id: str
    notify: list[str] = field(default_factory=list)
    receive_alerts: bool = True
    speed_limit: float = 0          # street limit (or the only one)
    highway_limit: float = 0        # 0 = same as speed_limit

    @property
    def two_limits(self) -> bool:
        return bool(self.speed_limit and self.highway_limit and self.highway_limit != self.speed_limit)


@dataclass
class PlaceConfig:
    id: str
    name: str
    latitude: float | None
    longitude: float | None
    radius: float
    zone: str | None = None
    icon: str | None = None
    notify_arrive: bool = True
    notify_leave: bool = True
    instant: bool = False
    watch: list[str] = field(default_factory=list)
    recipients: list[str] = field(default_factory=list)


def member_from_subentry(subentry_id: str, title: str, data: dict[str, Any]) -> MemberConfig:
    notify = data.get(CONF_NOTIFY) or []
    if isinstance(notify, str):
        notify = [notify]
    return MemberConfig(
        id=subentry_id,
        name=title,
        entity_id=data[CONF_ENTITY],
        notify=[n for n in notify if n],
        receive_alerts=bool(data.get(CONF_RECEIVE_ALERTS, True)),
        speed_limit=float(data.get(CONF_SPEED_LIMIT) or 0),
        highway_limit=float(data.get(CONF_HIGHWAY_SPEED_LIMIT) or 0),
    )


def place_from_subentry(subentry_id: str, title: str, data: dict[str, Any]) -> PlaceConfig:
    loc = data.get(CONF_LOCATION) or {}
    return PlaceConfig(
        id=subentry_id,
        name=title,
        latitude=loc.get(ATTR_LATITUDE),
        longitude=loc.get(ATTR_LONGITUDE),
        radius=float(loc.get(CONF_RADIUS) or data.get(CONF_RADIUS) or DEFAULT_RADIUS),
        zone=data.get(CONF_ZONE) or None,
        icon=data.get(CONF_ICON) or None,
        notify_arrive=bool(data.get(CONF_NOTIFY_ARRIVE, True)),
        notify_leave=bool(data.get(CONF_NOTIFY_LEAVE, True)),
        instant=bool(data.get(CONF_INSTANT, data.get(CONF_ZONE) == "zone.home")),
        watch=list(data.get(CONF_WATCH) or []),
        recipients=list(data.get(CONF_RECIPIENTS) or []),
    )


def notify_service(name: str) -> str:
    """«notify.mobile_app_x» or «mobile_app_x» -> «mobile_app_x»."""
    return name.split(".", 1)[1] if name.startswith("notify.") else name


class CircleEngine:
    """Ties together the configuration, each member's logic and Home Assistant."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.options: dict[str, Any] = {**entry.data, **entry.options}
        self.members: dict[str, MemberConfig] = {}
        self.places: dict[str, PlaceConfig] = {}
        for sub in entry.subentries.values():
            try:
                if sub.subentry_type == SUBENTRY_MEMBER:
                    self.members[sub.subentry_id] = member_from_subentry(sub.subentry_id, sub.title, dict(sub.data))
                elif sub.subentry_type == SUBENTRY_PLACE:
                    self.places[sub.subentry_id] = place_from_subentry(sub.subentry_id, sub.title, dict(sub.data))
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.warning("Ignoring «%s», its configuration is incomplete: %s", sub.title, err)
        self.trackers: dict[str, MemberTracker] = {}
        self.addresses: dict[str, str | None] = {}
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._unsubs: list[Callable[[], None]] = []
        self._by_entity: dict[str, list[str]] = {}
        self._geocoding: set[str] = set()
        self._battery_entities: dict[str, str | None] = {}
        self._pending_sends: set[Callable[[], None]] = set()
        self._road_cache: dict[tuple[float, float], tuple[str, datetime]] = {}
        self._road_lookups: set[tuple[float, float]] = set()
        self._member_road: dict[str, tuple[str, datetime]] = {}   # last known road type per member
        self.language = messages.lang_of(hass.config.language)

    # ------------------------------------------------------------------ lifecycle
    @property
    def signal(self) -> str:
        return SIGNAL_UPDATE.format(self.entry.entry_id)

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        saved = stored.get("members") or {}
        self.addresses = dict(stored.get("addresses") or {})
        for item in stored.get("roads") or []:
            try:
                lat, lon, road, when = item
                self._road_cache[(float(lat), float(lon))] = (str(road), datetime.fromisoformat(when))
            except (TypeError, ValueError):
                continue
        adopted = False
        for member_id in self.members:
            tracker = self.trackers[member_id] = MemberTracker.from_dict(saved.get(member_id) or {})
            # places added (the entry reloads) while someone is already inside them: no arrival alert
            adopted |= tracker.adopt_places(self.place_list(member_id))
        if adopted:
            self._schedule_save()
        self._index_entities()
        if self._by_entity:
            self._unsubs.append(async_track_state_change_event(self.hass, list(self._by_entity), self._on_state))
        self._unsubs.append(async_track_time_interval(self.hass, self._on_tick, TICK))
        for member_id in self.members:
            self._update_member(member_id)
            if not self.addresses.get(member_id):
                # e.g. after turning off «show zone names»: look up the address without waiting for a move
                self._maybe_geocode(member_id)

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for cancel in list(self._pending_sends):
            cancel()
        self._pending_sends.clear()
        await self._store.async_save(self._data_to_store())

    def _data_to_store(self) -> dict[str, Any]:
        return {
            "members": {mid: t.to_dict() for mid, t in self.trackers.items()},
            "addresses": self.addresses,
            "roads": [[lat, lon, road, when.isoformat()] for (lat, lon), (road, when) in self._road_cache.items()],
        }

    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._data_to_store, SAVE_DELAY)

    def _index_entities(self) -> None:
        """Entities to listen to per member: the person and the tracker it takes its location from."""
        self._by_entity = {}
        for member in self.members.values():
            entities = {member.entity_id}
            if member.entity_id.startswith("person."):
                for tracker in self._person_trackers(member.entity_id):
                    entities.add(tracker)
            for ent in entities:
                self._by_entity.setdefault(ent, []).append(member.id)

    def _person_trackers(self, person_id: str) -> list[str]:
        state = self.hass.states.get(person_id)
        # The person already copies its tracker's location; listening to the tracker too catches
        # speed or battery changes that don't move the person.
        if state is not None and state.attributes.get("device_trackers"):
            return list(state.attributes["device_trackers"])
        return []

    # ------------------------------------------------------------------ options
    def settings_for(self, member: MemberConfig, fix: Fix | None = None) -> Settings:
        o = self.options
        limit, road = member.speed_limit, None
        if member.two_limits and fix is not None:
            # Street or highway limit depending on the road. While a new stretch is being looked up, the
            # member's last known road type is used; if nothing recent is known, the (higher) highway
            # limit is used, so an unknown road never causes a false alert.
            road = self._road_cache_get(fix.lat, fix.lon)
            if road is not None:
                self._member_road[member.id] = (road, fix.time)
            elif (last := self._member_road.get(member.id)) and fix.time - last[1] <= MEMBER_ROAD_TTL:
                road = last[0]
            limit = member.speed_limit if road == geocode.ROAD_STREET else member.highway_limit
        return Settings(
            moving_speed=float(o.get(CONF_MOVING_SPEED, DEFAULT_MOVING_SPEED)),
            driving_speed=float(o.get(CONF_DRIVING_SPEED, DEFAULT_DRIVING_SPEED)),
            stop_minutes=float(o.get(CONF_STOP_MINUTES, DEFAULT_STOP_MINUTES)),
            start_distance=float(o.get(CONF_START_DISTANCE, DEFAULT_START_DISTANCE)),
            max_accuracy=float(o.get(CONF_MAX_ACCURACY, DEFAULT_MAX_ACCURACY)),
            low_battery=int(o.get(CONF_LOW_BATTERY, DEFAULT_LOW_BATTERY)),
            speed_limit=limit,
            road=road,
        )

    # ------------------------------------------------------------------ road types
    @staticmethod
    def _road_cell(lat: float, lon: float) -> tuple[float, float]:
        return round(lat, 3), round(lon, 3)   # ~100 m cells

    def _road_cache_get(self, lat: float, lon: float) -> str | None:
        hit = self._road_cache.get(self._road_cell(lat, lon))
        if hit is None or dt_util.utcnow() - hit[1] > ROAD_CACHE_TTL:
            return None
        return hit[0]

    @callback
    def _maybe_lookup_road(self, member: MemberConfig) -> None:
        """Looks up the road type only when someone with two limits goes faster than the street limit."""
        tracker = self.trackers[member.id]
        fix = tracker.last_fix
        if not member.two_limits or fix is None or tracker.trip is None:
            return
        if (tracker.speed_kmh or 0) <= member.speed_limit:
            return
        cell = self._road_cell(fix.lat, fix.lon)
        if cell in self._road_lookups or self._road_cache_get(fix.lat, fix.lon) is not None:
            return
        self._road_lookups.add(cell)
        self.entry.async_create_background_task(
            self.hass, self._lookup_road(member.id, cell, fix), f"{DOMAIN} road {cell}")

    async def _lookup_road(self, member_id: str, cell: tuple[float, float], fix: Fix) -> None:
        try:
            road = await geocode.road_type(async_get_clientsession(self.hass), fix.lat, fix.lon)
            if road is not None:
                self._member_road[member_id] = (road, fix.time)
                if len(self._road_cache) > ROAD_CACHE_MAX:
                    self._road_cache.clear()
                self._road_cache[cell] = (road, dt_util.utcnow())
                self._schedule_save()
        finally:
            self._road_lookups.discard(cell)

    def place_list(self, member_id: str | None = None) -> list[Place]:
        """Places with current coordinates (places linked to a zone follow it if it changes)."""
        result = []
        for cfg in self.places.values():
            lat, lon, radius = cfg.latitude, cfg.longitude, cfg.radius
            if cfg.zone:
                zone = self.hass.states.get(cfg.zone)
                if zone is None:
                    continue
                lat = zone.attributes.get(ATTR_LATITUDE)
                lon = zone.attributes.get(ATTR_LONGITUDE)
                radius = zone.attributes.get("radius", radius)
            if lat is None or lon is None:
                continue
            result.append(Place(cfg.id, cfg.name, float(lat), float(lon), float(radius), cfg.instant))
        return result

    # ------------------------------------------------------------------ reading positions
    def _source_state(self, state: State) -> State | None:
        if state.entity_id.startswith("person."):
            source = state.attributes.get("source")
            return self.hass.states.get(source) if source else None
        return state

    def _battery_entity(self, tracker_id: str) -> str | None:
        """Battery sensor of the same phone (Companion app), if any."""
        if tracker_id in self._battery_entities:
            return self._battery_entities[tracker_id]
        found = None
        registry = er.async_get(self.hass)
        entry = registry.async_get(tracker_id)
        if entry is not None and entry.device_id:
            candidates = [
                e for e in er.async_entries_for_device(registry, entry.device_id)
                if e.domain == "sensor" and (e.device_class or e.original_device_class) == "battery"
            ]
            candidates.sort(key=lambda e: 0 if "level" in (e.unique_id or "") else 1)
            if candidates:
                found = candidates[0].entity_id
        self._battery_entities[tracker_id] = found
        return found

    def read_fix(self, member: MemberConfig) -> Fix | None:
        state = self.hass.states.get(member.entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        attrs = state.attributes
        try:
            lat, lon = float(attrs[ATTR_LATITUDE]), float(attrs[ATTR_LONGITUDE])
        except (KeyError, TypeError, ValueError):
            return None
        source = self._source_state(state) or state
        sattrs = source.attributes
        accuracy = attrs.get("gps_accuracy", sattrs.get("gps_accuracy"))
        speed = sattrs.get("speed")
        speed_kmh = None
        if isinstance(speed, (int, float)) and speed >= 0:
            speed_kmh = float(speed) * 3.6   # the Companion app reports meters per second
        battery = sattrs.get("battery_level", sattrs.get("battery"))
        if battery is None and source.entity_id.startswith("device_tracker."):
            if (bat_id := self._battery_entity(source.entity_id)) and (bat := self.hass.states.get(bat_id)):
                battery = bat.state
        try:
            battery = int(float(battery)) if battery is not None else None
        except (TypeError, ValueError):
            battery = None
        when = max(state.last_updated, source.last_updated)
        return Fix(
            lat=lat, lon=lon, time=dt_util.as_local(when),
            accuracy=float(accuracy) if isinstance(accuracy, (int, float)) else None,
            speed_kmh=speed_kmh, battery=battery,
        )

    # ------------------------------------------------------------------ HA events
    @callback
    def _on_state(self, event: HaEvent[EventStateChangedData]) -> None:
        for member_id in self._by_entity.get(event.data["entity_id"], []):
            self._update_member(member_id)

    @callback
    def _update_member(self, member_id: str) -> None:
        member = self.members[member_id]
        fix = self.read_fix(member)
        if fix is None:
            return
        tracker = self.trackers[member_id]
        last = tracker.last_fix
        if last is not None and last.time == fix.time and (last.lat, last.lon) == (fix.lat, fix.lon) \
                and last.battery == fix.battery and last.speed_kmh == fix.speed_kmh:
            return
        was_initialized = tracker.initialized
        events = tracker.process(fix, self.place_list(member_id), self.settings_for(member, fix))
        self._handle(member, events)
        self._maybe_lookup_road(member)
        if not was_initialized or any(e.type in (EV_TRIP_END, EV_LEAVE) for e in events):
            self._maybe_geocode(member_id)
        async_dispatcher_send(self.hass, self.signal)
        self._schedule_save()

    @callback
    def _on_tick(self, now: datetime) -> None:
        changed = False
        local = dt_util.as_local(now)
        for member_id, tracker in self.trackers.items():
            member = self.members[member_id]
            events = tracker.tick(local, self.place_list(member_id), self.settings_for(member))
            if events:
                changed = True
                self._handle(member, events)
                self._maybe_geocode(member_id)
        if changed:
            async_dispatcher_send(self.hass, self.signal)
            self._schedule_save()

    # ------------------------------------------------------------------ addresses
    @callback
    def _maybe_geocode(self, member_id: str) -> None:
        if not self.options.get(CONF_REVERSE_GEOCODE, True) or member_id in self._geocoding:
            return
        tracker = self.trackers[member_id]
        if tracker.last_fix is None or tracker.places or tracker.trip is not None:
            return
        if self.current_zone(member_id) is not None:
            return   # the zone name is shown instead, no need to look up the address
        self._geocoding.add(member_id)
        self.entry.async_create_background_task(
            self.hass, self._geocode(member_id), f"{DOMAIN} address {member_id}"
        )

    async def _geocode(self, member_id: str) -> None:
        try:
            fix = self.trackers[member_id].last_fix
            if fix is None:
                return
            address = await geocode.reverse(async_get_clientsession(self.hass), fix.lat, fix.lon, self.language)
            if address:
                self.addresses[member_id] = address
                async_dispatcher_send(self.hass, self.signal)
                self._schedule_save()
        finally:
            self._geocoding.discard(member_id)

    # ------------------------------------------------------------------ alerts
    def current_place_name(self, member_id: str) -> str | None:
        ids = self.trackers[member_id].current_place_ids() if member_id in self.trackers else []
        return self.places[ids[0]].name if ids and ids[0] in self.places else None

    def current_zone(self, member_id: str) -> State | None:
        """The Home Assistant zone the member is in (smallest one), when the option is on and they are at none
        of the circle's places. Passive zones are skipped, like Home Assistant does for persons."""
        if not self.options.get(CONF_SHOW_ZONES, True):
            return None
        tracker = self.trackers.get(member_id)
        if tracker is None or tracker.last_fix is None or tracker.places:
            return None
        fix = tracker.last_fix
        found: tuple[float, State] | None = None
        for zone in self.hass.states.async_all("zone"):
            attrs = zone.attributes
            if attrs.get("passive"):
                continue
            try:
                lat, lon = float(attrs[ATTR_LATITUDE]), float(attrs[ATTR_LONGITUDE])
                radius = float(attrs.get("radius", 0))
            except (KeyError, TypeError, ValueError):
                continue
            if distance_m(lat, lon, fix.lat, fix.lon) <= radius and (found is None or radius < found[0]):
                found = (radius, zone)
        return found[1] if found else None

    def current_zone_name(self, member_id: str) -> str | None:
        zone = self.current_zone(member_id)
        return zone.name if zone is not None else None

    def _recipients(self, subject: MemberConfig, chosen: list[str]) -> list[MemberConfig]:
        notify_self = bool(self.options.get(CONF_NOTIFY_SELF, False))
        pool = [self.members[m] for m in chosen if m in self.members] if chosen else list(self.members.values())
        return [m for m in pool if m.receive_alerts and m.notify and (notify_self or m.id != subject.id)]

    def _wants(self, member: MemberConfig, event: Event) -> tuple[bool, list[str]]:
        """Is this event announced? And to whom (ids; empty = everyone)."""
        o = self.options
        if event.type in (EV_ARRIVE, EV_LEAVE):
            place = self.places.get(event.place_id or "")
            if place is None:
                return False, []
            if place.watch and member.id not in place.watch:
                return False, []
            enabled = place.notify_arrive if event.type == EV_ARRIVE else place.notify_leave
            return enabled, place.recipients
        safety = list(o.get(CONF_SAFETY_RECIPIENTS) or [])
        if event.type in (EV_TRIP_START, EV_TRIP_END):
            return bool(o.get(CONF_NOTIFY_TRIPS, False)), safety
        if event.type == EV_SPEEDING:
            return bool(o.get(CONF_NOTIFY_SPEEDING, True)), safety
        if event.type == EV_LOW_BATTERY:
            return bool(o.get(CONF_NOTIFY_BATTERY, True)), safety
        return True, []   # check-in and SOS go to everyone

    @callback
    def _handle(self, member: MemberConfig, events: list[Event]) -> None:
        tracker = self.trackers[member.id]
        for event in events:
            fix = tracker.last_fix
            payload = {
                "type": event.type,
                "member": member.name,
                "member_id": member.id,
                "entity_id": member.entity_id,
                "place": event.place_name,
                "place_id": event.place_id,
                "time": event.time.isoformat(),
                **({"latitude": fix.lat, "longitude": fix.lon} if fix else {}),
                **event.data,
            }
            self.hass.bus.async_fire(EVENT_NAME, payload)
            enabled, chosen = self._wants(member, event)
            if not enabled:
                continue
            title, message = messages.build(event.type, self.language, member.name, event.time,
                                            event.place_name, event.data)
            point = (fix.lat, fix.lon) if fix else None
            if event.type in COMPANION_EVENTS:
                self._send_later(member, chosen, event, title, message, point)
            else:
                self._send(member, chosen, event.type, title, message, point)

    def _send_later(self, member: MemberConfig, chosen: list[str], event: Event, title: str, message: str,
                    point: tuple[float, float] | None) -> None:
        """Waits a bit before alerting, to learn who was with the person and skip them."""
        cancel: Callable[[], None] | None = None

        @callback
        def _fire(_now: datetime) -> None:
            self._pending_sends.discard(cancel)
            skip = {r.id for r in self.members.values() if r.id != member.id and self.together(r.id, member.id, event)}
            self._send(member, chosen, event.type, title, message, point, skip=skip)

        cancel = async_call_later(self.hass, TOGETHER_GRACE_S, _fire)
        self._pending_sends.add(cancel)

    def together(self, other_id: str, subject_id: str, event: Event) -> bool:
        """Was «other» with «subject» for this event? (arrived, left or travel together)."""
        other, subject = self.trackers.get(other_id), self.trackers.get(subject_id)
        if other is None or subject is None or other.last_fix is None or subject.last_fix is None:
            return False
        window = timedelta(minutes=TOGETHER_WINDOW_MIN)
        if event.type == EV_ARRIVE and event.place_id:
            since = other.places.get(event.place_id) or other.pending.get(event.place_id)
            return since is not None and abs(since - event.time) <= window
        a, b = other.last_fix, subject.last_fix
        near = (abs(a.time - b.time) <= window
                and distance_m(a.lat, a.lon, b.lat, b.lon) <= TOGETHER_M + (a.accuracy or 0) + (b.accuracy or 0))
        if event.type == EV_LEAVE and event.place_id:
            # Left together: the other one is no longer at the place either and is nearby.
            return near and event.place_id not in other.places
        if event.type == EV_TRIP_START:
            return near and other.trip is not None
        return near

    def _send(self, subject: MemberConfig, chosen: list[str], event_type: str, title: str, message: str,
              point: tuple[float, float] | None, skip: set[str] | None = None) -> int:
        targets = [t for t in self._recipients(subject, chosen) if t.id not in (skip or set())]
        data: dict[str, Any] = {"tag": f"{DOMAIN}_{event_type}_{subject.id}", "group": DOMAIN}
        if point is not None:
            url = messages.maps_url(*point)
            data.update({"url": url, "clickAction": url})
        if event_type == EV_SOS:
            data.update({
                "priority": "high", "ttl": 0, "channel": "alarm_stream_max",   # Android: alarm sound at max volume
                "push": {"sound": {"name": "default", "critical": 1, "volume": 1.0},
                         "interruption-level": "critical"},
            })
        elif event_type == EV_SPEEDING:
            data.update({"priority": "high", "push": {"interruption-level": "time-sensitive"}})
        sent = 0
        for target in targets:
            for service in target.notify:
                svc = notify_service(service)
                if not self.hass.services.has_service("notify", svc):
                    _LOGGER.warning("Notification service notify.%s for %s does not exist", svc, target.name)
                    continue
                self.hass.async_create_task(
                    self._call_notify(svc, {"title": title, "message": message, "data": data}),
                    f"{DOMAIN} alert {svc}",
                )
                sent += 1
        return sent

    async def _call_notify(self, service: str, data: dict[str, Any]) -> None:
        try:
            await self.hass.services.async_call("notify", service, data, blocking=True)
        except Exception as err:  # noqa: BLE001 - one failing phone must not affect the rest
            _LOGGER.warning("Could not send the alert through notify.%s: %s", service, err)

    # ------------------------------------------------------------------ manual actions
    async def async_check_in(self, member_id: str, note: str = "", sos: bool = False) -> None:
        member = self.members[member_id]
        tracker = self.trackers[member_id]
        fix = self.read_fix(member) or tracker.last_fix
        place = self.current_place_name(member_id) or self.current_zone_name(member_id)
        address = None
        if fix is not None and place is None:
            address = await geocode.reverse(async_get_clientsession(self.hass), fix.lat, fix.lon, self.language)
            if address:
                self.addresses[member_id] = address
        where = messages.where_text(self.language, place, address or self.addresses.get(member_id))
        event_type = EV_SOS if sos else EV_CHECK_IN
        now = dt_util.now()
        title, message = messages.build(event_type, self.language, member.name, now, place, where=where, note=note)
        self.hass.bus.async_fire(EVENT_NAME, {
            "type": event_type, "member": member.name, "member_id": member.id, "entity_id": member.entity_id,
            "place": place, "address": address, "note": note, "time": now.isoformat(),
            **({"latitude": fix.lat, "longitude": fix.lon} if fix else {}),
        })
        self._send(member, [], event_type, title, message, (fix.lat, fix.lon) if fix else None)
        async_dispatcher_send(self.hass, self.signal)

    def member_by_entity(self, entity_id: str) -> MemberConfig | None:
        for member in self.members.values():
            if member.entity_id == entity_id:
                return member
        return None
