"""Búsqueda de direcciones con OpenStreetMap (Nominatim), sin claves de API.

Solo se usa para:
- convertir la dirección que escribes al crear un lugar en coordenadas, y
- (opcional) mostrar la dirección aproximada de un integrante cuando está detenido fuera de sus lugares.

Nominatim pide como máximo una consulta por segundo y un User-Agent que identifique la aplicación.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org"
USER_AGENT = "HomeAssistant-FamilyLocation/1.0 (+https://www.home-assistant.io)"
TIMEOUT = aiohttp.ClientTimeout(total=15)

_lock = asyncio.Lock()
_last_call = 0.0


@dataclass(frozen=True)
class GeoResult:
    latitude: float
    longitude: float
    label: str


async def _get(session: aiohttp.ClientSession, path: str, params: dict[str, Any], language: str) -> Any:
    global _last_call
    async with _lock:
        wait = 1.1 - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with session.get(
                f"{NOMINATIM}/{path}",
                params={**params, "format": "jsonv2"},
                headers={"User-Agent": USER_AGENT, "Accept-Language": language},
                timeout=TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        finally:
            _last_call = time.monotonic()


async def geocode(session: aiohttp.ClientSession, address: str, language: str = "es",
                  near: tuple[float, float] | None = None) -> GeoResult | None:
    """Coordenadas de una dirección, o None si no se encuentra o falla la consulta."""
    params: dict[str, Any] = {"q": address, "limit": 1, "addressdetails": 0}
    if near is not None:
        lat, lon = near
        # Preferir resultados cerca de la casa (sin excluir los demás).
        params["viewbox"] = f"{lon - 1.5},{lat + 1.5},{lon + 1.5},{lat - 1.5}"
    try:
        data = await _get(session, "search", params, language)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.warning("No se pudo buscar la dirección «%s»: %s", address, err)
        return None
    if not data:
        return None
    item = data[0]
    try:
        return GeoResult(float(item["lat"]), float(item["lon"]), str(item.get("display_name") or address))
    except (KeyError, TypeError, ValueError):
        return None


def short_address(item: dict[str, Any]) -> str | None:
    """Dirección corta y legible («Av. Providencia 1234, Providencia») a partir de la respuesta de Nominatim."""
    addr = item.get("address") or {}
    street = addr.get("road") or addr.get("pedestrian") or addr.get("footway") or addr.get("path")
    number = addr.get("house_number")
    place = item.get("name") if item.get("name") and item.get("name") != street else None
    area = (addr.get("suburb") or addr.get("city_district") or addr.get("town") or addr.get("city")
            or addr.get("village") or addr.get("municipality"))
    first = " ".join(p for p in (street, number) if p) or place
    parts = [p for p in (first, area) if p]
    if parts:
        return ", ".join(dict.fromkeys(parts))
    display = item.get("display_name")
    return ", ".join(str(display).split(", ")[:2]) if display else None


async def reverse(session: aiohttp.ClientSession, lat: float, lon: float, language: str = "es") -> str | None:
    """Dirección aproximada de unas coordenadas."""
    try:
        data = await _get(session, "reverse", {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 18,
                                               "addressdetails": 1}, language)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("No se pudo obtener la dirección de %s,%s: %s", lat, lon, err)
        return None
    if not isinstance(data, dict) or "error" in data:
        return None
    return short_address(data)
