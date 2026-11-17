# Family Location 📍

🇪🇸 [Leer en español](README.es.md)

**A Life360 replacement that lives inside your Home Assistant.** Places by address, arrival and departure
alerts for the whole family («Jaime arrived home», «Jeanette arrived at work»), who is on the move, trips with
distance and top speed, speeding alerts, low battery, check-in and an SOS button.

No accounts, no subscription, and your location never goes through third-party servers: positions come from
the **Home Assistant Companion app** on each phone, and everything is computed in your Home Assistant.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Ctuna89&repository=HA-Family-Location&category=integration)

## Features

| | |
|---|---|
| 🏠 **Places by address** | Type «1600 Amphitheatre Pkwy, Mountain View», it is looked up on OpenStreetMap, you confirm the point on a map and adjust the radius. You can also drop a pin on the map or reuse an existing zone |
| 🔔 **Arrivals and departures** | The rest of the circle is alerted when someone arrives at or leaves a place. Per place you choose whether to alert on arrival, on departure, for whom (e.g. only the kids at school) and to whom |
| 🚦 **No false arrivals** | A trip only ends after 5 minutes without moving (configurable): a traffic light or a jam doesn't end it. Arrivals at places other than Home are announced only once the person stays there for those 5 minutes; driving past, or stopping at a light in front of work, doesn't count |
| 👨‍👩‍👧 **Together? No alert** | If Jaime is with Jeanette, Jeanette doesn't get «Jaime arrived at Work» (nor the departure or the trip): only the rest of the circle does |
| 🚗 **On the move** | *Still / Moving / Driving* status, current speed, and a «Moving» binary sensor |
| 🛣️ **Trips** | Automatic start and end, distance, duration, top speed, origin and destination. Distance and trips today |
| ⚠️ **Speeding** | Per-person limit (e.g. 100 km/h for the new teen driver). Confirmed by two consecutive readings to avoid false alerts from GPS jumps |
| 🔋 **Low battery** | The circle is alerted when someone's phone drops below the threshold |
| ✅ **Check-in** | A button (and action) that tells everyone «Jaime is at Home» or «near 742 Evergreen Terrace» |
| 🆘 **Ask for help** | A button that sends a **critical** alert (rings even on silent) with a link to the location |
| 📫 **Approximate address** | Optional: when someone is stopped away from their places, their address is shown |
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
   limit (0 = no alert), which phone(s) receive their alerts and whether they receive alerts at all.
4. **General options** (*Configure* button): which safety alerts are sent and to whom, battery threshold, and
   trip detection sensitivity.

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
| `sensor.<name>_place` | Place where they are, or their approximate address, or «away». Attributes: since when, coordinates, accuracy, last seen |
| `sensor.<name>_status` | `still` · `moving` · `driving`. During a trip: distance, duration and top speed so far |
| `sensor.<name>_speed` | km/h |
| `binary_sensor.<name>_moving` | On while a trip is in progress |
| `binary_sensor.<name>_speeding` | Only if they have a speed limit |
| `sensor.<name>_distance_today` | km travelled today and number of trips |
| `sensor.<name>_last_trip` | km of the last trip; origin, destination, times, duration and top speed in attributes |
| `sensor.<name>_phone_battery` | Battery % |
| `button.<name>_check_in` / `button.<name>_ask_for_help` | Alert the circle |

Per place: `sensor.<place>_people` (how many and who) and `binary_sensor.<place>_occupied`.

## Actions

```yaml
action: family_location.check_in
data:
  entity_id: person.jaime
  message: "Grabbing some bread"
```

```yaml
action: family_location.sos
data:
  entity_id: person.jeanette
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
      - person.jaime
      - person.jeanette
    hours_to_show: 12
  - type: entities
    entities:
      - sensor.jaime_place
      - sensor.jaime_status
      - sensor.jaime_speed
      - sensor.jaime_last_trip
      - sensor.jeanette_place
      - sensor.jeanette_status
  - type: horizontal-stack
    cards:
      - type: button
        entity: button.jaime_check_in
        tap_action: {action: toggle}
      - type: button
        entity: button.jaime_ask_for_help
        hold_action: {action: toggle}
        tap_action: {action: none}
```

Home Assistant keeps the location history: the map card with `hours_to_show` shows the route.

## Privacy

- Your location stays in your Home Assistant.
- OpenStreetMap (Nominatim) is only queried to look up a place's address when you create it and, if the option
  is on, to show the address of someone stopped away from their places. You can turn it off.

## Not supported (yet)

- Crash detection: it needs real-time phone sensors that the Home Assistant app doesn't expose.
- Alerts are only as timely as each phone's location updates: if a phone reports every 5 minutes, alerts arrive
  with that delay.

## Contributing

Issues and pull requests are welcome. Run the tests with:

```bash
pip install pytest-homeassistant-custom-component
pytest tests
```
