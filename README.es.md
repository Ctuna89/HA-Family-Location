# Family Location 📍

🇬🇧 [Read in English](README.md)

**Un reemplazo de Life360 que vive dentro de tu Home Assistant.** Lugares por dirección, avisos de llegada y
salida para toda la familia («James llegó a casa», «Janet llegó al trabajo»), quién está en movimiento,
viajes con distancia y velocidad máxima, avisos de exceso de velocidad, batería baja, check-in y botón de ayuda.

Sin cuentas, sin suscripción y sin que tu ubicación pase por servidores de terceros: la posición la entrega la
**app de Home Assistant** (Companion) del celular de cada uno, y todo se calcula en tu Home Assistant.

## Qué incluye

| | |
|---|---|
| 🏠 **Lugares por dirección** | Escribes «Av. Apoquindo 3000, Las Condes», se busca en OpenStreetMap, confirmas el punto en el mapa y ajustas el radio. También puedes marcarlo directo en el mapa o usar una zona que ya tengas |
| 🔔 **Llegadas y salidas** | Aviso al resto del círculo cuando alguien llega o sale de un lugar. Por lugar eliges si se avisa al llegar, al salir, de quién (p. ej. solo los niños en el colegio) y a quién |
| 🚦 **Sin falsas llegadas** | Un viaje termina recién tras 5 minutos quieto (configurable): un semáforo o un taco no lo cortan. Y la llegada a un lugar que no sea Casa se avisa solo cuando la persona se queda ahí esos 5 minutos; pasar por al lado o parar en un semáforo frente al trabajo no cuenta |
| 👨‍👩‍👧 **Si van juntos, no se avisan** | Si James va con Janet, a Janet no le llega «James llegó al Trabajo» (ni la salida ni el viaje): solo al resto del círculo |
| 🚗 **En movimiento** | Estado *Quieto / En movimiento / Conduciendo*, velocidad actual, sensor binario «En movimiento» |
| 🛣️ **Viajes** | Inicio y fin automáticos, distancia, duración, velocidad máxima, origen y destino. Distancia y viajes del día |
| ⚠️ **Exceso de velocidad** | Límite por persona (p. ej. 100 km/h para el hijo que recién maneja), opcionalmente separado en límite de **calle** y de **autopista** (p. ej. 60 / 120 km/h). Se confirma con dos lecturas seguidas para evitar falsos avisos por saltos del GPS |
| 🏆 **Ranking semanal** | Distancia, viajes, velocidad máxima y excesos de cada persona en la semana (lunes a domingo), más un ranking del círculo |
| 🔋 **Batería baja** | Aviso al círculo cuando el teléfono de alguien baja del umbral |
| ✅ **Check-in** | Botón (y acción) que avisa a todos «James está en Casa» o «cerca de Av. Matta 100» |
| 🆘 **Pedir ayuda** | Botón que envía una alerta **crítica** (suena aunque el teléfono esté en silencio o en No molestar, una vez que cada teléfono lo permite: ver más abajo) con un enlace a la ubicación |
| 🗺️ **También tus zonas de HA** | Si alguien está dentro de una zona de Home Assistant que no agregaste como lugar (por ejemplo «Gimnasio»), se muestra el nombre de la zona en vez de la dirección. Opcional, activado por defecto |
| 📫 **Dirección aproximada** | Opcional: cuando alguien está detenido fuera de sus lugares y zonas se muestra la dirección |
| 🤖 **Eventos para automatizar** | Cada llegada, salida, viaje, exceso, batería, check-in y SOS genera el evento `family_location_event` |

## Requisitos

1. **Home Assistant 2025.3 o superior.**
2. La **app de Home Assistant** instalada en el teléfono de cada integrante, con la ubicación en **«Permitir
   siempre»** y una **persona** de Home Assistant asociada a ese teléfono.
3. Para avisos de velocidad útiles, el teléfono debe informar la ubicación seguido mientras se mueve:
   - **Android:** *Ajustes de la app → Sensores → Ubicación en segundo plano* activado; idealmente activa el
     *Modo de alta precisión* (puedes limitarlo a cuando el teléfono está conectado al auto por Bluetooth o
     Android Auto).
   - **iPhone:** iOS informa por cambios significativos de ubicación; las velocidades se calculan entre posiciones,
     así que en iPhone el aviso de velocidad es menos inmediato.

## Instalación

[![Añadir a HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Ctuna89&repository=HA-Family-Location&category=integration)

1. HACS → menú ⋮ → *Repositorios personalizados* → agrega este repositorio como **Integración**.
2. Instala **Family Location** y reinicia Home Assistant.
3. *Ajustes → Dispositivos y servicios → Añadir integración → Family Location.*

## Configuración

1. **Crear el círculo:** nombre («Familia»), quiénes lo forman (se detecta sola la notificación del celular de
   cada persona) y si se agrega «Casa» como primer lugar.
2. **Añadir lugares:** en la página de la integración, botón **«Añadir lugar»**:
   1. nombre y dirección (o una zona existente, o nada para marcarlo en el mapa);
   2. confirmas el punto y el radio en el mapa;
   3. eliges los avisos: al llegar / al salir, de quiénes y a quiénes.
3. **Añadir o editar integrantes:** botón **«Añadir integrante»**, o el lápiz junto a cada uno. Ahí defines sus
   límites de velocidad (0 = sin aviso), a qué celular(es) se le envían los avisos y si los recibe.
   - **Solo límite de calle:** se usa en todas partes.
   - **Límite de calle y de autopista:** cuando la persona supera el límite de calle, se le pregunta a
     OpenStreetMap si va por autopista, y se usa el límite que corresponde. Las respuestas se guardan, así que
     el mismo tramo no se consulta dos veces. Mientras no se sabe el tipo de vía, se usa el límite más alto (el
     de autopista), así una vía desconocida nunca genera un falso aviso.
4. **Opciones generales** (botón *Configurar*): qué avisos de seguridad se envían y a quién, umbral de batería,
   y la sensibilidad de la detección de viajes.

Nadie recibe sus propios avisos (se puede cambiar en las opciones).

### Cómo decide cuándo avisar

- **Casa** avisa la llegada apenas entras (para que la familia sepa al tiro). En los demás lugares la opción
  *«Avisar apenas entra»* viene apagada: la llegada se confirma tras quedarte detenido ahí los minutos
  configurados (5 por defecto) y el aviso dice la hora en que entraste. Puedes activarla por lugar.
- **Viajes:** empiezan al moverte más de 250 m desde donde estabas o al superar 8 km/h, y terminan solo tras
  5 minutos sin moverte. Detenerte 2–3 minutos en un semáforo o un taco no corta el viaje.
- **Acompañantes:** los avisos de llegada, salida y viaje esperan 90 segundos. Si en ese tiempo otro integrante
  está con la persona (llegó al mismo lugar con menos de 10 minutos de diferencia, o salieron juntos y están a
  menos de ~300 m), a ese integrante no se le envía el aviso. El exceso de velocidad, la batería baja, el
  check-in y el pedido de ayuda se avisan siempre y al instante.

## Entidades

Por cada integrante (dispositivo con su nombre):

| Entidad | Qué muestra |
|---|---|
| `sensor.<nombre>_lugar` | Lugar donde está, o la zona de Home Assistant en que está, o su dirección aproximada, o «fuera». Atributos: desde cuándo, zona, coordenadas, precisión, última vez visto |
| `sensor.<nombre>_estado` | Quieto · En movimiento · Conduciendo (valores internos: `still`, `moving`, `driving`). Durante un viaje: distancia, duración y velocidad máxima hasta ahora |
| `sensor.<nombre>_velocidad` | km/h |
| `binary_sensor.<nombre>_en_movimiento` | Encendido mientras hay un viaje en curso |
| `binary_sensor.<nombre>_exceso_de_velocidad` | Solo si tiene límite configurado |
| `sensor.<nombre>_distancia_hoy` | km recorridos hoy y número de viajes |
| `sensor.<nombre>_ultimo_viaje` | km del último viaje; origen, destino, horas, duración y velocidad máxima en atributos |
| `sensor.<nombre>_distancia_esta_semana` / `_velocidad_maxima_esta_semana` / `_excesos_de_velocidad_esta_semana` | Datos de la semana (lunes a domingo); los de la semana pasada en el atributo `last_week` |
| `sensor.<nombre>_bateria_del_telefono` | % de batería |
| `button.<nombre>_check_in` / `button.<nombre>_pedir_ayuda` | Avisan al círculo |

Por cada lugar: `sensor.<lugar>_personas` (cuántos y quiénes) y `binary_sensor.<lugar>_hay_alguien`.

## Acciones

```yaml
action: family_location.check_in
data:
  entity_id: person.james
  message: "Pasé a comprar pan"
```

```yaml
action: family_location.sos
data:
  entity_id: person.janet
```

## Automatizaciones con el evento

```yaml
triggers:
  - trigger: event
    event_type: family_location_event
    event_data:
      type: arrive
      place: Colegio
actions:
  - action: light.turn_on
    target:
      entity_id: light.entrada
```

Tipos: `arrive`, `leave`, `trip_start`, `trip_end`, `speeding`, `low_battery`, `check_in`, `sos`. El evento trae
`member`, `entity_id`, `place`, `latitude`, `longitude` y los datos del viaje o la velocidad.

## Tarjeta de ejemplo

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
      - sensor.james_lugar
      - sensor.james_estado
      - sensor.james_velocidad
      - sensor.james_ultimo_viaje
      - sensor.janet_lugar
      - sensor.janet_estado
  - type: horizontal-stack
    cards:
      - type: button
        entity: button.james_check_in
        tap_action: {action: toggle}
      - type: button
        entity: button.james_pedir_ayuda
        hold_action: {action: toggle}
        tap_action: {action: none}
```

El historial de recorridos lo guarda Home Assistant: la tarjeta de mapa con `hours_to_show` muestra la ruta.

## Tarjeta de mapa

La integración trae su propia tarjeta de mapa. Cada lugar se dibuja como un círculo semitransparente con su
radio real, y cada persona con su foto (o sus iniciales). Al tocar a alguien se ve dónde está, si está quieto o
manejando, su batería y cuándo informó su teléfono por última vez. No hay que instalar nada: la tarjeta se carga
sola al configurar la integración (recarga la página o la app después de actualizar).

```yaml
type: custom:family-location-map-card
people:
  - person.jaime
  - entity: person.jeanette
    color: "#db2777"
places:            # nombres de lugares, sensores de Family Location o zonas de Home Assistant
  - Casa
  - entity: zone.oficina
    color: "#7c3aed"
```

| Opción | Por defecto | |
|---|---|---|
| `people` | todas las `person` con ubicación | `person.*` o `device_tracker.*`, opcionalmente con `name` y `color` |
| `places` | todos los lugares de Family Location | nombre del lugar, `sensor.<lugar>_personas`, o cualquier `zone.*`, opcionalmente con `name` y `color` |
| `opacity` | `0.2` | opacidad del relleno de los círculos (0–1) |
| `min_circle_px` | `10` | con el mapa alejado, los lugares chicos se dibujan con este radio en píxeles para que se sigan viendo |
| `labels` | `true` | nombre de cada lugar bajo su círculo |
| `height` | `400` | alto en píxeles (en una vista de panel ocupa toda la pantalla) |
| `dark_mode` | `auto` | `auto` sigue a Home Assistant, o `light` / `dark` |
| `fit` | `all` | `people` centra el mapa solo en las personas |
| `tile_url` | proxy de mapas de Home Assistant | otro proveedor de mapas, p. ej. `https://tiles.example.com/{z}/{x}/{y}.png` |
| `tile_url_dark` | | mapas oscuros de ese proveedor (sin esto, los claros se muestran con colores invertidos) |
| `tile_attribution` | | texto de atribución (HTML) de ese proveedor |
| `title`, `language` | | título de la tarjeta; `es` o `en` (por defecto, el idioma del usuario) |

Por defecto los mapas de fondo pasan por el **proxy de mapas de Home Assistant**, el mismo que usa su tarjeta
de mapa: Home Assistant pide los mapas a [OpenStreetMap](https://www.openstreetmap.org/copyright) por el
navegador, así que funcionan en la red local y también por Nabu Casa o cualquier otra dirección remota, sin
claves. OpenStreetMap ve la zona que se muestra, no dónde está tu familia. En modo oscuro se muestran con los
colores invertidos. En versiones de Home Assistant sin ese proxy, la tarjeta pide los mapas directamente a
OpenStreetMap, lo que funciona en la red local pero no por dominios compartidos como `ui.nabu.casa`. Si usas
`tile_url`, respeta las condiciones de uso de ese proveedor.

### Ranking semanal

`sensor.<círculo>_ranking_semanal` muestra quién manejó más esta semana, con el ranking completo en el atributo
`ranking` (y además `fastest` y `most_speeding`). Una tarjeta Markdown:

```yaml
type: markdown
title: 🏆 Esta semana
content: >
  {% for r in state_attr('sensor.familia_ranking_semanal', 'ranking') %}
  **{{ r.position }}. {{ r.name }}** · {{ r.distance_km }} km · {{ r.trips }} viajes ·
  máx. {{ r.max_speed_kmh }} km/h · {{ r.speeding }} excesos
  {% endfor %}
```

## Que «Pedir ayuda» suene en silencio

Cada teléfono que recibe avisos tiene que permitirlo una vez:

- **iPhone:** *Ajustes → Notificaciones → Home Assistant →* activa **Alertas críticas**.
- **Android:** el aviso suena como una alarma al volumen máximo (canal `alarm_stream_max`). Después de recibir
  el primero:
  1. *Ajustes → Apps → Home Assistant → Notificaciones →* abre el canal **alarm_stream_max** y activa
     **Ignorar No molestar**.
  2. En *Ajustes → Sonido → No molestar*, revisa que las **Alarmas** estén permitidas (en «Silencio total» no
     lo están).

Haz una prueba con `family_location.sos` (o el botón) para confirmar que suena.

## Privacidad

- La ubicación se queda en tu Home Assistant.
- Solo se consulta OpenStreetMap (Nominatim) para buscar la dirección de un lugar al crearlo y, si la opción
  está activada, para mostrar la dirección de alguien detenido fuera de sus lugares. Puedes desactivarla.
- Si defines límites separados de calle y autopista para alguien, también se consulta a OpenStreetMap el tipo
  de vía donde está, solo mientras supera su límite de calle. Deja el límite de autopista en 0 para evitarlo.

## Lo que no hace (todavía)

- Detección de choques: requiere los sensores del teléfono en tiempo real que la app de Home Assistant no expone.
- Funciona con la frecuencia de ubicación que entregue cada teléfono: si el teléfono informa cada 5 minutos, los
  avisos llegan con ese desfase.

## Créditos

- La tarjeta de mapa dibuja con [Leaflet](https://leafletjs.com) 1.9.4 (licencia BSD 2-Clause,
  © Volodymyr Agafonkin y CloudMade), incluido en `custom_components/family_location/frontend/leaflet/` con su
  licencia.
- Datos y mapas © colaboradores de [OpenStreetMap](https://www.openstreetmap.org/copyright).
