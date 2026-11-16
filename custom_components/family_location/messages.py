"""Textos de las notificaciones (español e inglés)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .const import (
    EV_ARRIVE,
    EV_CHECK_IN,
    EV_LEAVE,
    EV_LOW_BATTERY,
    EV_SOS,
    EV_SPEEDING,
    EV_TRIP_END,
    EV_TRIP_START,
)

TEXTS: dict[str, dict[str, tuple[str, str]]] = {
    "es": {
        EV_ARRIVE: ("📍 {name} llegó a {place}", "{name} llegó a {place} a las {time}."),
        EV_LEAVE: ("🚶 {name} salió de {place}", "{name} salió de {place} a las {time}."),
        EV_TRIP_START: ("🚗 {name} va en camino", "{name} salió{from_txt} a las {time}."),
        EV_TRIP_END: ("🏁 {name} terminó un viaje", "{distance} km en {duration}{route} · máx. {max_speed} km/h."),
        EV_SPEEDING: ("⚠️ Exceso de velocidad: {name}", "{name} va a {speed} km/h (límite {limit} km/h)."),
        EV_LOW_BATTERY: ("🔋 Batería baja: {name}", "El teléfono de {name} tiene {battery} % de batería."),
        EV_CHECK_IN: ("✅ {name} hizo check-in", "{name} está {where}.{note}"),
        EV_SOS: ("🆘 {name} pide ayuda", "{name} pidió ayuda {where} a las {time}.{note}"),
    },
    "en": {
        EV_ARRIVE: ("📍 {name} arrived at {place}", "{name} arrived at {place} at {time}."),
        EV_LEAVE: ("🚶 {name} left {place}", "{name} left {place} at {time}."),
        EV_TRIP_START: ("🚗 {name} is on the way", "{name} left{from_txt} at {time}."),
        EV_TRIP_END: ("🏁 {name} finished a trip", "{distance} km in {duration}{route} · top {max_speed} km/h."),
        EV_SPEEDING: ("⚠️ Speeding: {name}", "{name} is going {speed} km/h (limit {limit} km/h)."),
        EV_LOW_BATTERY: ("🔋 Low battery: {name}", "{name}'s phone is at {battery}% battery."),
        EV_CHECK_IN: ("✅ {name} checked in", "{name} is {where}.{note}"),
        EV_SOS: ("🆘 {name} needs help", "{name} asked for help {where} at {time}.{note}"),
    },
}

WORDS = {
    "es": {"at": "en {}", "near": "cerca de {}", "unknown": "en una ubicación desconocida", "from": " de {}",
           "route_both": " · de {} a {}", "route_from": " · desde {}", "route_to": " · hasta {}"},
    "en": {"at": "at {}", "near": "near {}", "unknown": "at an unknown location", "from": " {}",
           "route_both": " · from {} to {}", "route_from": " · from {}", "route_to": " · to {}"},
}


def lang_of(language: str | None) -> str:
    return "es" if not language or not language.lower().startswith("en") else "en"


def _duration(minutes: float) -> str:
    minutes = round(minutes)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def _num(value: float, lang: str) -> str:
    text = f"{value:.1f}"
    return text.replace(".", ",") if lang == "es" else text


def where_text(lang: str, place: str | None, address: str | None) -> str:
    w = WORDS[lang]
    if place:
        return w["at"].format(place)
    if address:
        return w["near"].format(address)
    return w["unknown"]


def build(event_type: str, lang: str, name: str, when: datetime, place: str | None = None,
          data: dict[str, Any] | None = None, where: str = "", note: str = "") -> tuple[str, str]:
    """Título y mensaje de una notificación."""
    data = data or {}
    w = WORDS[lang]
    origin, dest = data.get("from"), data.get("to")
    if origin and dest:
        route = w["route_both"].format(origin, dest)
    elif origin:
        route = w["route_from"].format(origin)
    elif dest:
        route = w["route_to"].format(dest)
    else:
        route = ""
    values = {
        "name": name,
        "place": place or "",
        "time": when.strftime("%H:%M"),
        "from_txt": w["from"].format(origin) if origin else "",
        "distance": _num(float(data.get("distance_km") or 0), lang),
        "duration": _duration(float(data.get("duration_min") or 0)),
        "route": route,
        "max_speed": data.get("max_speed_kmh", 0),
        "speed": data.get("speed_kmh", ""),
        "limit": data.get("limit_kmh", ""),
        "battery": data.get("battery", ""),
        "where": where,
        "note": f" {note}" if note else "",
    }
    title, message = TEXTS[lang][event_type]
    return title.format(**values), message.format(**values)


def maps_url(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"
