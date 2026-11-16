"""Constantes de Family Location."""

from __future__ import annotations

DOMAIN = "family_location"

# Tipos de subentrada
SUBENTRY_MEMBER = "member"
SUBENTRY_PLACE = "place"

# Datos de un integrante
CONF_ENTITY = "entity_id"
CONF_NOTIFY = "notify"
CONF_RECEIVE_ALERTS = "receive_alerts"
CONF_SPEED_LIMIT = "speed_limit"

# Datos de un lugar
CONF_ADDRESS = "address"
CONF_LOCATION = "location"
CONF_ZONE = "zone"
CONF_RADIUS = "radius"
CONF_ICON = "icon"
CONF_NOTIFY_ARRIVE = "notify_arrive"
CONF_NOTIFY_LEAVE = "notify_leave"
CONF_INSTANT = "arrive_instant"   # avisar la llegada apenas entra (sin esperar a que se detenga)
CONF_WATCH = "watch"          # integrantes vigilados (vacío = todos)
CONF_RECIPIENTS = "recipients"  # quién recibe el aviso (vacío = todos los demás)

# Opciones generales
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
CONF_NOTIFY_SELF = "notify_self"

DEFAULT_RADIUS = 150
DEFAULT_SPEED_LIMIT = 0           # 0 = sin aviso de velocidad
DEFAULT_MOVING_SPEED = 8.0        # km/h: sobre esto se considera que va en movimiento
DEFAULT_DRIVING_SPEED = 25.0      # km/h: sobre esto se considera que va conduciendo
DEFAULT_STOP_MINUTES = 5          # minutos sin moverse para dar por terminado un viaje
DEFAULT_START_DISTANCE = 250      # metros desde el punto de reposo para empezar un viaje
DEFAULT_MAX_ACCURACY = 200        # metros: posiciones menos precisas se ignoran
DEFAULT_LOW_BATTERY = 15          # %

EVENT_NAME = f"{DOMAIN}_event"

# Tipos de evento (van en el campo «type» del evento de HA)
EV_ARRIVE = "arrive"
EV_LEAVE = "leave"
EV_TRIP_START = "trip_start"
EV_TRIP_END = "trip_end"
EV_SPEEDING = "speeding"
EV_LOW_BATTERY = "low_battery"
EV_CHECK_IN = "check_in"
EV_SOS = "sos"

# Estados de movimiento
STATUS_STILL = "quieto"
STATUS_MOVING = "en_movimiento"
STATUS_DRIVING = "conduciendo"
STATUS_UNKNOWN = "desconocido"
STATUSES = [STATUS_STILL, STATUS_MOVING, STATUS_DRIVING, STATUS_UNKNOWN]

AWAY = "fuera"

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"   # .format(entry_id)

SPEEDING_COOLDOWN_MIN = 10   # minutos entre avisos de exceso de velocidad del mismo viaje
SPEEDING_CONFIRM = 2         # lecturas seguidas sobre el límite para avisar
MAX_PLAUSIBLE_KMH = 250      # velocidades calculadas sobre esto se descartan (saltos de GPS)
TOGETHER_M = 300             # metros: a esta distancia dos integrantes «van juntos»
TOGETHER_WINDOW_MIN = 10     # minutos: margen para decir que llegaron/salieron juntos
TOGETHER_GRACE_S = 90        # segundos de espera antes de avisar, para que el teléfono del acompañante informe
BATTERY_HYSTERESIS = 5       # %: el aviso de batería se rearma al subir esto sobre el umbral
