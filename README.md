# Family Location 📍

**Un reemplazo de Life360 que vive dentro de tu Home Assistant.** Lugares por dirección, avisos de llegada y
salida para toda la familia («Jaime llegó a casa», «Jeanette llegó al trabajo»), quién está en movimiento,
viajes con distancia y velocidad máxima, avisos de exceso de velocidad, batería baja, check-in y botón de ayuda.

Sin cuentas, sin suscripción y sin que tu ubicación pase por servidores de terceros: la posición la entrega la
**app de Home Assistant** (Companion) del celular de cada uno, y todo se calcula en tu Home Assistant.

## Qué incluye

| | |
|---|---|
| 🏠 **Lugares por dirección** | Escribes «Av. Apoquindo 3000, Las Condes», se busca en OpenStreetMap, confirmas el punto en el mapa y ajustas el radio. También puedes marcarlo directo en el mapa o usar una zona que ya tengas |
| 🔔 **Llegadas y salidas** | Aviso al resto del círculo cuando alguien llega o sale de un lugar. Por lugar eliges si se avisa al llegar, al salir, de quién (p. ej. solo los niños en el colegio) y a quién |
| 🚦 **Sin falsas llegadas** | Un viaje termina recién tras 5 minutos quieto (configurable): un semáforo o un taco no lo cortan. Y la llegada a un lugar que no sea Casa se avisa solo cuando la persona se queda ahí esos 5 minutos; pasar por al lado o parar en un semáforo frente al trabajo no cuenta |
| 👨‍👩‍👧 **Si van juntos, no se avisan** | Si Jaime va con Jeanette, a Jeanette no le llega «Jaime llegó al Trabajo» (ni la salida ni el viaje): solo al resto del círculo |
| 🚗 **En movimiento** | Estado *Quieto / En movimiento / Conduciendo*, velocidad actual, sensor binario «En movimiento» |
| 🛣️ **Viajes** | Inicio y fin automáticos, distancia, duración, velocidad máxima, origen y destino. Distancia y viajes del día |
| ⚠️ **Exceso de velocidad** | Límite por persona (p. ej. 100 km/h para el hijo que recién maneja). Se confirma con dos lecturas seguidas para evitar falsos avisos por saltos del GPS |
| 🔋 **Batería baja** | Aviso al círculo cuando el teléfono de alguien baja del umbral |
| ✅ **Check-in** | Botón (y acción) que avisa a todos «Jaime está en Casa» o «cerca de Av. Matta 100» |
| 🆘 **Pedir ayuda** | Botón que envía una alerta **crítica** (suena aunque el teléfono esté en silencio) con un enlace a la ubicación |
| 📫 **Dirección aproximada** | Opcional: cuando alguien está detenido fuera de sus lugares se muestra la dirección |
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
3. **Añadir o editar integrantes:** botón **«Añadir integrante»**, o el lápiz junto a cada uno. Ahí defines su
   límite de velocidad (0 = sin aviso), a qué celular(es) se le envían los avisos y si los recibe.
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
| `sensor.<nombre>_lugar` | Lugar donde está, o su dirección aproximada, o «fuera». Atributos: desde cuándo, coordenadas, precisión, última vez visto |
| `sensor.<nombre>_estado` | quieto · en_movimiento · conduciendo. Durante un viaje: distancia, duración y velocidad máxima hasta ahora |
| `sensor.<nombre>_velocidad` | km/h |
| `binary_sensor.<nombre>_en_movimiento` | Encendido mientras hay un viaje en curso |
| `binary_sensor.<nombre>_exceso_de_velocidad` | Solo si tiene límite configurado |
| `sensor.<nombre>_distancia_hoy` | km recorridos hoy y número de viajes |
| `sensor.<nombre>_ultimo_viaje` | km del último viaje; origen, destino, horas, duración y velocidad máxima en atributos |
| `sensor.<nombre>_bateria_del_telefono` | % de batería |
| `button.<nombre>_check_in` / `button.<nombre>_pedir_ayuda` | Avisan al círculo |

Por cada lugar: `sensor.<lugar>_personas` (cuántos y quiénes) y `binary_sensor.<lugar>_hay_alguien`.

## Acciones

```yaml
action: family_location.check_in
data:
  entity_id: person.jaime
  message: "Pasé a comprar pan"
```

```yaml
action: family_location.sos
data:
  entity_id: person.jeanette
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
      - person.jaime
      - person.jeanette
    hours_to_show: 12
  - type: entities
    entities:
      - sensor.jaime_lugar
      - sensor.jaime_estado
      - sensor.jaime_velocidad
      - sensor.jaime_ultimo_viaje
      - sensor.jeanette_lugar
      - sensor.jeanette_estado
  - type: horizontal-stack
    cards:
      - type: button
        entity: button.jaime_check_in
        tap_action: {action: toggle}
      - type: button
        entity: button.jaime_pedir_ayuda
        hold_action: {action: toggle}
        tap_action: {action: none}
```

El historial de recorridos lo guarda Home Assistant: la tarjeta de mapa con `hours_to_show` muestra la ruta.

## Privacidad

- La ubicación se queda en tu Home Assistant.
- Solo se consulta OpenStreetMap (Nominatim) para buscar la dirección de un lugar al crearlo y, si la opción
  está activada, para mostrar la dirección de alguien detenido fuera de sus lugares. Puedes desactivarla.

## Lo que no hace (todavía)

- Detección de choques: requiere los sensores del teléfono en tiempo real que la app de Home Assistant no expone.
- Funciona con la frecuencia de ubicación que entregue cada teléfono: si el teléfono informa cada 5 minutos, los
  avisos llegan con ese desfase.
