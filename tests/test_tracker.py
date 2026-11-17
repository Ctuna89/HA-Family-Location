"""Tests of the tracking logic (without Home Assistant)."""

from datetime import datetime, timedelta, timezone

from custom_components.family_location.tracker import Fix, MemberTracker, Place, Settings, distance_m

T0 = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)
HOME = Place("home", "Casa", -33.4372, -70.6506, 150, instant=True)
WORK = Place("work", "Trabajo", -33.4150, -70.6030, 150)   # ~5 km to the NE
PLACES = [HOME, WORK]
S = Settings(speed_limit=100)


def fix(lat, lon, minutes, speed=None, acc=10, battery=None):
    return Fix(lat, lon, T0 + timedelta(minutes=minutes), acc, speed, battery)


def types(events):
    return [e.type for e in events]


def interp(a, b, f):
    return a.lat + (b.lat - a.lat) * f, a.lon + (b.lon - a.lon) * f


def test_distance():
    assert 4500 < distance_m(HOME.lat, HOME.lon, WORK.lat, WORK.lon) < 5500


def test_first_fix_sets_place_without_alerts():
    t = MemberTracker()
    assert t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S) == []
    assert t.current_place_ids() == ["home"]
    assert t.status == "still"


def test_commute_leave_trip_arrive():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S)
    all_events = []
    for i in range(1, 11):
        lat, lon = interp(HOME, WORK, i / 10)
        all_events += t.process(fix(lat, lon, i, speed=40), PLACES, S)
        if i == 5:
            assert t.status == "driving"
            assert t.moving
    # arrives at work and stops: the arrival is only confirmed after 5 minutes still
    all_events += t.process(fix(WORK.lat, WORK.lon, 12, speed=0), PLACES, S)
    assert "arrive" not in types(all_events)
    assert t.tick(T0 + timedelta(minutes=14), PLACES, S) == []
    all_events += t.tick(T0 + timedelta(minutes=16), PLACES, S)
    kinds = types(all_events)
    assert kinds[:2] == ["leave", "trip_start"]
    assert kinds[-2:] == ["arrive", "trip_end"]
    assert all_events[-2].time == T0 + timedelta(minutes=10)   # time they entered the place
    end = all_events[-1].data
    assert end["from"] == "Casa" and end["to"] == "Trabajo"
    assert 4 < end["distance_km"] < 7
    assert end["max_speed_kmh"] == 40
    assert t.status == "still" and t.current_place_ids() == ["work"]
    assert t.trips_today == 1 and t.distance_today_m > 4000


def test_traffic_light_does_not_end_trip():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S)
    ev = []
    lat, lon = interp(HOME, WORK, 0.3)
    ev += t.process(fix(lat, lon, 2, speed=40), PLACES, S)
    for m in (3, 4, 5, 6):          # 4 minutes stopped at a traffic light / jam
        ev += t.process(fix(lat, lon, m, speed=0), PLACES, S)
        ev += t.tick(T0 + timedelta(minutes=m, seconds=30), PLACES, S)
    assert t.moving
    lat, lon = interp(HOME, WORK, 0.6)
    ev += t.process(fix(lat, lon, 8, speed=45), PLACES, S)
    assert types(ev).count("trip_start") == 1 and "trip_end" not in types(ev)


def test_passing_by_a_place_is_not_an_arrival():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S)
    ev = []
    lat, lon = interp(HOME, WORK, 0.5)
    ev += t.process(fix(lat, lon, 5, speed=40), PLACES, S)
    ev += t.process(fix(WORK.lat, WORK.lon, 10, speed=0), PLACES, S)   # traffic light in front of work
    ev += t.tick(T0 + timedelta(minutes=12), PLACES, S)
    ev += t.process(fix(WORK.lat + 0.01, WORK.lon + 0.01, 13, speed=50), PLACES, S)   # drives on
    ev += t.tick(T0 + timedelta(minutes=30), PLACES, S)
    assert "arrive" not in types(ev) and types(ev).count("leave") == 1   # only left Home
    assert t.current_place_ids() == []


def test_home_arrival_is_immediate():
    t = MemberTracker()
    t.process(fix(WORK.lat, WORK.lon, 0), PLACES, S)
    lat, lon = interp(WORK, HOME, 0.5)
    t.process(fix(lat, lon, 5, speed=40), PLACES, S)
    ev = t.process(fix(HOME.lat, HOME.lon, 10, speed=20), PLACES, S)
    assert types(ev) == ["arrive"] and ev[0].place_name == "Casa"
    assert t.moving   # the trip ends later, after 5 minutes still


def test_gps_jitter_does_not_start_trip_or_leave():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S)
    events = []
    for i in range(1, 20):
        events += t.process(fix(HOME.lat + 0.0004 * (-1) ** i, HOME.lon, i, acc=30), PLACES, S)
    assert events == []
    assert t.status == "still"


def test_inaccurate_fix_ignored():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S)
    assert t.process(fix(WORK.lat, WORK.lon, 1, acc=1500), PLACES, S) == []
    assert t.current_place_ids() == ["home"]


def test_speeding_needs_two_readings_and_has_cooldown():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S)
    ev = []
    for i, speed in enumerate([60, 120, 125, 130, 90, 130, 131], start=1):
        lat, lon = interp(HOME, WORK, i / 20)
        ev += t.process(fix(lat, lon, i, speed=speed), PLACES, S)
    speeding = [e for e in ev if e.type == "speeding"]
    assert len(speeding) == 1                    # the second episode falls within the cooldown
    assert speeding[0].data["speed_kmh"] == 125
    assert t.speeding


def test_trip_ends_after_stop_minutes():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S)
    lat, lon = interp(HOME, WORK, 0.5)
    t.process(fix(lat, lon, 5, speed=30), PLACES, S)
    assert t.moving
    t.process(fix(lat, lon, 6, speed=0), PLACES, S)
    assert t.tick(T0 + timedelta(minutes=8), PLACES, S) == []
    ev = t.tick(T0 + timedelta(minutes=12), PLACES, S)
    assert types(ev) == ["trip_end"] and ev[0].data["to"] is None
    assert not t.moving


def test_derived_speed_without_reported_speed():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S)
    lat, lon = interp(HOME, WORK, 0.2)      # ~1 km in 1 minute ≈ 60 km/h
    t.process(fix(lat, lon, 1), PLACES, S)
    assert 50 < t.speed_kmh < 70


def test_low_battery_alert_once():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0, battery=50), PLACES, S)
    assert types(t.process(fix(HOME.lat, HOME.lon, 1, battery=14), PLACES, S)) == ["low_battery"]
    assert t.process(fix(HOME.lat, HOME.lon, 2, battery=10), PLACES, S) == []
    t.process(fix(HOME.lat, HOME.lon, 3, battery=40), PLACES, S)
    assert types(t.process(fix(HOME.lat, HOME.lon, 4, battery=12), PLACES, S)) == ["low_battery"]


def test_roundtrip_storage():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), PLACES, S)
    lat, lon = interp(HOME, WORK, 0.5)
    t.process(fix(lat, lon, 5, speed=30, battery=70), PLACES, S)
    copy = MemberTracker.from_dict(t.to_dict())
    assert copy.moving and copy.trip.start_place == "Casa"
    assert copy.battery == 70 and copy.last_fix == t.last_fix
    assert MemberTracker.from_dict({"places": "roto"}).initialized is False


def test_place_created_where_they_are_is_adopted_without_alert():
    t = MemberTracker()
    t.process(fix(WORK.lat, WORK.lon, 0), [HOME], S)   # only Home exists yet: at work they are «away»
    assert t.current_place_ids() == []
    assert t.adopt_places(PLACES) is True               # «Trabajo» is created while they are there
    assert t.current_place_ids() == ["work"]
    # their next position is not announced as an arrival
    assert t.process(fix(WORK.lat + 0.0002, WORK.lon, 60), PLACES, S) == []
    assert t.current_place_ids() == ["work"]


def test_place_created_where_they_are_is_adopted_on_next_position():
    # without calling adopt_places (e.g. the place appears between two positions), process() adopts it too
    t = MemberTracker()
    t.process(fix(WORK.lat, WORK.lon, 0), [HOME], S)
    assert t.process(fix(WORK.lat + 0.0002, WORK.lon, 60), PLACES, S) == []
    assert t.current_place_ids() == ["work"]


def test_place_created_elsewhere_still_announces_the_arrival():
    t = MemberTracker()
    t.process(fix(HOME.lat, HOME.lon, 0), [HOME], S)
    assert t.adopt_places(PLACES) is True                # «Trabajo» created from home
    assert t.current_place_ids() == ["home"]
    events = []
    for i in range(1, 11):
        lat, lon = interp(HOME, WORK, i / 10)
        events += t.process(fix(lat, lon, i, speed=40), PLACES, S)
    events += t.process(fix(WORK.lat, WORK.lon, 12, speed=0), PLACES, S)
    events += t.tick(T0 + timedelta(minutes=16), PLACES, S)
    assert "arrive" in types(events)
    assert t.current_place_ids() == ["work"]


def test_stored_state_from_older_version_adopts_places_silently():
    # state saved by 0.2.0 has no «known_places»: places they are in are taken without alerts
    t = MemberTracker()
    t.process(fix(WORK.lat, WORK.lon, 0), [HOME], S)
    data = t.to_dict()
    del data["known_places"]
    old = MemberTracker.from_dict(data)
    assert old.known_places is None
    assert old.process(fix(WORK.lat + 0.0002, WORK.lon, 60), PLACES, S) == []
    assert old.current_place_ids() == ["work"]
    assert MemberTracker.from_dict(old.to_dict()).known_places == {"home", "work"}
