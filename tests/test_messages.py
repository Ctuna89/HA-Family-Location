from datetime import datetime

from custom_components.family_location import messages


def test_arrive_es():
    title, msg = messages.build("arrive", "es", "Jaime", datetime(2026, 1, 1, 18, 32), "Casa")
    assert title == "📍 Jaime llegó a Casa"
    assert msg == "Jaime llegó a Casa a las 18:32."


def test_trip_end_es():
    data = {"distance_km": 12.37, "duration_min": 83, "from": "Casa", "to": "Trabajo", "max_speed_kmh": 98}
    _, msg = messages.build("trip_end", "es", "Jeanette", datetime(2026, 1, 1, 9, 0), data=data)
    assert msg == "12,4 km en 1 h 23 min · de Casa a Trabajo · máx. 98 km/h."


def test_speeding_en():
    title, msg = messages.build("speeding", "en", "Jaime", datetime(2026, 1, 1), data={"speed_kmh": 132, "limit_kmh": 120})
    assert "132 km/h" in msg and "120" in msg and title.startswith("⚠️")
