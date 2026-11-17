/*
 * Family Location map card.
 *
 * Shows the people of the circle and the places as semi-transparent circles with their real radius.
 * Served by the Family Location integration, which also loads it in the frontend: no resource to add.
 *
 * Map drawing: Leaflet (BSD-2-Clause, see leaflet/LICENSE). Map data and tiles: © OpenStreetMap contributors.
 */

const CARD_VERSION = "0.4.0";
const PALETTE = ["#2563eb", "#db2777", "#f97316", "#dc2626", "#7c3aed", "#059669", "#0891b2", "#ca8a04", "#4f46e5"];
const PEOPLE_PALETTE = ["#0f766e", "#be185d", "#1d4ed8", "#b45309", "#6d28d9", "#15803d"];

const TEXT = {
  es: {
    still: "Quieto", moving: "En movimiento", driving: "Manejando", unknown: "Sin datos",
    battery: "Batería", speed: "Velocidad", updated: "Actualizado", now: "recién", min: "hace {n} min",
    hours: "hace {n} h", days: "hace {n} d", recenter: "Centrar", noData: "Sin ubicación",
    nothing: "No hay personas ni lugares con ubicación para mostrar.",
  },
  en: {
    still: "Still", moving: "Moving", driving: "Driving", unknown: "No data",
    battery: "Battery", speed: "Speed", updated: "Updated", now: "just now", min: "{n} min ago",
    hours: "{n} h ago", days: "{n} d ago", recenter: "Recenter", noData: "No location",
    nothing: "There are no people or places with a location to show.",
  },
};

// OpenStreetMap's standard tiles: free, no key, fine for the light use of a family dashboard.
// In dark mode the same tiles are shown with inverted colors.
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';

const LEAFLET_JS = new URL("leaflet/leaflet.js", import.meta.url).href;
const LEAFLET_CSS = new URL("leaflet/leaflet.css", import.meta.url).href;

let leafletPromise;
function loadLeaflet() {
  if (window.L && window.L.map) return Promise.resolve(window.L);
  if (!leafletPromise) {
    leafletPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = LEAFLET_JS;
      script.onload = () => (window.L ? resolve(window.L) : reject(new Error("Leaflet did not load")));
      script.onerror = () => {
        leafletPromise = undefined;
        reject(new Error("Leaflet could not be loaded"));
      };
      document.head.appendChild(script);
    });
  }
  return leafletPromise;
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const norm = (s) => String(s ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase();
const num = (v) => (v === null || v === undefined || v === "" || isNaN(Number(v)) ? null : Number(v));
const asItem = (v) => (typeof v === "string" ? { entity: v } : { ...(v || {}) });

class FamilyLocationMapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._fitted = false;
    this._signature = "";
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    for (const key of ["people", "places"]) {
      if (config[key] !== undefined && !Array.isArray(config[key])) throw new Error(`«${key}» must be a list`);
    }
    const opacity = config.opacity === undefined ? 0.2 : Number(config.opacity);
    if (isNaN(opacity) || opacity < 0 || opacity > 1) throw new Error("«opacity» must be between 0 and 1");
    this._config = { opacity, height: 400, labels: true, dark_mode: "auto", ...config };
    this._config.opacity = opacity;
    this._signature = "";
    this._fitted = false;
    if (this._map) this._update();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    if (!this._root) this._build();
    if (this._map) this._update();
  }

  set isPanel(value) {
    this._isPanel = !!value;
    this.toggleAttribute("panel", this._isPanel);
    this._applyHeight();
  }

  getCardSize() {
    return Math.max(3, Math.round((this._config?.height || 400) / 50));
  }

  getGridOptions() {
    return { columns: 12, rows: Math.max(4, Math.round((this._config?.height || 400) / 56)), min_rows: 3 };
  }

  connectedCallback() {
    if (this._map) setTimeout(() => this._map && this._map.invalidateSize(), 0);
  }

  disconnectedCallback() {
    // The map is kept: Lovelace re-attaches the same card when switching views.
  }

  // ------------------------------------------------------------------ building
  _t(key, n) {
    const lang = (this._config?.language || this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    const s = (TEXT[lang] || TEXT.en)[key] || TEXT.en[key] || key;
    return n === undefined ? s : s.replace("{n}", n);
  }

  _build() {
    this._root = document.createElement("ha-card");
    if (this._config.title) this._root.setAttribute("header", this._config.title);
    this.shadowRoot.innerHTML = `
      <link rel="stylesheet" href="${LEAFLET_CSS}">
      <style>
        :host { display: block; }
        :host([panel]) { height: 100%; }
        ha-card { overflow: hidden; display: flex; flex-direction: column; height: 100%; }
        .dark .leaflet-tile-pane { filter: invert(1) hue-rotate(180deg) brightness(.95) contrast(.9); }
        #map { flex: 1 1 auto; min-height: 120px; position: relative; z-index: 0;
               background: var(--secondary-background-color, #e5e7eb); }
        .empty { padding: 16px; color: var(--secondary-text-color); }
        .fl-person { background: none; border: none; }
        .fl-avatar { position: relative; width: 40px; height: 40px; border-radius: 50%; border: 3px solid;
          box-sizing: border-box; background: var(--card-background-color, #fff); overflow: visible;
          box-shadow: 0 2px 6px rgba(0,0,0,.35); display: flex; align-items: center; justify-content: center;
          font: 600 15px/1 var(--ha-font-family-body, Roboto, sans-serif); color: #fff; }
        .fl-avatar img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
        .fl-avatar .initials { width: 100%; height: 100%; border-radius: 50%; display: flex;
          align-items: center; justify-content: center; }
        .fl-avatar .badge { position: absolute; right: -6px; bottom: -6px; width: 20px; height: 20px;
          border-radius: 50%; background: var(--card-background-color, #fff); color: var(--primary-text-color);
          display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,.4);
          --mdc-icon-size: 14px; }
        .fl-avatar.stale { filter: grayscale(.8); opacity: .75; }
        .leaflet-tooltip.fl-label { background: transparent; border: none; box-shadow: none; padding: 0;
          font: 600 12px/1.2 var(--ha-font-family-body, Roboto, sans-serif); color: #111827;
          text-shadow: 0 0 3px #fff, 0 0 3px #fff, 0 0 3px #fff; white-space: nowrap; }
        .dark .leaflet-tooltip.fl-label { color: #f3f4f6; text-shadow: 0 0 3px #000, 0 0 3px #000, 0 0 3px #000; }
        .leaflet-tooltip.fl-label::before { display: none; }
        .leaflet-popup-content-wrapper, .leaflet-popup-tip {
          background: var(--card-background-color, #fff); color: var(--primary-text-color, #111); }
        .leaflet-popup-content { margin: 10px 14px; font: 13px/1.45 var(--ha-font-family-body, Roboto, sans-serif); }
        .leaflet-popup-content b { font-size: 14px; }
        .leaflet-popup-content .muted { color: var(--secondary-text-color, #666); }
        .leaflet-container a.leaflet-popup-close-button { color: var(--secondary-text-color, #666); }
        .dark .leaflet-control-attribution { background: rgba(0,0,0,.55); color: #ccc; }
        .dark .leaflet-control-attribution a { color: #9ecbff; }
        .recenter { position: absolute; top: 10px; right: 10px; z-index: 800; width: 34px; height: 34px;
          border-radius: 8px; border: none; cursor: pointer; display: flex; align-items: center;
          justify-content: center; background: var(--card-background-color, #fff); color: var(--primary-text-color);
          box-shadow: 0 1px 5px rgba(0,0,0,.4); --mdc-icon-size: 20px; }
      </style>`;
    this._mapEl = document.createElement("div");
    this._mapEl.id = "map";
    this._root.appendChild(this._mapEl);
    this.shadowRoot.appendChild(this._root);
    this._applyHeight();

    loadLeaflet()
      .then((L) => this._initMap(L))
      .catch((err) => {
        this._mapEl.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
      });
  }

  _applyHeight() {
    if (!this._mapEl) return;
    this._mapEl.style.height = this._isPanel ? "100%" : `${Number(this._config?.height) || 400}px`;
    if (this._map) this._map.invalidateSize();
  }

  _initMap(L) {
    this._L = L;
    const map = (this._map = L.map(this._mapEl, { zoomControl: true, attributionControl: true }));
    map.setView([0, 0], 2);
    map.createPane("flLabels").style.zIndex = 450; // above the circles, below the people
    map.createPane("flPeople").style.zIndex = 620;
    this._placesLayer = L.layerGroup().addTo(map);
    this._peopleLayer = L.layerGroup().addTo(map);
    map.on("zoomend", () => this._sizeShapes());

    const btn = document.createElement("button");
    btn.className = "recenter";
    btn.title = this._t("recenter");
    btn.innerHTML = '<ha-icon icon="mdi:crosshairs-gps"></ha-icon>';
    L.DomEvent.disableClickPropagation(btn);
    btn.addEventListener("click", () => this._fit(true));
    this._mapEl.appendChild(btn);

    new ResizeObserver(() => {
      map.invalidateSize();
      this._firstFit();
    }).observe(this._mapEl);
    this._update();
  }

  _setTiles() {
    const mode = this._config.dark_mode;
    const dark = mode === true || mode === "dark" || ((mode === "auto" || mode === undefined) && !!this._hass?.themes?.darkMode);
    if (this._tilesDark === dark && this._tiles) return;
    this._tilesDark = dark;
    if (!this._tiles) {
      this._tiles = this._L.tileLayer(TILES, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(this._map);
    }
    this._root.classList.toggle("dark", dark);
  }

  // ------------------------------------------------------------------ data
  _flEntities() {
    const hass = this._hass;
    return Object.values(hass.entities || {}).filter((e) => e.platform === "family_location" && hass.states[e.entity_id]);
  }

  _deviceName(entityId) {
    const dev = this._hass.devices?.[this._hass.entities?.[entityId]?.device_id];
    return dev ? dev.name_by_user || dev.name : null;
  }

  _placeSensors() {
    return this._flEntities()
      .map((e) => this._hass.states[e.entity_id])
      .filter((s) => s.attributes.radius !== undefined && Array.isArray(s.attributes.people));
  }

  _places() {
    const hass = this._hass;
    const sensors = this._placeSensors();
    const fromSensor = (s, item) => ({
      key: s.entity_id,
      name: item.name || this._deviceName(s.entity_id) || s.attributes.friendly_name,
      lat: num(s.attributes.latitude), lon: num(s.attributes.longitude), radius: num(s.attributes.radius),
      color: item.color,
    });
    const fromZone = (z, item) => ({
      key: z.entity_id, name: item.name || z.attributes.friendly_name,
      lat: num(z.attributes.latitude), lon: num(z.attributes.longitude), radius: num(z.attributes.radius),
      color: item.color,
    });

    const items = this._config.places ? this._config.places.map(asItem) : sensors.map((s) => ({ entity: s.entity_id }));
    const out = [];
    for (const item of items) {
      const id = item.entity || item.place || "";
      let place = null;
      if (id.startsWith("sensor.") && hass.states[id]) {
        place = fromSensor(hass.states[id], item);
      } else if (id.startsWith("zone.")) {
        const linked = sensors.find((s) => s.attributes.zone === id);
        if (linked) place = fromSensor(linked, item);
        else if (hass.states[id]) place = fromZone(hass.states[id], item);
      } else if (id) {
        const wanted = norm(id);
        const s = sensors.find((x) => norm(this._deviceName(x.entity_id)) === wanted);
        if (s) place = fromSensor(s, item);
        else {
          const z = Object.values(hass.states).find(
            (x) => x.entity_id.startsWith("zone.") && norm(x.attributes.friendly_name) === wanted);
          if (z) place = fromZone(z, item);
        }
      }
      if (place && place.lat !== null && place.lon !== null && !out.some((p) => p.key === place.key)) out.push(place);
    }
    out.forEach((p, i) => (p.color = p.color || PALETTE[i % PALETTE.length]));
    return out;
  }

  _memberSensors(entityId) {
    // the «place» sensor of the Family Location member that follows this person or one of their trackers
    const hass = this._hass;
    const person = hass.states[entityId];
    const tracked = new Set([entityId, ...((person && person.attributes.device_trackers) || [])]);
    const name = norm(person?.attributes.friendly_name);
    const fl = this._flEntities();
    const placeSensor =
      fl.find((e) => tracked.has(hass.states[e.entity_id].attributes.tracked_entity)) ||
      fl.find((e) => "in_place" in hass.states[e.entity_id].attributes && norm(this._deviceName(e.entity_id)) === name);
    if (!placeSensor) return {};
    const same = fl.filter((e) => e.device_id && e.device_id === placeSensor.device_id).map((e) => hass.states[e.entity_id]);
    return {
      place: hass.states[placeSensor.entity_id],
      status: same.find((s) => (s.attributes.options || []).includes("driving")),
      battery: same.find((s) => s.attributes.device_class === "battery"),
      speed: same.find((s) => s.attributes.device_class === "speed" && "speed_limit_kmh" in s.attributes),
    };
  }

  _people() {
    const hass = this._hass;
    const items = this._config.people
      ? this._config.people.map(asItem)
      : Object.keys(hass.states).filter((id) => id.startsWith("person.")).map((entity) => ({ entity }));
    const out = [];
    items.forEach((item, i) => {
      const st = hass.states[item.entity];
      if (!st) return;
      const lat = num(st.attributes.latitude);
      const lon = num(st.attributes.longitude);
      if (lat === null || lon === null) return;
      out.push({
        key: item.entity,
        name: item.name || st.attributes.friendly_name || item.entity,
        lat, lon,
        picture: st.attributes.entity_picture || null,
        color: item.color || PEOPLE_PALETTE[i % PEOPLE_PALETTE.length],
        updated: st.last_updated,
        member: this._memberSensors(item.entity),
      });
    });
    return out;
  }

  // ------------------------------------------------------------------ drawing
  _update() {
    if (!this._map || !this._hass) return;
    this._setTiles();
    const places = this._places();
    const people = this._people();
    const sig = JSON.stringify([
      places.map((p) => [p.key, p.name, p.lat, p.lon, p.radius, p.color]),
      people.map((p) => [p.key, p.name, p.lat, p.lon, p.picture, p.color, p.updated,
        p.member.place?.state, p.member.status?.state, p.member.battery?.state, p.member.speed?.state]),
      this._tilesDark, this._config.opacity, this._config.labels,
    ]);
    if (sig === this._signature) return;
    this._signature = sig;
    this._lastPlaces = places;
    this._lastPeople = people;
    this._drawPlaces(places);
    this._drawPeople(people);
    this._firstFit();
  }

  _firstFit() {
    // only once the map has a size on screen: before that Leaflet would zoom all the way in
    if (this._fitted || !this._map) return;
    if (!(this._lastPlaces?.length || this._lastPeople?.length)) return;
    if (!this._mapEl.clientWidth || !this._mapEl.clientHeight) {
      // not on screen yet (e.g. a view that is not open): try again shortly
      clearTimeout(this._fitTimer);
      this._fitTimer = setTimeout(() => this._firstFit(), 500);
      return;
    }
    this._fitted = true;
    this._fit(false);
  }

  _drawPlaces(places) {
    const L = this._L;
    this._placesLayer.clearLayers();
    this._shapes = [];
    for (const p of places) {
      const style = { color: p.color, weight: 2, opacity: 0.85, fillColor: p.color,
        fillOpacity: this._config.opacity, interactive: false };
      // the real radius, and a minimum size on screen so small places stay visible when zoomed out
      const real = L.circle([p.lat, p.lon], { ...style, radius: p.radius || 100 });
      const dot = L.circleMarker([p.lat, p.lon], { ...style, radius: this._minPx() });
      this._shapes.push({ p, real, dot });
      if (this._config.labels !== false) {
        const label = L.tooltip({ permanent: true, direction: "center", className: "fl-label", pane: "flLabels",
          interactive: false, offset: [0, 0] })
          .setLatLng([p.lat, p.lon])
          .setContent(esc(p.name));
        this._shapes[this._shapes.length - 1].label = label;
      }
    }
    this._sizeShapes();
  }

  _minPx() {
    return Number(this._config.min_circle_px ?? 10);
  }

  _sizeShapes() {
    // after every zoom: the real circle when it is big enough on screen, otherwise the fixed-size one
    if (!this._shapes || !this._map) return;
    const zoom = this._map.getZoom();
    for (const s of this._shapes) {
      const mPerPx = (40075016.686 * Math.cos((s.p.lat * Math.PI) / 180)) / 2 ** (zoom + 8);
      const px = (s.p.radius || 100) / mPerPx;
      const useReal = px >= this._minPx();
      const show = useReal ? s.real : s.dot;
      const hide = useReal ? s.dot : s.real;
      if (this._placesLayer.hasLayer(hide)) this._placesLayer.removeLayer(hide);
      if (!this._placesLayer.hasLayer(show)) this._placesLayer.addLayer(show);
      if (s.label) {
        // the name goes just below the circle, so it never hides the people standing in it
        const below = (Math.max(px, this._minPx()) + 9) * mPerPx;
        s.label.setLatLng([s.p.lat - below / 111320, s.p.lon]);
        if (!this._placesLayer.hasLayer(s.label)) this._placesLayer.addLayer(s.label);
      }
    }
  }

  _drawPeople(people) {
    const L = this._L;
    this._peopleLayer.clearLayers();
    // people standing in the same spot are spread side by side
    const groups = new Map();
    for (const p of people) {
      const k = `${p.lat.toFixed(3)},${p.lon.toFixed(3)}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(p);
    }
    for (const group of groups.values()) {
      group.forEach((p, i) => {
        const dx = (i - (group.length - 1) / 2) * 34;
        const marker = L.marker([p.lat, p.lon], {
          pane: "flPeople", keyboard: false, title: p.name,
          icon: L.divIcon({ className: "fl-person", html: this._avatar(p), iconSize: [40, 40], iconAnchor: [20 - dx, 20],
            popupAnchor: [dx, -22] }),
        });
        marker.bindPopup(() => this._popup(p), { autoPanPadding: [20, 20] });
        this._peopleLayer.addLayer(marker);
      });
    }
  }

  _avatar(p) {
    const status = p.member.status?.state;
    const badge = status === "driving" ? "mdi:car" : status === "moving" ? "mdi:walk" : null;
    const stale = p.updated && Date.now() - new Date(p.updated).getTime() > 6 * 3600e3;
    const initials = p.name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
    const inner = p.picture
      ? `<img src="${esc(this._hass.hassUrl ? this._hass.hassUrl(p.picture) : p.picture)}" alt="">`
      : `<span class="initials" style="background:${esc(p.color)}">${esc(initials)}</span>`;
    return `<div class="fl-avatar${stale ? " stale" : ""}" style="border-color:${esc(p.color)}">${inner}${
      badge ? `<span class="badge"><ha-icon icon="${badge}"></ha-icon></span>` : ""}</div>`;
  }

  _ago(iso) {
    if (!iso) return "";
    const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (min < 2) return this._t("now");
    if (min < 60) return this._t("min", min);
    if (min < 48 * 60) return this._t("hours", Math.round(min / 60));
    return this._t("days", Math.round(min / 1440));
  }

  _popup(p) {
    const m = p.member;
    const lines = [`<b>${esc(p.name)}</b>`];
    if (m.place && m.place.state && !["unknown", "unavailable"].includes(m.place.state)) lines.push(esc(m.place.state));
    if (m.status && TEXT.en[m.status.state]) {
      let s = this._t(m.status.state);
      if (m.status.state === "driving" && m.speed && num(m.speed.state) !== null) s += ` · ${Math.round(num(m.speed.state))} km/h`;
      lines.push(s);
    }
    if (m.battery && num(m.battery.state) !== null) lines.push(`${this._t("battery")}: ${Math.round(num(m.battery.state))}%`);
    const seen = m.place?.attributes.last_seen || p.updated;
    if (seen) lines.push(`<span class="muted">${this._t("updated")} ${this._ago(seen)}</span>`);
    return lines.join("<br>");
  }

  _fit(animate = true) {
    const L = this._L;
    const points = [];
    const onlyPeople = this._config.fit === "people" && this._lastPeople?.length;
    if (!onlyPeople) {
      for (const p of this._lastPlaces || []) {
        const b = L.latLng(p.lat, p.lon).toBounds((p.radius || 100) * 2);
        points.push(b.getNorthWest(), b.getSouthEast());
      }
    }
    for (const p of this._lastPeople || []) points.push(L.latLng(p.lat, p.lon));
    if (!points.length) return;
    this._map.invalidateSize();
    this._map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 16, animate });
  }
}

if (!customElements.get("family-location-map-card")) {
  customElements.define("family-location-map-card", FamilyLocationMapCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "family-location-map-card",
    name: "Family Location map",
    description: "People and places of the circle, with each place drawn as a circle of its real radius.",
    documentationURL: "https://github.com/Ctuna89/HA-Family-Location#map-card",
  });
  console.info(`%c FAMILY-LOCATION-MAP-CARD %c ${CARD_VERSION} `, "background:#2563eb;color:#fff", "background:#e5e7eb;color:#111");
}
