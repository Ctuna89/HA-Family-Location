"""Tests of what is sent to Nominatim (without Home Assistant)."""

import asyncio
from unittest.mock import patch

from custom_components.family_location import geocode

HOME = (-33.4372, -70.6506)


def test_viewbox_does_not_reveal_home():
    box = geocode.near_viewbox(*HOME)
    assert box == "-71.25,-33.00,-70.25,-34.00"            # centered on (-33.5, -70.75), ±0.5°
    # every home within the same 0.25° cell sends exactly the same box
    assert geocode.near_viewbox(-33.40, -70.70) == box
    assert geocode.near_viewbox(-33.55, -70.80) == box
    assert str(HOME[0]) not in box and str(HOME[1]) not in box


def test_requests_use_the_configured_server_and_identify_the_integration():
    calls = []

    async def fake_get(session, path, params, language, base_url=None):
        calls.append((geocode.server_url(base_url), path, params))
        return [{"lat": "1", "lon": "2", "display_name": "x"}]

    with patch.object(geocode, "_get", side_effect=fake_get):
        asyncio.run(geocode.geocode(None, "Main St 1", "en", near=HOME, base_url="http://nominatim.lan:8080/"))
    base, path, params = calls[0]
    assert base == "http://nominatim.lan:8080" and path == "search"
    assert params["viewbox"] == geocode.near_viewbox(*HOME)
    assert geocode.server_url("") == geocode.server_url(None) == "https://nominatim.openstreetmap.org"
    assert "github.com/Ctuna89/HA-Family-Location" in geocode.USER_AGENT
