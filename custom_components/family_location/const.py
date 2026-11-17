"""Family Location constants."""

from __future__ import annotations

DOMAIN = "family_location"

# Subentry types
SUBENTRY_MEMBER = "member"
SUBENTRY_PLACE = "place"

# Member data
CONF_ENTITY = "entity_id"
CONF_NOTIFY = "notify"
CONF_RECEIVE_ALERTS = "receive_alerts"
CONF_SPEED_LIMIT = "speed_limit"                   # street limit (or the only one)
CONF_HIGHWAY_SPEED_LIMIT = "highway_speed_limit"   # 0 = same as the street limit

# Place data
CONF_ADDRESS = "address"
CONF_LOCATION = "location"
CONF_ZONE = "zone"
CONF_RADIUS = "radius"
CONF_ICON = "icon"
CONF_NOTIFY_ARRIVE = "notify_arrive"
CONF_NOTIFY_LEAVE = "notify_leave"
CONF_INSTANT = "arrive_instant"   # announce arrival on entry (without waiting for a stop)
CONF_WATCH = "watch"          # watched members (empty = everyone)
CONF_RECIPIENTS = "recipients"  # who receives the alert (empty = everyone else)

# General options
CONF_MOVING_SPEED = "moving_speed"
CONF_DRIVING_SPEED = "driving_speed"
CONF_STOP_MINUTES = "stop_minutes"
CONF_START_DISTANCE = "start_distance"
CONF_MAX_ACCURACY = "max_accuracy"
CONF_LOW_BATTERY = "low_battery"
CONF_NOTIFY_TRIPS = "notify_trips"
CONF_NOTIFY_SPEEDING = "notify_speeding"
CONF_NOTIFY_BATTERY = "notify_battery"
CONF_SAFETY_RECIPIENTS = "safety_recipients"
CONF_REVERSE_GEOCODE = "reverse_geocode"
CONF_SHOW_ZONES = "show_zones"   # show the HA zone name when not at a place
CONF_NOTIFY_SELF = "notify_self"

DEFAULT_RADIUS = 150
DEFAULT_SPEED_LIMIT = 0           # 0 = no speed alert
DEFAULT_MOVING_SPEED = 8.0        # km/h: above this the person is moving
DEFAULT_DRIVING_SPEED = 25.0      # km/h: above this the person is driving
DEFAULT_STOP_MINUTES = 5          # minutes without moving to end a trip
DEFAULT_START_DISTANCE = 250      # meters from the resting point to start a trip
DEFAULT_MAX_ACCURACY = 200        # meters: less accurate positions are ignored
DEFAULT_LOW_BATTERY = 15          # %

EVENT_NAME = f"{DOMAIN}_event"

# Event types (the «type» field of the HA event)
EV_ARRIVE = "arrive"
EV_LEAVE = "leave"
EV_TRIP_START = "trip_start"
EV_TRIP_END = "trip_end"
EV_SPEEDING = "speeding"
EV_LOW_BATTERY = "low_battery"
EV_CHECK_IN = "check_in"
EV_SOS = "sos"

# Movement states
STATUS_STILL = "still"
STATUS_MOVING = "moving"
STATUS_DRIVING = "driving"
STATUS_UNKNOWN = "unknown"
STATUSES = [STATUS_STILL, STATUS_MOVING, STATUS_DRIVING, STATUS_UNKNOWN]

AWAY = {"es": "fuera", "en": "away"}   # state of the place sensor when at no place

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"   # .format(entry_id)

SPEEDING_COOLDOWN_MIN = 10   # minutes between speeding alerts in the same trip
SPEEDING_CONFIRM = 2         # consecutive readings over the limit before alerting
MAX_PLAUSIBLE_KMH = 250      # computed speeds above this are discarded (GPS jumps)
TOGETHER_M = 300             # meters: two members this close are «together»
TOGETHER_WINDOW_MIN = 10     # minutes: window to say they arrived/left together
TOGETHER_GRACE_S = 90        # seconds to wait before alerting, so a companion's phone can report
BATTERY_HYSTERESIS = 5       # %: the battery alert re-arms after rising this much above the threshold
