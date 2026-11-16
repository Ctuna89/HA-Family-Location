"""Pruebas dentro de Home Assistant (requieren pytest-homeassistant-custom-component)."""

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
    """Avanza el reloj de a 30 s (como el chequeo periódico de la integración)."""
    for _ in range(int(seconds // 30)):
        freezer.tick(timedelta(seconds=30))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()


async def setup_circle(hass: HomeAssistant, speed_limit=100, extra=(), **options):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Familia", data={}, options={**default_options(), **options},
        subentries_data=[
            ConfigSubentryData(subentry_type="member", title="Jaime", unique_id="device_tracker.jaime",
                               data={"entity_id": "device_tracker.jaime", "notify": ["notify.mobile_app_jaime"],
                                     "receive_alerts": True, "speed_limit": speed_limit}),
            ConfigSubentryData(subentry_type="member", title="Jeanette", unique_id="device_tracker.jeanette",
                               data={"entity_id": "device_tracker.jeanette", "notify": ["notify.mobile_app_jeanette"],
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
    jaime_calls = capture_notify(hass, "mobile_app_jaime")
    jeanette_calls = capture_notify(hass, "mobile_app_jeanette")
    events = []
    hass.bus.async_listen(EVENT_NAME, callback(lambda e: events.append(e.data)))
    tracker(hass, "device_tracker.jaime", *HOME, battery=80)
    tracker(hass, "device_tracker.jeanette", *HOME)

    with patch("custom_components.family_location.engine.geocode.reverse", return_value="Av. Siempre Viva 742"):
        await setup_circle(hass)
        assert hass.states.get("sensor.jaime_lugar").state == "Casa"
        assert hass.states.get("sensor.jaime_estado").state == "quieto"
        assert hass.states.get("binary_sensor.casa_hay_alguien").state == "on"
        assert hass.states.get("sensor.casa_personas").state == "2"
        assert hass.states.get("sensor.jaime_bateria_del_telefono").state == "80"

        # Jaime sale de casa y va al trabajo; en la mitad va a 130 km/h dos veces.
        for i, speed in enumerate([40, 130, 132, 50, 40], start=1):
            f = i / 5
            freezer.tick(timedelta(seconds=60))
            tracker(hass, "device_tracker.jaime", HOME[0] + (WORK[0] - HOME[0]) * f,
                    HOME[1] + (WORK[1] - HOME[1]) * f, speed=speed)
            await hass.async_block_till_done()
        assert hass.states.get("binary_sensor.jaime_en_movimiento").state == "on"
        tracker(hass, "device_tracker.jaime", *WORK, speed=0)
        await hass.async_block_till_done()
        await advance(hass, freezer, 120)
        assert hass.states.get("sensor.jaime_lugar").state != "Trabajo"   # aún no se confirma
        await advance(hass, freezer, 400)   # 5 minutos detenido
    kinds = [e["type"] for e in events]
    assert kinds == ["leave", "trip_start", "speeding", "arrive", "trip_end"]
    titles = [c.data["title"] for c in jeanette_calls]
    # el exceso se avisa al tiro; llegadas y salidas esperan 90 s por si alguien iba acompañándolo
    assert titles == ["⚠️ Exceso de velocidad: Jaime", "🚶 Jaime salió de Casa", "📍 Jaime llegó a Trabajo"]
    assert "maps" in jeanette_calls[0].data["data"]["url"]
    assert jaime_calls == []   # no se avisa a uno mismo
    assert hass.states.get("sensor.jaime_lugar").state == "Trabajo"
    last = hass.states.get("sensor.jaime_ultimo_viaje")
    assert last.attributes["from"] == "Casa" and last.attributes["to"] == "Trabajo"
    assert float(last.state) > 4
    assert hass.states.get("sensor.casa_personas").state == "1"


async def test_check_in_and_sos(hass: HomeAssistant):
    hass.config.language = "es"
    calls = capture_notify(hass, "mobile_app_jeanette")
    capture_notify(hass, "mobile_app_jaime")
    tracker(hass, "device_tracker.jaime", -33.45, -70.66)
    tracker(hass, "device_tracker.jeanette", *HOME)
    with patch("custom_components.family_location.engine.geocode.reverse", return_value="Av. Matta 100, Santiago"):
        await setup_circle(hass)
        await hass.services.async_call(DOMAIN, "check_in", {"entity_id": "device_tracker.jaime"}, blocking=True)
        await hass.services.async_call("button", "press", {"entity_id": "button.jaime_pedir_ayuda"}, blocking=True)
        await hass.async_block_till_done()
    assert calls[0].data["message"] == "Jaime está cerca de Av. Matta 100, Santiago."
    assert calls[1].data["title"] == "🆘 Jaime pide ayuda"
    assert calls[1].data["data"]["push"]["sound"]["critical"] == 1
    assert hass.states.get("sensor.jaime_lugar").state == "Av. Matta 100, Santiago"


@pytest.fixture(autouse=True)
def _no_network():
    with patch("custom_components.family_location.engine.geocode.reverse", return_value=None):
        yield


async def test_config_flow_creates_members_and_home(hass: HomeAssistant):
    hass.config.language = "es"
    assert await async_setup_component(hass, "zone", {})
    hass.states.async_set("person.jaime", "home", {"friendly_name": "Jaime", "latitude": hass.config.latitude,
                                                     "longitude": hass.config.longitude, "device_trackers": []})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Familia", "members": ["person.jaime"], "add_home": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    subs = {s.title: s for s in entry.subentries.values()}
    assert set(subs) == {"Jaime", "Casa"}
    assert subs["Casa"].data["zone"] == "zone.home"
    await hass.async_block_till_done()
    assert hass.states.get("sensor.jaime_lugar").state == "Casa"


async def test_place_subentry_by_address(hass: HomeAssistant):
    hass.config.language = "es"
    tracker(hass, "device_tracker.jaime", *HOME)
    tracker(hass, "device_tracker.jeanette", *HOME)
    entry = await setup_circle(hass)
    jeanette = next(s.subentry_id for s in entry.subentries.values() if s.title == "Jeanette")

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
        flow["flow_id"], {"notify_arrive": True, "notify_leave": False, "watch": [], "recipients": [jeanette]})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    place = next(s for s in entry.subentries.values() if s.title == "Colegio")
    assert place.data["location"] == {"latitude": -33.401, "longitude": -70.571, "radius": 180}
    assert place.data["recipients"] == [jeanette]
    assert hass.states.get("sensor.colegio_personas").state == "0"


async def test_member_subentry(hass: HomeAssistant):
    hass.config.language = "es"
    tracker(hass, "device_tracker.jaime", *HOME)
    tracker(hass, "device_tracker.jeanette", *HOME)
    tracker(hass, "device_tracker.hijo", *HOME)
    entry = await setup_circle(hass)
    flow = await hass.config_entries.subentries.async_init((entry.entry_id, "member"), context={"source": "user"})
    res = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"entity_id": "device_tracker.jaime", "notify": [], "receive_alerts": True, "speed_limit": 0})
    assert res["errors"] == {"entity_id": "already_member"}
    res = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"entity_id": "device_tracker.hijo", "name": "Tomás", "notify": [],
                          "receive_alerts": False, "speed_limit": 90})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("sensor.tomas_lugar").state == "Casa"
    assert hass.states.get("binary_sensor.tomas_exceso_de_velocidad").state == "off"


async def test_options_flow(hass: HomeAssistant):
    tracker(hass, "device_tracker.jaime", *HOME)
    tracker(hass, "device_tracker.jeanette", *HOME)
    entry = await setup_circle(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    opts = {**default_options(), "notify_trips": True}
    res = await hass.config_entries.options.async_configure(flow["flow_id"], opts)
    assert res["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["notify_trips"] is True


async def test_place_reconfigure_keeps_location(hass: HomeAssistant):
    hass.config.language = "es"
    tracker(hass, "device_tracker.jaime", *HOME)
    tracker(hass, "device_tracker.jeanette", *HOME)
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
    assert hass.states.get("sensor.jaime_lugar").state == "Hogar"


async def test_no_alert_to_who_travels_together(hass: HomeAssistant, freezer):
    """Jaime y Jeanette van juntos de Casa al Trabajo: no se avisan entre ellos; Tomás (en casa) sí recibe."""
    hass.config.language = "es"
    jaime = capture_notify(hass, "mobile_app_jaime")
    jeanette = capture_notify(hass, "mobile_app_jeanette")
    tomas = capture_notify(hass, "mobile_app_tomas")
    for ent in ("jaime", "jeanette", "tomas"):
        tracker(hass, f"device_tracker.{ent}", *HOME)
    await setup_circle(hass, speed_limit=0,
                       extra=[member("device_tracker.tomas", "Tomás", "notify.mobile_app_tomas")])

    def both(lat, lon, speed):
        tracker(hass, "device_tracker.jaime", lat, lon, speed=speed)
        tracker(hass, "device_tracker.jeanette", lat + 0.0003, lon, speed=speed)

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

    assert jaime == [] and jeanette == []
    titles = sorted(c.data["title"] for c in tomas)
    assert titles == ["📍 Jaime llegó a Trabajo", "📍 Jeanette llegó a Trabajo",
                      "🚶 Jaime salió de Casa", "🚶 Jeanette salió de Casa"]


async def test_alert_when_not_together(hass: HomeAssistant, freezer):
    hass.config.language = "es"
    jeanette = capture_notify(hass, "mobile_app_jeanette")
    capture_notify(hass, "mobile_app_jaime")
    tracker(hass, "device_tracker.jaime", *HOME)
    tracker(hass, "device_tracker.jeanette", *HOME)
    await setup_circle(hass, speed_limit=0)
    tracker(hass, "device_tracker.jaime", HOME[0] + 0.01, HOME[1], speed=40)   # Jaime sale solo
    await hass.async_block_till_done()
    assert jeanette == []          # se espera un poco por si iba acompañado
    await advance(hass, freezer, 120)
    assert [c.data["title"] for c in jeanette] == ["🚶 Jaime salió de Casa"]
