"""Asistente de configuración de Family Location.

- La entrada principal es el «círculo» (p. ej. «Familia»). Al crearlo se pueden elegir las personas de Home
  Assistant que lo forman y se agrega «Casa» como primer lugar.
- Cada integrante y cada lugar es una subentrada: se agregan, editan y borran desde la página de la
  integración con «Añadir integrante» y «Añadir lugar».
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import slugify

from . import geocode
from .const import (
    CONF_ADDRESS,
    CONF_DRIVING_SPEED,
    CONF_ENTITY,
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
    CONF_SAFETY_RECIPIENTS,
    CONF_SPEED_LIMIT,
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
    SUBENTRY_MEMBER,
    SUBENTRY_PLACE,
)

CONF_MEMBERS = "members"
CONF_ADD_HOME = "add_home"
SKIP_NOTIFY = {"send_message", "persistent_notification", "notify"}


# ---------------------------------------------------------------------- ayudas
def notify_services(hass: HomeAssistant) -> list[str]:
    services = hass.services.async_services_for_domain("notify")
    return sorted(f"notify.{name}" for name in services if name not in SKIP_NOTIFY)


def detect_notify(hass: HomeAssistant, entity_id: str) -> list[str]:
    """Servicio notify.mobile_app_* del teléfono de una persona o rastreador, si se puede deducir."""
    trackers = [entity_id]
    if entity_id.startswith("person."):
        state = hass.states.get(entity_id)
        trackers = list(state.attributes.get("device_trackers") or []) if state else []
    ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)
    found: list[str] = []
    for tracker in trackers:
        entry = ent_reg.async_get(tracker)
        if entry is None or entry.platform != "mobile_app" or not entry.device_id:
            continue
        device = dev_reg.async_get(entry.device_id)
        if device is None:
            continue
        for name in (device.name, device.name_by_user):
            if name and hass.services.has_service("notify", f"mobile_app_{slugify(name)}"):
                found.append(f"notify.mobile_app_{slugify(name)}")
                break
    return list(dict.fromkeys(found))


def friendly_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    if state is not None and state.name:
        return str(state.name)
    return entity_id.split(".", 1)[-1].replace("_", " ").title()


def member_options(entry: ConfigEntry) -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=sub.subentry_id, label=sub.title)
        for sub in entry.subentries.values() if sub.subentry_type == SUBENTRY_MEMBER
    ]


def _member_data(hass: HomeAssistant, entity_id: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        subentry_type=SUBENTRY_MEMBER,
        title=friendly_name(hass, entity_id),
        data={CONF_ENTITY: entity_id, CONF_NOTIFY: detect_notify(hass, entity_id),
              CONF_RECEIVE_ALERTS: True, CONF_SPEED_LIMIT: 0},
        unique_id=entity_id,
    )


def _number(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX))


def _multi_select(options: list[Any], custom: bool = False) -> selector.SelectSelector:
    return selector.SelectSelector(selector.SelectSelectorConfig(
        options=options, multiple=True, custom_value=custom, mode=selector.SelectSelectorMode.DROPDOWN))


# ---------------------------------------------------------------------- círculo
class FamilyLocationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Crea un círculo."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            subentries = [_member_data(self.hass, ent) for ent in user_input.get(CONF_MEMBERS) or []]
            if user_input.get(CONF_ADD_HOME) and self.hass.states.get("zone.home") is not None:
                subentries.append(ConfigSubentryData(
                    subentry_type=SUBENTRY_PLACE,
                    title="Casa" if not self.hass.config.language.startswith("en") else "Home",
                    data={CONF_ZONE: "zone.home", CONF_NOTIFY_ARRIVE: True, CONF_NOTIFY_LEAVE: True, CONF_INSTANT: True,
                          CONF_WATCH: [], CONF_RECIPIENTS: []},
                    unique_id=None,
                ))
            return self.async_create_entry(title=user_input[CONF_NAME], data={}, options=default_options(),
                                           subentries=subentries)

        persons = sorted(self.hass.states.async_entity_ids("person"))
        schema = vol.Schema({
            vol.Required(CONF_NAME, default="Familia"): selector.TextSelector(),
            vol.Optional(CONF_MEMBERS, default=persons): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["person", "device_tracker"], multiple=True)),
            vol.Optional(CONF_ADD_HOME, default=True): selector.BooleanSelector(),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FamilyLocationOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_MEMBER: MemberSubentryFlow, SUBENTRY_PLACE: PlaceSubentryFlow}


def default_options() -> dict[str, Any]:
    return {
        CONF_NOTIFY_SPEEDING: True,
        CONF_NOTIFY_BATTERY: True,
        CONF_NOTIFY_TRIPS: False,
        CONF_NOTIFY_SELF: False,
        CONF_REVERSE_GEOCODE: True,
        CONF_SAFETY_RECIPIENTS: [],
        CONF_LOW_BATTERY: DEFAULT_LOW_BATTERY,
        CONF_MOVING_SPEED: DEFAULT_MOVING_SPEED,
        CONF_DRIVING_SPEED: DEFAULT_DRIVING_SPEED,
        CONF_STOP_MINUTES: DEFAULT_STOP_MINUTES,
        CONF_START_DISTANCE: DEFAULT_START_DISTANCE,
        CONF_MAX_ACCURACY: DEFAULT_MAX_ACCURACY,
    }


class FamilyLocationOptionsFlow(OptionsFlow):
    """Avisos generales y sensibilidad de la detección de viajes."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = {**default_options(), **self.config_entry.options}
        members = member_options(self.config_entry)
        fields: dict[Any, Any] = {
            vol.Required(CONF_NOTIFY_SPEEDING, default=opts[CONF_NOTIFY_SPEEDING]): selector.BooleanSelector(),
            vol.Required(CONF_NOTIFY_BATTERY, default=opts[CONF_NOTIFY_BATTERY]): selector.BooleanSelector(),
            vol.Required(CONF_LOW_BATTERY, default=opts[CONF_LOW_BATTERY]): _number(5, 50, 1, "%"),
            vol.Required(CONF_NOTIFY_TRIPS, default=opts[CONF_NOTIFY_TRIPS]): selector.BooleanSelector(),
            vol.Optional(CONF_SAFETY_RECIPIENTS, default=[
                m for m in opts[CONF_SAFETY_RECIPIENTS] if m in {o["value"] for o in members}
            ]): _multi_select(members),
            vol.Required(CONF_NOTIFY_SELF, default=opts[CONF_NOTIFY_SELF]): selector.BooleanSelector(),
            vol.Required(CONF_REVERSE_GEOCODE, default=opts[CONF_REVERSE_GEOCODE]): selector.BooleanSelector(),
            vol.Required(CONF_MOVING_SPEED, default=opts[CONF_MOVING_SPEED]): _number(3, 30, 1, "km/h"),
            vol.Required(CONF_DRIVING_SPEED, default=opts[CONF_DRIVING_SPEED]): _number(10, 60, 1, "km/h"),
            vol.Required(CONF_STOP_MINUTES, default=opts[CONF_STOP_MINUTES]): _number(1, 30, 1, "min"),
            vol.Required(CONF_START_DISTANCE, default=opts[CONF_START_DISTANCE]): _number(100, 2000, 10, "m"),
            vol.Required(CONF_MAX_ACCURACY, default=opts[CONF_MAX_ACCURACY]): _number(20, 2000, 10, "m"),
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))


# ---------------------------------------------------------------------- integrante
class MemberSubentryFlow(ConfigSubentryFlow):
    """Agrega o edita un integrante."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._form(user_input, None)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._form(user_input, self._get_reconfigure_subentry())

    async def _form(self, user_input: dict[str, Any] | None, current: Any) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_entry()
        if user_input is not None:
            entity = user_input[CONF_ENTITY]
            taken = {s.data.get(CONF_ENTITY) for s in entry.subentries.values()
                     if s.subentry_type == SUBENTRY_MEMBER and (current is None or s.subentry_id != current.subentry_id)}
            if entity in taken:
                errors[CONF_ENTITY] = "already_member"
            else:
                title = (user_input.pop(CONF_NAME, "") or "").strip() or friendly_name(self.hass, entity)
                data = {
                    CONF_ENTITY: entity,
                    CONF_NOTIFY: list(user_input.get(CONF_NOTIFY) or []),
                    CONF_RECEIVE_ALERTS: user_input.get(CONF_RECEIVE_ALERTS, True),
                    CONF_SPEED_LIMIT: float(user_input.get(CONF_SPEED_LIMIT) or 0),
                }
                if current is None:
                    return self.async_create_entry(title=title, data=data, unique_id=entity)
                return self.async_update_and_abort(entry, current, title=title, data=data, unique_id=entity)

        values = dict(current.data) if current is not None else {}
        if user_input is not None:
            values.update(user_input)
        notify_choices = notify_services(self.hass)
        default_notify = list(values.get(CONF_NOTIFY) or [])
        schema = vol.Schema({
            vol.Required(CONF_ENTITY, **_default(values.get(CONF_ENTITY))): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["person", "device_tracker"])),
            vol.Optional(CONF_NAME, **_default(current.title if current else None)): selector.TextSelector(),
            vol.Optional(CONF_NOTIFY, default=default_notify): _multi_select(
                sorted(set(notify_choices) | set(default_notify)), custom=True),
            vol.Required(CONF_RECEIVE_ALERTS, default=values.get(CONF_RECEIVE_ALERTS, True)): selector.BooleanSelector(),
            vol.Required(CONF_SPEED_LIMIT, default=values.get(CONF_SPEED_LIMIT, 0)): _number(0, 250, 5, "km/h"),
        })
        step = "user" if current is None else "reconfigure"
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)


def _default(value: Any) -> dict[str, Any]:
    return {"default": value} if value not in (None, "") else {}


# ---------------------------------------------------------------------- lugar
class PlaceSubentryFlow(ConfigSubentryFlow):
    """Agrega o edita un lugar: por dirección, en el mapa o a partir de una zona de Home Assistant."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._title = ""
        self._found = ""

    def _current(self) -> Any:
        return self._get_reconfigure_subentry() if self.source == "reconfigure" else None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._step_place(user_input, "user")

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is None and not self._data:
            current = self._current()
            self._data = dict(current.data)
            self._title = current.title
        return await self._step_place(user_input, "reconfigure")

    async def _step_place(self, user_input: dict[str, Any] | None, step_id: str) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._title = user_input[CONF_NAME].strip()
            address = (user_input.get(CONF_ADDRESS) or "").strip()
            zone = user_input.get(CONF_ZONE) or ""
            radius = float(user_input.get(CONF_RADIUS) or DEFAULT_RADIUS)
            self._data[CONF_ADDRESS] = address
            if zone:
                self._data[CONF_ZONE] = zone
                self._data.pop(CONF_LOCATION, None)
                return await self.async_step_alerts()
            self._data.pop(CONF_ZONE, None)
            previous = self._data.get(CONF_LOCATION)
            if address and (previous is None or address != self._data.get("_geocoded")):
                home = (self.hass.config.latitude, self.hass.config.longitude)
                result = await geocode.geocode(async_get_clientsession(self.hass), address,
                                               self.hass.config.language or "es", near=home)
                if result is None:
                    errors[CONF_ADDRESS] = "address_not_found"
                else:
                    self._found = result.label
                    self._data["_geocoded"] = address
                    self._data[CONF_LOCATION] = {ATTR_LATITUDE: result.latitude, ATTR_LONGITUDE: result.longitude,
                                                 CONF_RADIUS: radius}
            elif previous is None:
                self._data[CONF_LOCATION] = {ATTR_LATITUDE: self.hass.config.latitude,
                                             ATTR_LONGITUDE: self.hass.config.longitude, CONF_RADIUS: radius}
            else:
                self._data[CONF_LOCATION] = {**previous, CONF_RADIUS: radius}
            if not errors:
                return await self.async_step_location()

        radius = (self._data.get(CONF_LOCATION) or {}).get(CONF_RADIUS, DEFAULT_RADIUS)
        schema = vol.Schema({
            vol.Required(CONF_NAME, **_default(self._title)): selector.TextSelector(),
            vol.Optional(CONF_ADDRESS, **_default(self._data.get(CONF_ADDRESS))): selector.TextSelector(),
            vol.Optional(CONF_ZONE, **_default(self._data.get(CONF_ZONE))): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="zone")),
            vol.Required(CONF_RADIUS, default=radius): _number(30, 5000, 10, "m"),
        })
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_location(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Muestra el mapa para confirmar o corregir el punto y el radio."""
        if user_input is not None:
            loc = user_input[CONF_LOCATION]
            self._data[CONF_LOCATION] = {
                ATTR_LATITUDE: loc[ATTR_LATITUDE], ATTR_LONGITUDE: loc[ATTR_LONGITUDE],
                CONF_RADIUS: loc.get(CONF_RADIUS) or self._data[CONF_LOCATION].get(CONF_RADIUS, DEFAULT_RADIUS),
            }
            return await self.async_step_alerts()
        schema = vol.Schema({
            vol.Required(CONF_LOCATION, default=self._data[CONF_LOCATION]): selector.LocationSelector(
                selector.LocationSelectorConfig(radius=True, icon="mdi:map-marker")),
        })
        return self.async_show_form(
            step_id="location", data_schema=schema,
            description_placeholders={"name": self._title, "found": self._found or self._data.get(CONF_ADDRESS) or "—"},
        )

    async def async_step_alerts(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Quién se vigila en este lugar y quién recibe los avisos."""
        entry = self._get_entry()
        members = member_options(entry)
        valid = {m["value"] for m in members}
        if user_input is not None:
            data = {k: v for k, v in self._data.items() if not k.startswith("_")}
            data["_geocoded"] = self._data.get("_geocoded", "")
            data.update({
                CONF_NOTIFY_ARRIVE: user_input[CONF_NOTIFY_ARRIVE],
                CONF_NOTIFY_LEAVE: user_input[CONF_NOTIFY_LEAVE],
                CONF_INSTANT: user_input.get(CONF_INSTANT, False),
                CONF_WATCH: list(user_input.get(CONF_WATCH) or []),
                CONF_RECIPIENTS: list(user_input.get(CONF_RECIPIENTS) or []),
            })
            current = self._current()
            if current is None:
                return self.async_create_entry(title=self._title, data=data)
            return self.async_update_and_abort(entry, current, title=self._title, data=data)

        schema = vol.Schema({
            vol.Required(CONF_NOTIFY_ARRIVE, default=self._data.get(CONF_NOTIFY_ARRIVE, True)): selector.BooleanSelector(),
            vol.Required(CONF_NOTIFY_LEAVE, default=self._data.get(CONF_NOTIFY_LEAVE, True)): selector.BooleanSelector(),
            vol.Required(CONF_INSTANT, default=self._data.get(
                CONF_INSTANT, self._data.get(CONF_ZONE) == "zone.home")): selector.BooleanSelector(),
            vol.Optional(CONF_WATCH, default=[m for m in self._data.get(CONF_WATCH) or [] if m in valid]):
                _multi_select(members),
            vol.Optional(CONF_RECIPIENTS, default=[m for m in self._data.get(CONF_RECIPIENTS) or [] if m in valid]):
                _multi_select(members),
        })
        return self.async_show_form(step_id="alerts", data_schema=schema,
                                    description_placeholders={"name": self._title})
