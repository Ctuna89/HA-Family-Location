from datetime import datetime

from custom_components.family_location import messages


def test_arrive_es():
    title, msg = messages.build("arrive", "es", "James", datetime(2026, 1, 1, 18, 32), "Casa")
    assert title == "📍 James llegó a Casa"
    assert msg == "James llegó a Casa a las 18:32."


def test_trip_end_es():
    data = {"distance_km": 12.37, "duration_min": 83, "from": "Casa", "to": "Trabajo", "max_speed_kmh": 98}
    _, msg = messages.build("trip_end", "es", "Janet", datetime(2026, 1, 1, 9, 0), data=data)
    assert msg == "12,4 km en 1 h 23 min · de Casa a Trabajo · máx. 98 km/h."


def test_speeding_en():
    title, msg = messages.build("speeding", "en", "James", datetime(2026, 1, 1), data={"speed_kmh": 132, "limit_kmh": 120})
    assert "132 km/h" in msg and "120" in msg and title.startswith("⚠️")


def test_language_defaults_to_english():
    assert messages.lang_of("es") == "es"
    assert messages.lang_of("es-419") == "es"
    assert messages.lang_of("en") == "en"
    assert messages.lang_of("de") == "en"
    assert messages.lang_of(None) == "en"


def test_twelve_hour_clock():
    t = datetime(2026, 1, 1, 18, 32)
    assert messages.format_time(t, "en", "12h") == "6:32 PM"
    assert messages.format_time(t, "es", "12h") == "6:32 p. m."
    assert messages.format_time(datetime(2026, 1, 1, 0, 5), "en", "12h") == "12:05 AM"
    assert messages.format_time(datetime(2026, 1, 1, 12, 0), "en", "12h") == "12:00 PM"
    assert messages.format_time(t, "en", "24h") == "18:32"
    _, msg = messages.build("arrive", "en", "James", t, "Home", time_format="12h")
    assert msg == "James arrived at Home at 6:32 PM."
