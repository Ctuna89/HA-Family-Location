"""Tests inside Home Assistant (require pytest-homeassistant-custom-component)."""

from unittest.mock import patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import ConfigSubentryData  # noqa: E402
from homeassistant.core import HomeAssistant, ServiceCall, callback  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.setup import async_setup_component  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed  # noqa: E402

from datetime import timedelta  # noqa: E402

from custom_components.family_location.const import DOMAIN, EVENT_NAME  # noqa: E402
from custom_components.family_location.config_flow import default_options  # noqa: E402
from custom_components.family_location.geocode import GeoResult  # noqa: E402

HOME = (-33.4372, -70.6506)
WORK = (-33.4150, -70.6030)


def tracker(hass, entity, lat, lon, speed=None, battery=None, acc=10):
    attrs = {"latitude": lat, "longitude": lon, "gps_accuracy": acc, "source_type": "gps"}
    if speed is not None:
        attrs["speed"] = speed / 3.6
    if battery is not None:
        attrs["battery_level"] = battery
    hass.states.async_set(entity, "not_home", attrs)


def capture_notify(hass, name):
    calls: list[ServiceCall] = []

    async def _svc(call):
        calls.append(call)

    hass.services.async_register("notify", name, _svc)
    return calls


def member(entity, title, notify, speed_limit=0):
    return ConfigSubentryData(subentry_type="member", title=title, unique_id=entity,
                              data={"entity_id": entity, "notify": [notify], "receive_alerts": True,
                                    "speed_limit": speed_limit})


async def advance(hass, freezer, seconds):
    """Moves the clock forward 30 s at a time (like the integration's periodic check)."""
    for _ in range(int(seconds // 30)):
        freezer.tick(timedelta(seconds=30))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()


async def setup_circle(hass: HomeAssistant, speed_limit=100, extra=(), highway_limit=0, **options):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Familia", data={}, options={**default_options(), **options},
        subentries_data=[
            ConfigSubentryData(subentry_type="member", title="James", unique_id="device_tracker.james",
                               data={"entity_id": "device_tracker.james", "notify": ["notify.mobile_app_james"],
                                     "receive_alerts": True, "speed_limit": speed_limit,
                                     "highway_speed_limit": highway_limit}),
            ConfigSubentryData(subentry_type="member", title="Janet", unique_id="device_tracker.janet",
                               data={"entity_id": "device_tracker.janet", "notify": ["notify.mobile_app_janet"],
                                     "receive_alerts": True, "speed_limit": 0}),
            ConfigSubentryData(subentry_type="place", title="Casa", unique_id=None,
                               data={"location": {"latitude": HOME[0], "longitude": HOME[1], "radius": 150},
                                     "notify_arrive": True, "notify_leave": True, "arrive_instant": True,
                                     "watch": [], "recipients": []}),
            ConfigSubentryData(subentry_type="place", title="Trabajo", unique_id=None,
                               data={"location": {"latitude": WORK[0], "longitude": WORK[1], "radius": 150},
                                     "notify_arrive": True, "notify_leave": False, "watch": [], "recipients": []}),
            *extra,
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_arrive_leave_speeding_and_entities(hass: HomeAssistant, freezer):
    hass.config.language = "es"
    james_calls = capture_notify(hass, "mobile_app_james")
    janet_calls = capture_notify(hass, "mobile_app_janet")
    events = []
    hass.bus.async_listen(EVENT_NAME, callback(lambda e: events.append(e.data)))
    tracker(hass, "device_tracker.james", *HOME, battery=80)
    tracker(hass, "device_tracker.janet", *HOME)

    with patch("custom_components.family_location.engine.geocode.reverse", return_value="Av. Siempre Viva 742"):
        await setup_circle(hass)
        assert hass.states.get("sensor.james_lugar").state == "Casa"
        # the map card links the person to their member sensors through this attribute
        assert hass.states.get("sensor.james_lugar").attributes["tracked_entity"] == "device_tracker.james"
        assert hass.states.get("sensor.james_estado").state == "still"
        assert hass.states.get("binary_sensor.casa_hay_alguien").state == "on"
        assert hass.states.get("sensor.casa_personas").state == "2"
        assert hass.states.get("sensor.james_bateria_del_telefono").state == "80"

        # James leaves home for work; halfway he goes 130 km/h twice.
        for i, speed in enumerate([40, 130, 132, 50, 40], start=1):
            f = i / 5
            freezer.tick(timedelta(seconds=60))
            tracker(hass, "device_tracker.james", HOME[0] + (WORK[0] - HOME[0]) * f,
                    HOME[1] + (WORK[1] - HOME[1]) * f, speed=speed)
            await hass.async_block_till_done()
        assert hass.states.get("binary_sensor.james_en_movimiento").state == "on"
        tracker(hass, "device_tracker.james", *WORK, speed=0)
        await hass.async_block_till_done()
        await advance(hass, freezer, 120)
        assert hass.states.get("sensor.james_lugar").state != "Trabajo"   # not confirmed yet
        await advance(hass, freezer, 400)   # 5 minutes stopped
    kinds = [e["type"] for e in events]
    assert kinds == ["leave", "trip_start", "speeding", "arrive", "trip_end"]
    titles = [c.data["title"] for c in janet_calls]
    # speeding is alerted right away; arrivals and departures wait 90 s in case someone was with him
    assert titles == ["⚠️ Exceso de velocidad: James", "🚶 James salió de Casa", "📍 James llegó a Trabajo"]
    assert "maps" in janet_calls[0].data["data"]["url"]
    assert james_calls == []   # nobody is alerted about themselves
    assert hass.states.get("sensor.james_lugar").state == "Trabajo"
    last = hass.states.get("sensor.james_ultimo_viaje")
    assert last.attributes["from"] == "Casa" and last.attributes["to"] == "Trabajo"
    assert float(last.state) > 4
    assert hass.states.get("sensor.casa_personas").state == "1"


async def test_check_in_and_sos(hass: HomeAssistant):
    hass.config.language = "es"
    calls = capture_notify(hass, "mobile_app_janet")
    capture_notify(hass, "mobile_app_james")
    tracker(hass, "device_tracker.james", -33.45, -70.66)
    tracker(hass, "device_tracker.janet", *HOME)
    with patch("custom_components.family_location.engine.geocode.reverse", return_value="Av. Matta 100, Santiago"):
        await setup_circle(hass)
        await hass.services.async_call(DOMAIN, "check_in", {"entity_id": "device_tracker.james"}, blocking=True)
        await hass.services.async_call("button", "press", {"entity_id": "button.james_pedir_ayuda"}, blocking=True)
        await hass.async_block_till_done()
    assert calls[0].data["message"] == "James está cerca de Av. Matta 100, Santiago."
    assert calls[1].data["title"] == "🆘 James pide ayuda"
    assert calls[1].data["data"]["push"]["sound"]["critical"] == 1        # iPhone: critical alert
    # Android: «alarm_stream» is the only notification channel the Companion app plays on the alarm stream
    # («alarm_stream_max» only applies to spoken TTS messages)
    assert calls[1].data["data"]["channel"] == "alarm_stream"
    assert hass.states.get("sensor.james_lugar").state == "Av. Matta 100, Santiago"


@pytest.fixture(autouse=True)
def _no_network():
    with patch("custom_components.family_location.engine.geocode.reverse", return_value=None):
        yield


async def test_config_flow_creates_members_and_home(hass: HomeAssistant):
    hass.config.language = "es"
    assert await async_setup_component(hass, "zone", {})
    hass.states.async_set("person.james", "home", {"friendly_name": "James", "latitude": hass.config.latitude,
                                                     "longitude": hass.config.longitude, "device_trackers": []})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Familia", "members": ["person.james"], "add_home": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    subs = {s.title: s for s in entry.subentries.values()}
    assert set(subs) == {"James", "Casa"}
    assert subs["Casa"].data["zone"] == "zone.home"
    await hass.async_block_till_done()
    assert hass.states.get("sensor.james_lugar").state == "Casa"


async def test_place_subentry_by_address(hass: HomeAssistant):
    hass.config.language = "es"
    tracker(hass, "device_tracker.james", *HOME)
    tracker(hass, "device_tracker.janet", *HOME)
    entry = await setup_circle(hass)
    janet = next(s.subentry_id for s in entry.subentries.values() if s.title == "Janet")

    flow = await hass.config_entries.subentries.async_init((entry.entry_id, "place"), context={"source": "user"})
    with patch("custom_components.family_location.config_flow.geocode.geocode", return_value=None):
        res = await hass.config_entries.subentries.async_configure(
            flow["flow_id"], {"name": "Colegio", "address": "nada", "radius": 200})
    assert res["errors"] == {"address": "address_not_found"}
    with patch("custom_components.family_location.config_flow.geocode.geocode",
               return_value=GeoResult(-33.40, -70.57, "Colegio X, Las Condes")):
        res = await hass.config_entries.subentries.async_configure(
            flow["flow_id"], {"name": "Colegio", "address": "Colegio X, Las Condes", "radius": 200})
    assert res["step_id"] == "location"
    assert res["description_placeholders"]["found"] == "Colegio X, Las Condes"
    res = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"location": {"latitude": -33.401, "longitude": -70.571, "radius": 180}})
    assert res["step_id"] == "alerts"
    res = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"notify_arrive": True, "notify_leave": False, "watch": [], "recipients": [janet]})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    place = next(s for s in entry.subentries.values() if s.title == "Colegio")
    assert place.data["location"] == {"latitude": -33.401, "longitude": -70.571, "radius": 180}
    assert place.data["recipients"] == [janet]
    assert hass.states.get("sensor.colegio_personas").state == "0"


async def test_member_subentry(hass: HomeAssistant):
    hass.config.language = "es"
    tracker(hass, "device_tracker.james", *HOME)
    tracker(hass, "device_tracker.janet", *HOME)
    tracker(hass, "device_tracker.hijo", *HOME)
    entry = await setup_circle(hass)
    flow = await hass.config_entries.subentries.async_init((entry.entry_id, "member"), context={"source": "user"})
    res = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"entity_id": "device_tracker.james", "notify": [], "receive_alerts": True, "speed_limit": 0})
    assert res["errors"] == {"entity_id": "already_member"}
    res = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"entity_id": "device_tracker.hijo", "name": "Tom", "notify": [],
                          "receive_alerts": False, "speed_limit": 90})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("sensor.tom_lugar").state == "Casa"
    assert hass.states.get("binary_sensor.tom_exceso_de_velocidad").state == "off"


async def test_options_flow(hass: HomeAssistant):
    tracker(hass, "device_tracker.james", *HOME)
    tracker(hass, "device_tracker.janet", *HOME)
    entry = await setup_circle(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    opts = {**default_options(), "notify_trips": True}
    res = await hass.config_entries.options.async_configure(flow["flow_id"], opts)
    assert res["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["notify_trips"] is True


async def test_place_reconfigure_keeps_location(hass: HomeAssistant):
    hass.config.language = "es"
    tracker(hass, "device_tracker.james", *HOME)
    tracker(hass, "device_tracker.janet", *HOME)
    entry = await setup_circle(hass)
    casa = next(s for s in entry.subentries.values() if s.title == "Casa")
    flow = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "place"), context={"source": "reconfigure", "subentry_id": casa.subentry_id})
    assert flow["step_id"] == "reconfigure"
    res = await hass.config_entries.subentries.async_configure(flow["flow_id"], {"name": "Hogar", "radius": 300})
    assert res["step_id"] == "location"
    res = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"location": {"latitude": HOME[0], "longitude": HOME[1], "radius": 300}})
    res = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"notify_arrive": False, "notify_leave": True, "watch": [], "recipients": []})
    assert res["type"] is FlowResultType.ABORT and res["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    updated = entry.subentries[casa.subentry_id]
    assert updated.title == "Hogar" and updated.data["location"]["radius"] == 300
    assert updated.data["notify_arrive"] is False
    assert hass.states.get("sensor.james_lugar").state == "Hogar"


async def test_no_alert_to_who_travels_together(hass: HomeAssistant, freezer):
    """James and Janet travel together from Home to Work: no alerts between them; Tom (at home) gets them."""
    hass.config.language = "es"
    james = capture_notify(hass, "mobile_app_james")
    janet = capture_notify(hass, "mobile_app_janet")
    tom = capture_notify(hass, "mobile_app_tom")
    for ent in ("james", "janet", "tom"):
        tracker(hass, f"device_tracker.{ent}", *HOME)
    await setup_circle(hass, speed_limit=0,
                       extra=[member("device_tracker.tom", "Tom", "notify.mobile_app_tom")])

    def both(lat, lon, speed):
        tracker(hass, "device_tracker.james", lat, lon, speed=speed)
        tracker(hass, "device_tracker.janet", lat + 0.0003, lon, speed=speed)

    for i in range(1, 6):
        f = i / 5
        freezer.tick(timedelta(seconds=60))
        both(HOME[0] + (WORK[0] - HOME[0]) * f, HOME[1] + (WORK[1] - HOME[1]) * f, 40)
        await hass.async_block_till_done()
    both(*WORK, 0)
    await hass.async_block_till_done()
    await advance(hass, freezer, 120)
    await advance(hass, freezer, 400)
    await advance(hass, freezer, 120)

    assert james == [] and janet == []
    titles = sorted(c.data["title"] for c in tom)
    assert titles == ["📍 James llegó a Trabajo", "📍 Janet llegó a Trabajo",
                      "🚶 James salió de Casa", "🚶 Janet salió de Casa"]


async def test_alert_when_not_together(hass: HomeAssistant, freezer):
    hass.config.language = "es"
    janet = capture_notify(hass, "mobile_app_janet")
    capture_notify(hass, "mobile_app_james")
    tracker(hass, "device_tracker.james", *HOME)
    tracker(hass, "device_tracker.janet", *HOME)
    await setup_circle(hass, speed_limit=0)
    tracker(hass, "device_tracker.james", HOME[0] + 0.01, HOME[1], speed=40)   # James leaves alone
    await hass.async_block_till_done()
    assert janet == []          # waits a bit in case he was accompanied
    await advance(hass, freezer, 120)
    assert [c.data["title"] for c in janet] == ["🚶 James salió de Casa"]


GYM = (-33.4250, -70.6200)


async def test_zone_name_instead_of_address(hass: HomeAssistant):
    """Inside a HA zone that isn't a place: the place sensor shows the zone name, not the address."""
    hass.config.language = "en"
    hass.states.async_set("zone.gym", "0", {"latitude": GYM[0], "longitude": GYM[1], "radius": 100,
                                            "friendly_name": "Gym", "passive": False})
    hass.states.async_set("zone.big_area", "0", {"latitude": GYM[0], "longitude": GYM[1], "radius": 3000,
                                                 "friendly_name": "Downtown", "passive": False})
    hass.states.async_set("zone.hidden", "0", {"latitude": GYM[0], "longitude": GYM[1], "radius": 50,
                                               "friendly_name": "Hidden", "passive": True})
    tracker(hass, "device_tracker.james", *GYM)
    tracker(hass, "device_tracker.janet", *HOME)
    with patch("custom_components.family_location.engine.geocode.reverse", return_value="1 Main St") as reverse:
        entry = await setup_circle(hass)
        state = hass.states.get("sensor.james_place")
        assert state.state == "Gym"                       # smallest active zone, passive ones skipped
        assert state.attributes["zone"] == "zone.gym"
        assert hass.states.get("sensor.janet_place").state == "Casa"   # circle places still win
        assert reverse.call_count == 0                    # no address lookup needed inside a zone

        hass.config_entries.async_update_entry(entry, options={**entry.options, "show_zones": False})
        await hass.async_block_till_done()
        assert hass.states.get("sensor.james_place").state == "1 Main St"


async def test_check_in_uses_zone_name(hass: HomeAssistant):
    hass.config.language = "en"
    calls = capture_notify(hass, "mobile_app_janet")
    capture_notify(hass, "mobile_app_james")
    hass.states.async_set("zone.gym", "0", {"latitude": GYM[0], "longitude": GYM[1], "radius": 100,
                                            "friendly_name": "Gym"})
    tracker(hass, "device_tracker.james", *GYM)
    tracker(hass, "device_tracker.janet", *HOME)
    await setup_circle(hass)
    await hass.services.async_call(DOMAIN, "check_in", {"entity_id": "device_tracker.james"}, blocking=True)
    await hass.async_block_till_done()
    assert calls[0].data["message"] == "James is at Gym."


async def test_street_and_highway_limits_and_leaderboard(hass: HomeAssistant, freezer):
    """60 km/h on streets, 120 on highways: 100 km/h on the highway is fine, on a street it's speeding."""
    hass.config.language = "en"
    janet = capture_notify(hass, "mobile_app_janet")
    capture_notify(hass, "mobile_app_james")
    tracker(hass, "device_tracker.james", *HOME)
    tracker(hass, "device_tracker.janet", *HOME)
    midway = (HOME[0] + WORK[0]) / 2

    async def road(_session, lat, lon):
        return "highway" if lat < midway else "street"

    with patch("custom_components.family_location.engine.geocode.road_type", side_effect=road) as lookup:
        await setup_circle(hass, speed_limit=60, highway_limit=120)
        for i in range(1, 11):
            f = i / 10
            freezer.tick(timedelta(seconds=30))
            tracker(hass, "device_tracker.james", HOME[0] + (WORK[0] - HOME[0]) * f,
                    HOME[1] + (WORK[1] - HOME[1]) * f, speed=100)
            await hass.async_block_till_done()
        assert lookup.call_count >= 5                    # only looked up while over the street limit
        await advance(hass, freezer, 120)

    speeding = [c.data for c in janet if c.data["title"].startswith("⚠️")]
    assert len(speeding) == 1
    assert speeding[0]["message"] == "James is going 100 km/h on a street (limit 60 km/h)."

    attrs = hass.states.get("sensor.james_speed").attributes
    assert attrs["speed_limit_kmh"] == 60 and attrs["highway_speed_limit_kmh"] == 120
    assert hass.states.get("sensor.james_speeding_this_week").state == "1"
    assert hass.states.get("sensor.james_top_speed_this_week").state == "100"
    board = hass.states.get("sensor.familia_weekly_leaderboard")
    assert board.state == "James"
    assert [r["name"] for r in board.attributes["ranking"]] == ["James", "Janet"]
    assert board.attributes["most_speeding"] == "James"
