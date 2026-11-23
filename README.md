# Family Location 📍

🇪🇸 [Leer en español](README.es.md)

**A Life360 replacement that lives inside your Home Assistant.** Places by address, arrival and departure
alerts for the whole family («James arrived home», «Janet arrived at work»), who is on the move, trips with
distance and top speed, speeding alerts, low battery, check-in and an SOS button.

No accounts and no subscription: positions come from the **Home Assistant Companion app** on each phone, and
everything (places, trips, speeding, alerts) is computed in your Home Assistant. A few optional features look up
addresses or road types on OpenStreetMap; [Privacy](#privacy) lists exactly what is sent, when, and the switch
that turns it all off.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Ctuna89&repository=HA-Family-Location&category=integration)

## Features

| | |
|---|---|
| 🏠 **Places by address** | Type «1600 Amphitheatre Pkwy, Mountain View», it is looked up on OpenStreetMap, you confirm the point on a map and adjust the radius. You can also drop a pin on the map or reuse an existing zone |
| 🔔 **Arrivals and departures** | The rest of the circle is alerted when someone arrives at or leaves a place. Per place you choose whether to alert on arrival, on departure, for whom (e.g. only the kids at school) and to whom |
| 🚦 **No false arrivals** | A trip only ends after 5 minutes without moving (configurable): a traffic light or a jam doesn't end it. Arrivals at places other than Home are announced only once the person stays there for those 5 minutes; driving past, or stopping at a light in front of work, doesn't count |
| 👨‍👩‍👧 **Together? No alert** | If James is with Janet, Janet doesn't get «James arrived at Work» (nor the departure or the trip): only the rest of the circle does |
| 🚗 **On the move** | *Still / Moving / Driving* status, current speed, and a «Moving» binary sensor |
| 🛣️ **Trips** | Automatic start and end, distance, duration, top speed, origin and destination. Distance and trips today |
| ⚠️ **Speeding** | Per-person limit (e.g. 100 km/h for the new teen driver), optionally split into a **street** and a **highway** limit (e.g. 60 / 120 km/h). Confirmed by two consecutive readings to avoid false alerts from GPS jumps |
| 🏆 **Weekly leaderboard** | Distance, trips, top speed and speeding events per person this week (Monday to Sunday), plus a circle leaderboard |
| 🔋 **Low battery** | The circle is alerted when someone's phone drops below the threshold |
| ✅ **Check-in** | A button (and action) that tells everyone «James is at Home» or «near 742 Evergreen Terrace» |
| 🆘 **Ask for help** | A button that sends a **critical** alert (rings even on silent or Do Not Disturb, once each phone allows it — see below) with a link to the location |
| 🗺️ **Your HA zones too** | If someone is inside a Home Assistant zone you didn't add as a place (e.g. «Gym»), their place shows the zone name instead of a street address. Optional, on by default |
| 📫 **Approximate address** | Optional: when someone is stopped away from their places and zones, their address is shown (looked up on OpenStreetMap, see [Privacy](#privacy)) |
| 🤖 **Events for automations** | Every arrival, departure, trip, speeding, battery, check-in and SOS fires the `family_location_event` event |
| 🌍 **Languages** | English and Spanish (notifications follow your Home Assistant language) |

## Requirements

1. **Home Assistant 2025.3 or newer.**
2. The **Home Assistant Companion app** on each member's phone, with location set to **«Allow all the time»**, and
   a Home Assistant **person** linked to that phone.
3. For useful speeding alerts the phone has to report its location often while moving:
   - **Android:** *App settings → Sensors → Background location* enabled; ideally turn on *High accuracy
     mode* (you can limit it to when the phone is connected to the car via Bluetooth or Android Auto).
   - **iPhone:** iOS reports on significant location changes; speeds are computed between positions, so on
     iPhone speeding alerts are less immediate.

## Installation

1. HACS → ⋮ menu → *Custom repositories* → add `https://github.com/Ctuna89/HA-Family-Location` as an
   **Integration** (or use the button above).
2. Install **Family Location** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → Family Location.*

## Configuration

1. **Create the circle:** name («Family»), who is in it (each person's phone notification service is detected
   automatically) and whether to add «Home» as the first place.
2. **Add places:** on the integration page, **«Add place»** button:
   1. name and address (or an existing zone, or nothing to drop a pin on the map);
   2. confirm the point and radius on the map;
   3. choose the alerts: on arrival / on departure, for whom and to whom, and whether to alert as soon as
      someone enters.
3. **Add or edit members:** **«Add member»** button, or the pencil next to each one. There you set their speed
   limits (0 = no alert), which phone(s) receive their alerts and whether they receive alerts at all.
   - **Street limit** only: it applies everywhere.
   - **Street + highway limits:** when the person goes over the street limit, OpenStreetMap is asked whether
     they're on a highway (motorway or expressway), and the matching limit is used. Results are cached, so
     the same stretch of road isn't looked up twice. Until the road type is known, the higher (highway) limit
     applies, so an unknown road never causes a false alert.
4. **General options** (*Configure* button): which safety alerts are sent and to whom, battery threshold,
   12- or 24-hour clock in notifications, trip detection sensitivity, and what may be looked up on
   OpenStreetMap (see [Privacy](#privacy)).

Nobody receives alerts about themselves (configurable in the options).

### When alerts are sent

- **Home** announces arrivals as soon as someone enters. For other places the *«Alert as soon as they enter»*
  option is off: the arrival is confirmed after the person stays stopped there for the configured minutes
  (5 by default), and the alert shows the time they entered. You can turn it on per place.
- **Trips** start when someone moves more than 250 m from where they were or goes faster than 8 km/h, and only
  end after 5 minutes without moving. Stopping 2–3 minutes at a traffic light or in a jam doesn't end the trip.
- **Companions:** arrival, departure and trip alerts wait 90 seconds. If during that time another member is with
  the person (arrived at the same place less than 10 minutes apart, or left together and is within ~300 m),
  that member doesn't get the alert. Speeding, low battery, check-in and SOS are always sent right away.

## Entities

Per member (a device with their name; entity IDs depend on your Home Assistant language, English shown):

| Entity | What it shows |
|---|---|
| `sensor.<name>_place` | Place where they are, or the Home Assistant zone they're in, or their approximate address, or «away». Attributes: since when, zone, coordinates, accuracy, last seen |
| `sensor.<name>_status` | `still` · `moving` · `driving`. During a trip: distance, duration and top speed so far |
| `sensor.<name>_speed` | km/h |
| `binary_sensor.<name>_moving` | On while a trip is in progress |
| `binary_sensor.<name>_speeding` | Only if they have a speed limit |
| `sensor.<name>_distance_today` | km travelled today and number of trips |
| `sensor.<name>_last_trip` | km of the last trip; origin, destination, times, duration and top speed in attributes |
| `sensor.<name>_distance_this_week` / `_top_speed_this_week` / `_speeding_this_week` | This week's stats (Monday to Sunday); last week's totals in the `last_week` attribute |
| `sensor.<name>_phone_battery` | Battery % |
| `button.<name>_check_in` / `button.<name>_ask_for_help` | Alert the circle |

Per place: `sensor.<place>_people` (how many and who) and `binary_sensor.<place>_occupied`.

## Actions

```yaml
action: family_location.check_in
data:
  entity_id: person.james
  message: "Grabbing some bread"
```

```yaml
action: family_location.sos
data:
  entity_id: person.janet
```

## Automations with the event

```yaml
triggers:
  - trigger: event
    event_type: family_location_event
    event_data:
      type: arrive
      place: School
actions:
  - action: light.turn_on
    target:
      entity_id: light.porch
```

Types: `arrive`, `leave`, `trip_start`, `trip_end`, `speeding`, `low_battery`, `check_in`, `sos`. The event
includes `member`, `entity_id`, `place`, `latitude`, `longitude` and the trip or speed data.

## Example card

```yaml
type: vertical-stack
cards:
  - type: map
    entities:
      - person.james
      - person.janet
    hours_to_show: 12
  - type: entities
    entities:
      - sensor.james_place
      - sensor.james_status
      - sensor.james_speed
      - sensor.james_last_trip
      - sensor.janet_place
      - sensor.janet_status
  - type: horizontal-stack
    cards:
      - type: button
        entity: button.james_check_in
        tap_action: {action: toggle}
      - type: button
        entity: button.james_ask_for_help
        hold_action: {action: toggle}
        tap_action: {action: none}
```

Home Assistant keeps the location history: the map card with `hours_to_show` shows the route.

## Map card

The integration includes its own map card. Each place is drawn as a semi-transparent circle with its real
radius, and each person as their picture (or initials). Tapping someone shows where they are, whether they're
still or driving, their battery and when their phone last reported. Nothing to install: the card is loaded
automatically once the integration is set up (reload the page or the app after updating).

```yaml
type: custom:family-location-map-card
people:
  - person.james
  - entity: person.janet
    color: "#db2777"
places:            # place names, Family Location sensors or Home Assistant zones
  - Home
  - entity: zone.office
    color: "#7c3aed"
```

| Option | Default | |
|---|---|---|
| `people` | every `person` with a location | `person.*` or `device_tracker.*`, optionally with `name` and `color` |
| `places` | every Family Location place | a place name, a `sensor.<place>_people`, or any `zone.*`, optionally with `name` and `color` |
| `opacity` | `0.2` | fill opacity of the circles (0–1) |
| `min_circle_px` | `10` | zoomed out, small places are drawn with this radius in pixels so they stay visible |
| `labels` | `true` | place names under the circles |
| `height` | `400` | height in pixels (in a panel view it takes the whole screen) |
| `dark_mode` | `auto` | `auto` follows Home Assistant, or `light` / `dark` |
| `fit` | `all` | `people` centers the map on the people only |
| `tile_url` | Home Assistant's tile proxy | another tile provider, e.g. `https://tiles.example.com/{z}/{x}/{y}.png` |
| `tile_url_dark` | | dark tiles for that provider (without it, the light ones are shown with inverted colors) |
| `tile_attribution` | | attribution text (HTML) for that provider |
| `title`, `language` | | card title; `es` or `en` (by default, the user's language) |

By default the map tiles come through **Home Assistant's own tile proxy**, the same one its built-in map card
uses: Home Assistant fetches [OpenStreetMap](https://www.openstreetmap.org/copyright) tiles on the browser's
behalf, so they work locally and through Nabu Casa or any other remote URL, with no API keys. OpenStreetMap
sees the area being displayed, not where your family is. In dark mode the tiles are shown with inverted colors.
On a Home Assistant version without that proxy, the card loads OpenStreetMap's tiles directly, which works on
the local network but not through shared domains such as `ui.nabu.casa`. Respect your provider's usage policy
when you set `tile_url`.

### Weekly leaderboard

`sensor.<circle>_weekly_leaderboard` shows who drove the most this week, with the full ranking in its
`ranking` attribute (plus `fastest` and `most_speeding`). A Markdown card:

```yaml
type: markdown
title: 🏆 This week
content: >
  {% for r in state_attr('sensor.family_weekly_leaderboard', 'ranking') %}
  **{{ r.position }}. {{ r.name }}** · {{ r.distance_km }} km · {{ r.trips }} trips ·
  top {{ r.max_speed_kmh }} km/h · {{ r.speeding }} speeding
  {% endfor %}
```

## Making «Ask for help» ring on silent

Each phone that receives alerts has to allow it once:

- **iPhone:** *Settings → Notifications → Home Assistant →* turn on **Critical Alerts**.
- **Android:** the alert plays as an alarm, at the **alarm volume**, even with the ringer off (the
  `alarm_stream` channel). After the first one arrives:
  1. *Settings → Apps → Home Assistant → Notifications →* open the **alarm_stream** channel and turn on
     **Override Do Not Disturb**.
  2. In *Settings → Sound → Do Not Disturb*, make sure **Alarms** are allowed (they're not in «Total silence»).
  3. Keep the alarm volume up: that's the volume it rings at.

Send a test with `family_location.sos` (or the button) to check it rings.

## Privacy

**Always local.** Tracking, places, arrivals and departures, trips, speeding with a single limit, battery,
weekly stats, notifications (they go from your Home Assistant to your family's phones through the Companion
app's usual push service) and the history all stay in your Home Assistant. No account, no analytics.

**Sent to OpenStreetMap's Nominatim service**, only in these cases:

| What is sent | When | Automatic? | Controlled by |
|---|---|---|---|
| The address you type, plus a search area rounded to ~25 km around your home (never its exact location) | When you add or edit a place by address | No, you start it | *Use OpenStreetMap (Nominatim)* |
| A member's coordinates | When they're stopped away from their places and zones, and in check-ins and SOS alerts outside them, to show an approximate address | Yes | *Show the address when someone is away from their places* (and the master switch) |
| A member's coordinates | Only for members with a **highway** speed limit, while they're going faster than their street limit, to know whether they're on a highway (cached per ~100 m stretch) | Yes | The member's highway limit (0 = never) and the master switch |

- **Master switch:** *Configure → Use OpenStreetMap (Nominatim)*. When off, no location or address leaves your
  Home Assistant. What still works: everything above under «always local»; places are marked on the map or
  taken from a zone instead of looked up by address; the place sensor shows the place, the zone or «away»
  instead of a street address; check-ins and SOS alerts carry the map link instead of an address; and the
  street limit applies everywhere (the highway limit is ignored).
- **Self-hosted Nominatim:** set *Self-hosted Nominatim server* (e.g. `http://192.168.1.10:8080`) and nothing
  goes to the public server.
- Requests to the public server are limited to one per second and identify this integration, as its
  [usage policy](https://operations.osmfoundation.org/policies/nominatim/) asks. That policy also asks not to
  send personal data: no names or identities are ever sent, only coordinates or the address you typed, but if
  you consider even that personal, turn the master switch off or use your own server.
- **Map card:** the tiles come through Home Assistant's own tile proxy; OpenStreetMap sees the map area being
  displayed, not where your family is.

## Not supported (yet)

- Crash detection: it needs real-time phone sensors that the Home Assistant app doesn't expose.
- Alerts are only as timely as each phone's location updates: if a phone reports every 5 minutes, alerts arrive
  with that delay.

## Credits

- The map card draws with [Leaflet](https://leafletjs.com) 1.9.4 (BSD 2-Clause License,
  © Volodymyr Agafonkin and CloudMade), included in
  `custom_components/family_location/frontend/leaflet/` with its license.
- Map data and tiles © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.

## Contributing

Issues and pull requests are welcome. Run the tests with:

```bash
pip install pytest-homeassistant-custom-component
pytest tests
```
