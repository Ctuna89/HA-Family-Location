"""Address lookup with OpenStreetMap (Nominatim), no API keys.

Used for, and only when the «Use OpenStreetMap (Nominatim)» option is on:
- turning the address you type when creating a place into coordinates;
- (optional) the approximate address of a member stopped away from their places and zones, also in check-ins
  and SOS alerts;
- (only for members with a highway speed limit) the road type while they go faster than their street limit.

The public server asks for at most one request per second and a User-Agent that identifies the application; a
self-hosted Nominatim server can be used instead.
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
USER_AGENT = "HA-Family-Location (Home Assistant integration; +https://github.com/Ctuna89/HA-Family-Location)"
# Address searches prefer results near home. The center is rounded to a 0.25° grid (~25 km), so the request
# doesn't reveal where home is (no more than the request's IP address already does).
NEAR_GRID = 0.25
NEAR_HALF_SIZE = 0.5   # degrees around that center (~110 km box); results outside it are not excluded
TIMEOUT = aiohttp.ClientTimeout(total=15)

_lock = asyncio.Lock()
_last_call = 0.0


@dataclass(frozen=True)
class GeoResult:
    latitude: float
    longitude: float
    label: str


def server_url(url: str | None) -> str:
    """Base URL of the Nominatim server to use (the public one by default)."""
    url = (url or "").strip().rstrip("/")
    return url or NOMINATIM


def near_viewbox(lat: float, lon: float) -> str:
    """Search bias box around a coarse (0.25°) version of a point, as Nominatim's «viewbox»."""
    clat = round(lat / NEAR_GRID) * NEAR_GRID
    clon = round(lon / NEAR_GRID) * NEAR_GRID
    h = NEAR_HALF_SIZE
    return f"{clon - h:.2f},{clat + h:.2f},{clon + h:.2f},{clat - h:.2f}"


async def _get(session: aiohttp.ClientSession, path: str, params: dict[str, Any], language: str,
               base_url: str | None = None) -> Any:
    global _last_call
    base = server_url(base_url)
    async with _lock:
        wait = 1.1 - (time.monotonic() - _last_call)
        if wait > 0 and base == NOMINATIM:   # the public server's rate limit
            await asyncio.sleep(wait)
        try:
            async with session.get(
                f"{base}/{path}",
                params={**params, "format": "jsonv2"},
                headers={"User-Agent": USER_AGENT, "Accept-Language": language},
                timeout=TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        finally:
            _last_call = time.monotonic()


async def geocode(session: aiohttp.ClientSession, address: str, language: str = "es",
                  near: tuple[float, float] | None = None, base_url: str | None = None) -> GeoResult | None:
    """Coordinates of an address, or None if not found or the request fails."""
    params: dict[str, Any] = {"q": address, "limit": 1, "addressdetails": 0}
    if near is not None:
        # Prefer results near home (without excluding others), without revealing where home is.
        params["viewbox"] = near_viewbox(*near)
    try:
        data = await _get(session, "search", params, language, base_url)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.warning("Could not look up the address «%s»: %s", address, err)
        return None
    if not data:
        return None
    item = data[0]
    try:
        return GeoResult(float(item["lat"]), float(item["lon"]), str(item.get("display_name") or address))
    except (KeyError, TypeError, ValueError):
        return None


def short_address(item: dict[str, Any]) -> str | None:
    """Short readable address («Av. Providencia 1234, Providencia») from a Nominatim response."""
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


async def reverse(session: aiohttp.ClientSession, lat: float, lon: float, language: str = "es",
                  base_url: str | None = None) -> str | None:
    """Approximate address of some coordinates."""
    try:
        data = await _get(session, "reverse", {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 18,
                                               "addressdetails": 1}, language, base_url)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("Could not get the address of %s,%s: %s", lat, lon, err)
        return None
    if not isinstance(data, dict) or "error" in data:
        return None
    return short_address(data)


ROAD_HIGHWAY = "highway"
ROAD_STREET = "street"
# OSM road classes treated as highways (motorways and expressways); everything else is a street.
HIGHWAY_TYPES = {"motorway", "motorway_link", "trunk", "trunk_link"}


async def road_type(session: aiohttp.ClientSession, lat: float, lon: float,
                    base_url: str | None = None) -> str | None:
    """«highway» or «street» for the road closest to some coordinates, or None if unknown.

    Uses Nominatim's reverse lookup at street level (zoom 16), which returns the road itself.
    """
    try:
        data = await _get(session, "reverse", {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "zoom": 16,
                                               "addressdetails": 0}, "en", base_url)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("Could not get the road type at %s,%s: %s", lat, lon, err)
        return None
    if not isinstance(data, dict) or data.get("category") != "highway":
        return None
    return ROAD_HIGHWAY if data.get("type") in HIGHWAY_TYPES else ROAD_STREET
