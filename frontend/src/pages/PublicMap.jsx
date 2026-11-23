import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, ZoomControl, ScaleControl, Pane, CircleMarker, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { useSearchParams } from 'react-router-dom';
import LayerControl from '../components/Map/LayerControl';
import HazardPanel, { clearHistoryCache } from '../components/Map/HazardPanel';
import BarangayPanel from '../components/Map/BarangayPanel';
import { useSusceptibility } from '../components/Map/susceptibility';
import PurokLayer from '../components/Map/PurokLayer';
import PurokHistoryLayer from '../components/Map/PurokHistoryLayer';
import { PUROK_HAZARD_AREA, PUROK_OF_HAZARD, hasEstimates, purokAt, purokStyle, purokTooltip, puroksOf } from '../components/Map/purokStyle';
import { byPurok, historyLine } from '../components/Map/purokLevels';
import { HAZARD_TYPES, SEVERITY, severityInfo, hazardKey, hazardIconPath, hazardColor } from '../components/Map/hazardInfo';
import { hazardsApi } from '../api/hazardsApi';
import { barangaysApi } from '../api/barangaysApi';
import { historyApi } from '../api/historyApi';
import {
  FIRE_MODEL_LABEL, FIRE_ONLY_NOTE, FORECAST_DISCLAIMER, PUROK_CAVEAT, SEVERITY_WORD, chanceText, defaultPeriod,
  hazardsParam, levelLabel, likelihoodInfo, likelyKey, periodIn, periodLabel, periodParams, periodYearsText,
  purokLikelyLevels, purokLikelyTip, unavailableNote,
} from '../components/Forecast/forecastLevels';
import ForecastPeriodPicker from '../components/Forecast/ForecastPeriodPicker';
import { hazardAreas, hazardAt, hazardPuroks, markerSpots } from '../components/Map/hazardPins';
import ReportedFiresLayer from '../components/Map/ReportedFiresLayer';
import { useAuth } from '../context/AuthContext';
import './css/PublicMap.css';
import './css/PublicMapGis.css';
import './css/PublicMapLayers.css';

// Talisay City, Cebu
const TALISAY_CENTER = [10.2446, 123.8473];
const PANEL_WIDTH = 400; // keep in sync with .pm-panel width in PublicMap.css
const MOBILE_BREAKPOINT = 860; // keep in sync with the @media rule in PublicMap.css
const MAP_REFRESH_MS = 30000; // how often an open map checks for new or changed zones

// Base maps (no API key needed).
//   Map     quiet light gray map with place names drawn above the hazard colors
//   Streets OpenStreetMap, for street-level detail
const ESRI_ATTRIBUTION = 'Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors';
const BASEMAPS = {
  map: {
    label: 'Map',
    base: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    labels: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
    attribution: ESRI_ATTRIBUTION,
    nativeZoom: 16,
    layerOpacity: 0.7,
  },
  streets: {
    label: 'Streets',
    base: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    labels: null,
    attribution: '&copy; OpenStreetMap contributors',
    nativeZoom: 19,
    layerOpacity: 0.6,
  },
};

// Size limits for a drawn zone's core (a kitchen fire up to a river overflow)
const MIN_RADIUS = 10;
const MAX_RADIUS = 1000;
const SAMPLE_ZOOM_RADIUS = 500; // meters shown around a pin when it is selected
const SEVERITY_RANK = { Red: 0, Orange: 1, Green: 2 };
// Failed background tiles, with none loaded, before the tile server counts as down
const TILE_FAIL_LIMIT = 6;

// What the map is coloured by. Active hazards are pins in both views,
// coloured by their alert level, with no shading of their own.
// Past hazards: each purok by how often it was hit in the history period
// (components/Map/purokLevels.js).
const VIEWS = [
  { key: 'past', label: 'Past hazards', note: null },
  // Fire's level per purok for a chosen month, from the fire risk model (the
  // only hazard with one since 2026-11-22; flood and landslide are being
  // rebuilt), each barangay's chance on hover; a model that cannot run is
  // unavailable, never counted.
  { key: 'likely', label: 'Likely by month', note: FORECAST_DISCLAIMER },
];

// The 'likely' view fills puroks by fire level only
const FIRE_TYPES = ['Fire'];

/* ---------- Helpers ---------- */

const isDesktop = () => window.innerWidth > MOBILE_BREAKPOINT;

// rest_framework_gis puts the primary key on feature.id, not in properties
const featureId = (feature) => feature?.id ?? feature?.properties?.id;

// Turns one GeoJSON feature from /api/hazards/ into the shape this page uses
function featureToItem(feature) {
  const p = feature.properties || {};
  let center;
  let radius;
  try {
    const bounds = L.geoJSON(feature).getBounds();
    center = bounds.getCenter();
    radius = coreRadius(bounds);
  } catch {
    return null; // skip hazards without a valid shape
  }
  return {
    id: featureId(feature),
    barangayId: p.barangay ?? null,
    location: p.barangay_name || p.location_name || `${p.hazard_type_name || 'Hazard'} zone`,
    type: p.hazard_type_name || 'Hazard',
    severity: p.severity,
    status: p.status,
    description: p.description,
    activatedAt: p.activated_at,
    // When it started by its reports; null for a zone drawn with no report
    startedAt: p.started_at || null,
    // Extreme alerts: approved by a second officer, or sent on its own
    approvedByName: p.approved_by_name,
    // 'Red' while a raise to Extreme waits for a second officer
    pendingSeverity: p.pending_severity || '',
    // A fire made from reports: one pin per purok, shown instead of the
    // zone's shading and outline (see components/Map/hazardPins.js)
    pins: p.pins || [],
    autoReleased: !!p.auto_released,
    position: [center.lat, center.lng],
    radius,
    feature,
  };
}

// Core radius from the size of the drawn zone: half its shorter side
function coreRadius(bounds) {
  const c = bounds.getCenter();
  const width = L.latLng(c.lat, bounds.getWest()).distanceTo(L.latLng(c.lat, bounds.getEast()));
  const height = L.latLng(bounds.getSouth(), c.lng).distanceTo(L.latLng(bounds.getNorth(), c.lng));
  return Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, Math.min(width, height) / 2));
}

// Turns one GeoJSON feature from /api/barangays/ into the shape this page uses
function featureToBarangay(feature) {
  const p = feature.properties || {};
  return {
    id: featureId(feature),
    name: p.name || 'Barangay',
    municipality: p.municipality,
    feature,
  };
}

// Is a [lat, lng] point inside a barangay's boundary?
function pointInRing(lat, lng, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function containsPoint(feature, position) {
  const g = feature?.geometry;
  if (!g || !position) return false;
  const [lat, lng] = position;
  const polygons = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
  return polygons.some(
    (rings) => pointInRing(lat, lng, rings[0]) && !rings.slice(1).some((hole) => pointInRing(lat, lng, hole)),
  );
}

// A hazard belongs to the barangay its pin is in. Falls back to the saved
// barangay when boundaries aren't loaded.
function isInBarangay(hazard, barangay) {
  if (barangay.feature?.geometry && hazard.position) return containsPoint(barangay.feature, hazard.position);
  if (hazard.barangayId != null) return String(hazard.barangayId) === String(barangay.id);
  return hazard.location === barangay.name;
}

// Teardrop pin colored by severity (red / orange / green). The hazard icon
// keeps its own natural color (flood blue, fire orange, landslide brown)
// on a white disc.

function pinIcon(item, selected, overlapping) {
  const sev = severityInfo(item.severity);
  return L.divIcon({
    className: 'pm-drop-wrap',
    html: `<span class="pm-drop${selected ? ' is-selected' : ''}${overlapping ? ' has-overlap' : ''}">
             <svg viewBox="0 0 44 56" aria-hidden="true">
               <path class="pm-drop-body" style="fill:${sev.color}" d="M22 54s-17-19.6-17-32a17 17 0 0 1 34 0c0 12.4-17 32-17 32z"/>
               <circle cx="22" cy="22" r="12.5" fill="#fff"/>
               <path d="${hazardIconPath(item.type)}" transform="translate(13 13) scale(0.75)" fill="${hazardColor(item.type)}"/>
             </svg>
           </span>`,
    iconSize: [44, 56],
    iconAnchor: [22, 54],
  });
}

// Clicking empty map closes the panel
function MapClickHandler({ onMapClick }) {
  useMapEvents({ click: (e) => onMapClick(e.latlng) });
  return null;
}

// The phone layout's width, the same as the @media rules in PublicMap.css
const PHONE_QUERY = '(max-width: 860px)';

function isPhone() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia(PHONE_QUERY).matches;
}

function NorthArrow() {
  return (
    <div className="pm-north" aria-label="North is up" role="img">
      <svg viewBox="0 0 24 34" aria-hidden="true">
        <path d="M12 2 4 26l8-5 8 5z" />
        <path d="M12 2v19l8 5z" className="pm-north-shade" />
      </svg>
      <span>N</span>
    </div>
  );
}

/* ---------- Page ---------- */

export default function PublicMap() {
  const [map, setMap] = useState(null);
  // Staff (BFP, DRRMO, Admin) also see the fire reports DRRMO hasn't decided
  // yet (ReportedFiresLayer); residents only ever see approved hazards
  const { canCloseFires } = useAuth();
  const [reportedCount, setReportedCount] = useState(0);
  const [reportNote, setReportNote] = useState('');
  const [liveHazards, setLiveHazards] = useState([]);
  const [barangayGeo, setBarangayGeo] = useState(null);
  const [purokGeo, setPurokGeo] = useState(null);
  // Per purok: past hazards by type, { thresholds, levels } or { error: true }
  const [purokLevels, setPurokLevels] = useState(null);
  const [view, setView] = useState('past'); // 'past' | 'likely'
  // Seasonal likelihood for the 'likely' view: which month, and the answer
  // The time the likelihood is for: a month, a month in a year, or a date
  const [likelyPeriod, setLikelyPeriod] = useState(defaultPeriod);
  const [likely, setLikely] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  // F6: several hazard layers can be visible at once, so this is a set of
  // type names rather than the old single-select filter.
  const [activeTypes, setActiveTypes] = useState(() => new Set(HAZARD_TYPES));
  const [layerTypes, setLayerTypes] = useState([]);   // from /api/hazards/layers/
  const [layersFailed, setLayersFailed] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  // Open on a computer; folded on a phone, where the open legend covers half the map
  const [legendOpen, setLegendOpen] = useState(() => !isPhone());
  // The chips wrap onto as many rows as they need. On a phone the status pills
  // and the north arrow sit just below them (--pm-chips-bottom); on a computer
  // the search and chips stop short of the status pills (--pm-status-room), so
  // a long row, as in the Likely view, never runs under them.
  const chipsRef = useRef(null);
  const statusRef = useRef(null);
  const [overlay, setOverlay] = useState(null);
  useEffect(() => {
    const chips = chipsRef.current;
    const status = statusRef.current;
    if (!chips || !status || typeof ResizeObserver === 'undefined') return undefined;
    const measure = () => {
      const topbar = chips.offsetParent;
      setOverlay({
        chipsBottom: topbar ? topbar.offsetTop + chips.offsetTop + chips.offsetHeight : null,
        statusRoom: status.offsetWidth ? status.offsetWidth + 12 : 0,
      });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(chips);
    observer.observe(status);
    measure();
    return () => observer.disconnect();
  }, []);
  const [query, setQuery] = useState('');
  const [selection, setSelection] = useState(null); // { kind: 'hazard' | 'barangay', id }
  // Ids of the hazards at the spot last clicked, most serious first. Kept fixed
  // while the user steps through them, so the list doesn't reshuffle around
  // whichever neighbor is showing.
  const [stackIds, setStackIds] = useState([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [basemap, setBasemap] = useState('streets');
  // Map background health. Tiles that fail with none loading mean the tile
  // server is unreachable: switch once to the other provider, and if that
  // fails too, say so instead of leaving a blank grey map.
  const [tileFailures, setTileFailures] = useState({ count: 0, loaded: false });
  const [failedBasemaps, setFailedBasemaps] = useState(() => new Set());
  const [tileSwitchNote, setTileSwitchNote] = useState('');
  useEffect(() => { setTileFailures({ count: 0, loaded: false }); }, [basemap]);
  useEffect(() => {
    // Came back: this background works again
    if (tileFailures.loaded) {
      if (failedBasemaps.has(basemap)) {
        const next = new Set(failedBasemaps);
        next.delete(basemap);
        setFailedBasemaps(next);
      }
      return;
    }
    if (tileFailures.count < TILE_FAIL_LIMIT || failedBasemaps.has(basemap)) return;
    const next = new Set(failedBasemaps);
    next.add(basemap);
    setFailedBasemaps(next);
    const other = Object.keys(BASEMAPS).find((k) => !next.has(k));
    if (other) {
      setTileSwitchNote(`The ${BASEMAPS[basemap].label.toLowerCase()} background did not load, so the ${BASEMAPS[other].label.toLowerCase()} background is shown instead.`);
      setBasemap(other);
    }
  }, [tileFailures, basemap, failedBasemaps]);
  const tilesDown = Object.keys(BASEMAPS).every((k) => failedBasemaps.has(k));
  const tileEvents = useMemo(() => ({
    tileerror: () => setTileFailures((t) => (t.loaded ? t : { ...t, count: t.count + 1 })),
    tileload: () => setTileFailures((t) => (t.loaded ? t : { count: 0, loaded: true })),
  }), []);
  const susceptibility = useSusceptibility();
  const [searchParams, setSearchParams] = useSearchParams();
  // /map?report=<id>, from the BFP dashboard's Show on map (staff only)
  const focusReportId = canCloseFires ? searchParams.get('report') : null;

  // Load hazards. Pulled out of the effect so the timed refresh and
  // resolving can re-run it.
  const hazardsTag = useRef(null);
  const loadHazards = useCallback((background = false) => {
    return hazardsApi
      .listTagged()
      .then(({ data, etag }) => {
        // Same version as last time: nothing changed, keep the map as it is
        if (background && etag && etag === hazardsTag.current) return;
        hazardsTag.current = etag;
        const features = data?.features || data?.results?.features || [];
        const items = features
          .filter((f) => !f.properties?.status || f.properties.status === 'Active')
          .map(featureToItem)
          .filter(Boolean);
        setLiveHazards(items);
        setLoadFailed(false);
      })
      .catch(() => {
        // A failed refresh keeps the zones already shown
        if (!background) setLoadFailed(true);
      });
  }, []);

  // Each purok's past hazards, for the Past hazards colours. Reloaded after
  // a resolve, since that writes a new historical record, and with the
  // hazards below; a failed reload keeps the colours already shown. An
  // unchanged answer keeps the same state, so an open purok tooltip stays.
  const purokLevelsTag = useRef(null);
  const loadPurokLevels = useCallback(() => {
    return historyApi
      .purokLevels()
      .then((data) => {
        const tag = JSON.stringify(data);
        if (tag === purokLevelsTag.current) return;
        purokLevelsTag.current = tag;
        setPurokLevels({ thresholds: data.thresholds, levels: byPurok(data.results) });
      })
      .catch(() => setPurokLevels((prev) => (prev && !prev.error ? prev : { error: true })));
  }, []);

  // A map left open (a phone on the barangay hall desk) used to show the
  // zones from when it was opened, forever. Refresh while the tab is
  // visible; the server answers 304 when nothing changed, so this is cheap.
  // The purok colours come along: a fire closed from the DRRMO dashboard
  // recolours its puroks here without a reload.
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== 'visible') return;
      loadHazards(true);
      loadPurokLevels();
    };
    const id = setInterval(refresh, MAP_REFRESH_MS);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [loadHazards, loadPurokLevels]);

  // Load hazards, barangay and purok outlines once
  useEffect(() => {
    loadHazards().finally(() => setLoading(false));
    barangaysApi.list().then(setBarangayGeo).catch(() => {});
    barangaysApi.puroks().then(setPurokGeo).catch(() => {});
    loadPurokLevels();
  }, [loadHazards, loadPurokLevels]);

  // Per-type counts and the severity legend for the layer panel.
  const loadLayers = useCallback(() => {
    hazardsApi
      .layers()
      .then((data) => {
        setLayerTypes(Array.isArray(data?.Layers) ? data.Layers : []);
        setLayersFailed(false);
      })
      .catch(() => {
        setLayerTypes([]);
        setLayersFailed(true);
      });
  }, []);

  useEffect(() => { loadLayers(); }, [loadLayers]);

  // Resolving changes more of the map than the thing the user was looking
  // at: the pins, the per-type counts in the Layers panel, the purok colours
  // and the past-incident lists, so it refreshes all of them here.
  const refreshMap = useCallback(() => {
    clearHistoryCache();
    loadLayers();
    return Promise.all([loadHazards(), loadPurokLevels()]);
  }, [loadHazards, loadPurokLevels, loadLayers]);

  // Close the panel with the Escape key
  useEffect(() => {
    function onKey(e) {
      if (e.key !== 'Escape') return;
      setPanelOpen(false);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const rawHazards = liveHazards;

  const barangays = useMemo(
    () => (barangayGeo?.features || []).map(featureToBarangay),
    [barangayGeo],
  );

  // Name each hazard after the barangay its pin actually sits in
  const hazards = useMemo(
    () =>
      rawHazards.map((h) => {
        const home = barangays.find((b) => containsPoint(b.feature, h.position));
        return home && home.name !== h.location ? { ...h, location: home.name, barangayId: home.id } : h;
      }),
    [rawHazards, barangays],
  );

  const visibleHazards = useMemo(
    () => hazards.filter((h) => activeTypes.has(hazardKey(h.type))),
    [hazards, activeTypes],
  );

  // Whether the purok outlines inside each barangay are drawn. On unless
  // turned off in this browser.
  const [showPuroks, setShowPuroks] = useState(() => {
    try {
      return localStorage.getItem('geoalert-purok-outlines') !== 'off';
    } catch {
      return true;
    }
  });
  const togglePuroks = useCallback(() => {
    setShowPuroks((on) => {
      try {
        localStorage.setItem('geoalert-purok-outlines', on ? 'off' : 'on');
      } catch {
        // storage blocked: the choice lasts until the page is closed
      }
      return !on;
    });
  }, []);

  // F6: zones of different severities can overlap. Pins whose areas touch are
  // marked on the map and listed in each other's detail panel, so a reader
  // isn't shown one severity while standing in two.
  const overlaps = useMemo(() => {
    const found = new Map();
    const link = (a, b) => {
      if (!found.has(a.id)) found.set(a.id, []);
      found.get(a.id).push(b);
    };
    for (let i = 0; i < hazards.length; i += 1) {
      for (let j = i + 1; j < hazards.length; j += 1) {
        const a = hazards[i];
        const b = hazards[j];
        if (!a.position || !b.position) continue;
        const gap = L.latLng(a.position).distanceTo(L.latLng(b.position));
        if (gap < (a.radius || 0) + (b.radius || 0)) { link(a, b); link(b, a); }
      }
    }
    return found;
  }, [hazards]);

  const searchResults = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const barangayMatches = barangays
      .filter((b) => b.name.toLowerCase().includes(q))
      .slice(0, 5)
      .map((b) => ({ kind: 'barangay', key: `b-${b.id}`, item: b }));
    const hazardMatches = hazards
      .filter((h) => `${h.location} ${h.type}`.toLowerCase().includes(q))
      .map((h) => ({ kind: 'hazard', key: `h-${h.id}`, item: h }));
    return [...barangayMatches, ...hazardMatches];
  }, [barangays, hazards, query]);

  const selectedHazardId = selection?.kind === 'hazard' ? selection.id : null;
  const selectedBarangayId = selection?.kind === 'barangay' ? selection.id : null;
  // Purok lines show only inside the barangay whose panel is open
  const selectedPuroks = useMemo(
    () => (showPuroks && panelOpen ? puroksOf(purokGeo, selectedBarangayId) : null),
    [showPuroks, panelOpen, purokGeo, selectedBarangayId],
  );

  const selectedHazard = hazards.find((h) => h.id === selectedHazardId) || null;
  // The puroks of the hazard whose panel is open, outlined on the map
  const selectedHazardPuroks = useMemo(
    () => (panelOpen && selectedHazard ? hazardPuroks(selectedHazard, purokGeo) : null),
    [panelOpen, selectedHazard, purokGeo],
  );
  // Every shown hazard's puroks, outlined lightly from the start so the
  // affected area is visible before anything is tapped; a tap inside one
  // opens its hazard
  const areas = useMemo(() => hazardAreas(visibleHazards, purokGeo), [visibleHazards, purokGeo]);
  const stack = useMemo(
    () => stackIds.map((id) => hazards.find((h) => h.id === id)).filter(Boolean),
    [stackIds, hazards],
  );
  const selectedBarangay =
    selectedBarangayId == null ? null : barangays.find((b) => String(b.id) === String(selectedBarangayId)) || null;

  // The barangay panel lists every hazard in the barangay, ignoring the type chips
  const barangayHazards = useMemo(
    () => (selectedBarangay ? hazards.filter((h) => isInBarangay(h, selectedBarangay)) : []),
    [hazards, selectedBarangay],
  );

  // Zoom the map to fit all pins once, after they first load
  const hasFitted = useRef(false);
  useEffect(() => {
    // A report link zooms to that report instead (onReportFocused)
    if (!map || loading || hasFitted.current || focusReportId || hazards.length === 0) return;
    hasFitted.current = true;
    const bounds = L.latLngBounds(hazards.map((h) => h.position));
    map.fitBounds(bounds, { padding: [120, 120], maxZoom: 15 });
  }, [map, loading, hazards, focusReportId]);

  // Open a hazard straight from a link, e.g. tapping a notification, which
  // points at /map?zone=<id>. Strips the parameter once used, so a later
  // refresh doesn't reopen a panel the user has closed, while another link
  // followed on this page (the alert bell in the navbar) still opens its zone.
  useEffect(() => {
    if (loading) return;
    const zoneId = searchParams.get('zone');
    if (!zoneId) return;

    const target = hazards.find((h) => String(h.id) === String(zoneId));
    if (!target) return;

    hasFitted.current = true;   // don't fit all pins, then fly away from them
    selectHazard(target);
    searchParams.delete('zone');
    setSearchParams(searchParams, { replace: true });
  }, [loading, hazards, searchParams, setSearchParams]);   // eslint-disable-line react-hooks/exhaustive-deps

  // The report link has been followed: the layer zoomed to it, or it is no
  // longer waiting. Strip the parameter, as for ?zone, and don't fit all pins.
  const onReportFocused = useCallback((found) => {
    hasFitted.current = true;
    if (!found) setReportNote('That fire report is no longer waiting for DRRMO. It may have been approved or rejected.');
    searchParams.delete('report');
    setSearchParams(searchParams, { replace: true });
  }, [searchParams, setSearchParams]);

  // Paddings that keep a zoomed area clear of the details panel and search bar
  function panelPadding() {
    return isDesktop()
      ? { paddingTopLeft: [PANEL_WIDTH + 32, 96], paddingBottomRight: [32, 32] }
      : { paddingTopLeft: [24, 140], paddingBottomRight: [24, map.getSize().y * 0.62] };
  }

  function toggleType(name) {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  }

  function selectHazard(item) {
    setStackIds(
      [item, ...(overlaps.get(item.id) || [])]
        .sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])
        .map((h) => h.id),
    );
    setSelection({ kind: 'hazard', id: item.id });
    setPanelOpen(true);
    setQuery('');
    if (!map) return;

    // Zoom to its puroks, or the area around the pin, beside the panel
    const puroks = hazardPuroks(item, purokGeo);
    let bounds = L.latLng(item.position).toBounds(SAMPLE_ZOOM_RADIUS * 2);
    try { if (puroks) bounds = L.geoJSON(puroks).getBounds(); } catch { /* the pin's area */ }
    map.flyToBounds(bounds, { ...panelPadding(), maxZoom: 17, duration: 0.8 });
  }

  // Step to another hazard at the same spot. The map stays put unless that
  // pin is hidden behind the panel.
  function showStacked(item) {
    setSelection({ kind: 'hazard', id: item.id });
    if (map && item.position) map.panInside(item.position, panelPadding());
  }

  // spot: [lat, lng] when the barangay was tapped on the map, for the panel's
  // "This spot" reading; null when it was picked from search.
  // purokId: the purok whose past hazards the panel shows; null for the
  // whole barangay, which is where every new barangay starts.
  function selectBarangay(barangay, spot = null, purokId = null) {
    const alreadyOpen = panelOpen && selection?.kind === 'barangay' && String(selection.id) === String(barangay.id);
    setSelection({ kind: 'barangay', id: barangay.id, spot, purokId });
    setPanelOpen(true);
    setQuery('');
    // Tapping around inside the open barangay only moves the spot; fitting
    // the barangay again on every tap would keep pulling the map away.
    if (alreadyOpen && spot) return;
    if (!map || !barangay.feature?.geometry) return;

    const bounds = L.geoJSON(barangay.feature).getBounds();
    if (!bounds.isValid()) return;

    // Fit the barangay into the part of the map the panel doesn't cover
    map.flyToBounds(bounds, { ...panelPadding(), maxZoom: 16, duration: 0.8 });
  }

  // From the panel's past hazards: one purok, 'none', or back to the barangay
  function pickPurok(purokId) {
    setSelection((s) => (s?.kind === 'barangay' ? { ...s, purokId } : s));
  }

  function selectResult(result) {
    if (result.kind === 'barangay') selectBarangay(result.item);
    else selectHazard(result.item);
  }

  function handleSearchKey(e) {
    if (e.key === 'Enter' && searchResults.length > 0) selectResult(searchResults[0]);
  }

  // A zone that is no longer Active — resolved, or withdrawn as published in
  // error — comes off the map. Both endpoints answer with the plain
  // serializer rather than GeoJSON, so featureToItem can't be reused here;
  // match on the id instead.
  function dropHazard(zone) {
    const goneId = zone?.id ?? selectedHazardId;
    // Drop the pin straight away rather than waiting on the round trip, so
    // the map doesn't keep showing a hazard the officer has just closed.
    setLiveHazards((prev) => prev.filter((h) => String(h.id) !== String(goneId)));

    // The shading, the per-type counts and the past-incident lists all have
    // to catch up: resolving adds a historical record, withdrawing changes
    // the active counts.
    refreshMap();

    // Move on to the next hazard at the same spot, if there is one
    const next = stack.find((h) => String(h.id) !== String(goneId));
    if (next) {
      setStackIds((ids) => ids.filter((id) => String(id) !== String(goneId)));
      setSelection({ kind: 'hazard', id: next.id });
      return;
    }
    setSelection(null);
    setPanelOpen(false);
  }

  const handleResolved = dropHazard;
  const handleRetracted = dropHazard;

  // A tap on empty map closes whichever details panel is open
  function handleMapClick() {
    setPanelOpen(false);
  }

  // Fire is the only hazard with a prediction model since 2026-11-22: the
  // view asks for fire while its layer is ticked, and for nothing otherwise
  const likelyHazards = hazardsParam(activeTypes);

  // Seasonal likelihood, fetched only while that view is open
  useEffect(() => {
    if (view !== 'likely') return undefined;
    // Fire not ticked, nothing to ask for: the legend says only fire has a prediction
    if (!likelyHazards) { setLikely(null); return undefined; }
    let cancelled = false;
    historyApi.forecast({ ...periodParams(likelyPeriod), hazards: likelyHazards })
      .then((d) => { if (!cancelled) setLikely(d); })
      .catch(() => { if (!cancelled) setLikely({ error: true, results: [] }); });
    return () => { cancelled = true; };
  }, [view, likelyPeriod, likelyHazards]);

  // Per barangay: its fire row
  const fireRows = useMemo(() => new Map((likely?.results || [])
    .filter((r) => r.hazard_type === 'Fire')
    .map((r) => [String(r.barangay_id), r])), [likely]);
  // Per purok: the fire model's level and chance, in the shape the fill layer reads
  const likelyLevels = useMemo(() => purokLikelyLevels(likely), [likely]);
  // When the purok chances are for: "in June", "in June 2027", "in the week of Jun 15"
  const likelySpan = likelyPeriod.mode === 'date' ? `in ${periodIn(likelyPeriod)}` : `in ${periodLabel(likelyPeriod)}`;
  // For the barangay panel's purok list: every purok's name, and the open barangay's purok rows
  const purokNames = useMemo(
    () => new Map((purokGeo?.features || []).map((f) => [String(featureId(f)), f.properties?.name])),
    [purokGeo],
  );
  const likelyPuroks = useMemo(
    () => (likely?.purok_results || []).filter((r) => String(r.barangay_id) === String(selectedBarangayId)),
    [likely, selectedBarangayId],
  );

  // Thin dark boundaries, like sub-catchment lines on a GIS map. Transparent fill keeps them clickable.
  // In the likely view too: the puroks carry the fire levels, a barangay's chance is on hover.
  function barangayStyle(feature) {
    // Bold only while its panel is open
    const selected =
      panelOpen && selectedBarangayId != null && String(featureId(feature)) === String(selectedBarangayId);
    return selected
      ? { className: 'pm-brgy', color: '#111111', weight: 2.6, opacity: 1, fillColor: '#1c2e4a', fillOpacity: 0.07 }
      : { className: 'pm-brgy', color: '#2b2b2b', weight: 1, opacity: 0.8, fillOpacity: 0 };
  }

  const visibleTypeList = useMemo(() => [...activeTypes], [activeTypes]);
  const viewNote = VIEWS.find((m) => m.key === view).note;
  const levels = purokLevels?.levels || null;
  const thresholds = purokLevels?.thresholds || null;
  // What hovering a purok says: its name, in Past hazards its counts, in
  // Likely by month its fire level and chance. Stable between renders, since
  // the hover listeners are rebuilt when it changes.
  const purokTip = useCallback((f) => {
    const id = String(f.id ?? f.properties?.id);
    let line = '';
    if (view === 'past' && levels) line = historyLine(levels.get(id), visibleTypeList, thresholds.years);
    if (view === 'likely') {
      const row = likelyLevels.get(id)?.Fire;
      if (row) line = purokLikelyTip(row, 'Fire', likelySpan);
    }
    return line ? `${purokTooltip(f)}<br>${line}` : purokTooltip(f);
  }, [view, levels, thresholds, visibleTypeList, likelyLevels, likelySpan]);
  // Fire with no figures, named in the legend with its reason instead of dropped silently
  const unavailableLegend = unavailableNote(likely);

  // What the checkbox panel lists: the API's counts when available, otherwise
  // counts worked out from the pins already on the map.
  const layerRows = layerTypes.length
    ? layerTypes
    : HAZARD_TYPES.map((name) => ({
        name,
        active_count: hazards.filter((h) => hazardKey(h.type) === name).length,
        severity_counts: ['Red', 'Orange', 'Green'].reduce((acc, sev) => {
          acc[sev] = hazards.filter((h) => hazardKey(h.type) === name && h.severity === sev).length;
          return acc;
        }, {}),
      }));

  return (
    <div className="pm">
      <PublicNavbar />

      <div
        className="pm-stage"
        style={overlay ? {
          ...(overlay.chipsBottom ? { '--pm-chips-bottom': `${overlay.chipsBottom}px` } : {}),
          '--pm-status-room': `${overlay.statusRoom}px`,
        } : undefined}
      >
        {/* ============ MAP ============ */}
        <MapContainer
          ref={setMap}
          className="pm-map"
          center={TALISAY_CENTER}
          zoom={14}
          zoomControl={false}
        >
          {BASEMAPS[basemap].base && (
            <TileLayer
              key={`base-${basemap}`}
              url={BASEMAPS[basemap].base}
              attribution={BASEMAPS[basemap].attribution}
              maxNativeZoom={BASEMAPS[basemap].nativeZoom}
              maxZoom={20}
              eventHandlers={tileEvents}
            />
          )}
          <ZoomControl position="bottomright" />
          <ScaleControl position="bottomright" imperial={false} />
          <MapClickHandler onMapClick={handleMapClick} />

          {/* Past hazards: each purok in its level's colour, citywide */}
          {view === 'past' && levels && (
            <PurokHistoryLayer
              geo={purokGeo}
              levels={levels}
              types={visibleTypeList}
              tooltipFor={purokTip}
              skipBarangay={selectedPuroks ? selectedBarangayId : null}
            />
          )}

          {/* Likely by month: each purok in its fire level's colour, from the fire risk model */}
          {view === 'likely' && likelyLevels.size > 0 && (
            <PurokHistoryLayer
              geo={purokGeo}
              levels={likelyLevels}
              types={FIRE_TYPES}
              tooltipFor={purokTip}
              skipBarangay={selectedPuroks ? selectedBarangayId : null}
            />
          )}

          {/* Purok outlines of the selected barangay, under the barangay lines;
              hovering one names it, and the one the panel shows is bold */}
          <PurokLayer
            geo={selectedPuroks}
            selectedId={selection?.kind === 'barangay' ? selection.purokId ?? null : null}
            tooltipFor={purokTip}
          />

          {/* Every active hazard's puroks, faint; the one the panel shows bold
              and lightly filled. Over the past-hazard fills, under the
              barangay lines, so a tap reaches the barangay layer, which
              hands taps inside these to their hazard. */}
          {(areas || selectedHazardPuroks) && (
            <Pane name="hazard-puroks" style={{ zIndex: 380, pointerEvents: 'none' }}>
              {areas && (
                <GeoJSON
                  key={`hazard-areas-${areas.features.map((f) => `${f.id}:${f.properties.hazards.map((h) => h.id).join('+')}`).join(',')}`}
                  data={areas}
                  style={(f) => ({ ...purokStyle(f), ...PUROK_HAZARD_AREA })}
                  interactive={false}
                />
              )}
              {selectedHazardPuroks && (
                <GeoJSON
                  key={`hazard-puroks-${selectedHazardId}-${selectedHazardPuroks.features.map((f) => f.id).join(',')}`}
                  data={selectedHazardPuroks}
                  style={(f) => ({ ...purokStyle(f), ...PUROK_OF_HAZARD })}
                  interactive={false}
                />
              )}
            </Pane>
          )}

          {/* Street and place names above the hazard layer */}
          {BASEMAPS[basemap].labels && (
            <Pane name="basemap-labels" style={{ zIndex: 450, pointerEvents: 'none' }}>
              <TileLayer
                key={`labels-${basemap}`}
                url={BASEMAPS[basemap].labels}
                maxNativeZoom={BASEMAPS[basemap].nativeZoom}
                maxZoom={20}
              />
            </Pane>
          )}

          {/* Barangay boundaries: hover for the name, click for barangay-specific hazards */}
          {barangayGeo && (
            <GeoJSON
              key={`brgy-${selectedBarangayId ?? 'none'}-${panelOpen}-${view}-${periodLabel(likelyPeriod)}-${likelyKey(likely)}-${[...activeTypes].join('')}-${!!selectedPuroks}`}
              data={barangayGeo}
              style={barangayStyle}
              bubblingMouseEvents={false}
              onEachFeature={(feature, layer) => {
                // Inside the selected barangay its puroks name themselves on hover
                if (selectedPuroks && String(featureId(feature)) === String(selectedBarangayId)) return;
                const name = feature.properties?.name || 'Barangay';
                let tip = name;
                if (view === 'likely') {
                  const r = fireRows.get(String(featureId(feature)));
                  // A past period also says what happened in it
                  const happened = r && r.actual != null ? `; ${r.actual || 'none'} happened` : '';
                  let line = '';
                  if (r?.method === 'unavailable') line = `Fire: ${levelLabel(r)}${r.reason ? ` (${r.reason})` : ''}`;
                  else if (r?.method === 'model') line = `Fire: ${likelihoodInfo(r.level).label}, about ${chanceText(r)}${happened}`;
                  else if (r) line = `Fire: ${likelihoodInfo(r.level).label} (${periodYearsText(r, likelyPeriod)}${happened})`;
                  tip = !likelyHazards
                    ? `<strong>${name}</strong><br>${FIRE_ONLY_NOTE} Tick the Fire layer to see its chance.`
                    : line
                    ? `<strong>${name}</strong><br>${line}`
                    : `<strong>${name}</strong><br>Nothing on record in ${periodIn(likelyPeriod)} in past years`;
                }
                layer.bindTooltip(tip, {
                  sticky: true,
                  direction: 'top',
                  className: 'pm-brgy-tip',
                });
              }}
              eventHandlers={{
                click: (e) => {
                  const f = e.propagatedFrom?.feature || e.layer?.feature;
                  if (!f) return;
                  // The first tap opens the barangay; a tap inside it after
                  // that picks the purok there, or the whole barangay again
                  // where no purok is drawn
                  const barangay = featureToBarangay(f);
                  const open = panelOpen && selection?.kind === 'barangay'
                    && String(selection.id) === String(barangay.id);
                  // Inside a hazard's purok: that hazard. Not while this
                  // barangay's panel is open, where a tap picks a purok.
                  const hazard = open ? null : hazardAt(areas, e.latlng.lng, e.latlng.lat);
                  if (hazard) {
                    selectHazard(hazard);
                    return;
                  }
                  const purok = open ? purokAt(puroksOf(purokGeo, barangay.id), e.latlng.lng, e.latlng.lat) : null;
                  selectBarangay(barangay, [e.latlng.lat, e.latlng.lng], purok ? featureId(purok) : null);
                },
              }}
            />
          )}


          {/* The tapped spot the barangay panel is reading. Not interactive,
              so the next tap lands on the map and moves it. */}
          {panelOpen && selection?.kind === 'barangay' && selection.spot && (
            <CircleMarker
              center={selection.spot}
              radius={6}
              interactive={false}
              pathOptions={{ color: '#1c2e4a', weight: 2, fillColor: '#ffffff', fillOpacity: 1 }}
            />
          )}

          {visibleHazards.flatMap((h) => markerSpots(h).map((spot) => (
            <Marker
              key={spot.key}
              position={spot.position}
              icon={pinIcon(h, h.id === selectedHazardId, overlaps.has(h.id))}
              title={`${spot.purok || h.location}: ${h.type}, ${severityInfo(h.severity).label}`}
              eventHandlers={{
                click: () => selectHazard(h),
              }}
            />
          )))}

          {canCloseFires && (
            <ReportedFiresLayer
              focusId={focusReportId}
              onFocused={onReportFocused}
              onCount={setReportedCount}
              refreshMs={MAP_REFRESH_MS}
            />
          )}
        </MapContainer>

        {/* ============ SEARCH + FILTERS ============ */}
        <div className="pm-topbar">
          <div className="pm-search">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>
            <label htmlFor="pm-search-input" className="pm-visually-hidden">Search barangays or hazards</label>
            <input
              id="pm-search-input"
              type="search"
              placeholder="Search a barangay or hazard"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleSearchKey}
              autoComplete="off"
            />

            {query.trim() && (
              <ul className="pm-results">
                {searchResults.length === 0 && (
                  <li className="pm-results-empty">No barangays or hazards match "{query.trim()}".</li>
                )}
                {searchResults.map((r) => {
                  if (r.kind === 'barangay') {
                    const count = hazards.filter((h) => isInBarangay(h, r.item)).length;
                    return (
                      <li key={r.key}>
                        <button type="button" onClick={() => selectBarangay(r.item)}>
                          <span className="pm-results-dot pm-results-dot-brgy" />
                          <span>
                            <strong>{r.item.name}</strong>
                            <small>
                              Barangay, {count === 0 ? 'no active hazards' : `${count} active ${count === 1 ? 'hazard' : 'hazards'}`}
                            </small>
                          </span>
                        </button>
                      </li>
                    );
                  }
                  const sev = severityInfo(r.item.severity);
                  return (
                    <li key={r.key}>
                      <button type="button" onClick={() => selectHazard(r.item)}>
                        <span className="pm-results-dot" style={{ background: sev.color }} />
                        <span>
                          <strong>{r.item.location}</strong>
                          <small>{r.item.type}, {sev.label.toLowerCase()}</small>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="pm-chips" role="group" aria-label="Map layers" ref={chipsRef}>
            <div className="pm-mode" role="group" aria-label="Shading">
              {VIEWS.map((m) => (
                <button
                  key={m.key}
                  type="button"
                  className={view === m.key ? 'is-active' : ''}
                  aria-pressed={view === m.key}
                  onClick={() => setView(m.key)}
                >
                  {m.label}
                </button>
              ))}
            </div>

            {view === 'likely' && (
              <ForecastPeriodPicker
                value={likelyPeriod}
                onChange={setLikelyPeriod}
                fieldClass="pm-chip pm-likely-month"
                labelClass="pm-sr"
              />
            )}

            <button
              type="button"
              className={`pm-chip ${layersOpen ? 'is-active' : ''}`}
              aria-expanded={layersOpen}
              onClick={() => setLayersOpen((open) => !open)}
            >
              Layers ({activeTypes.size}/{layerRows.length})
            </button>

          </div>

          {layersOpen && (
            <LayerControl
              types={layerRows}
              active={activeTypes}
              onToggle={toggleType}
              onAll={() => setActiveTypes(new Set(layerRows.map((t) => t.name)))}
              onNone={() => setActiveTypes(new Set())}
              failed={layersFailed}
              onRetry={loadLayers}
              showPuroks={showPuroks}
              onTogglePuroks={purokGeo?.features?.length ? togglePuroks : undefined}
              puroksEstimated={hasEstimates(purokGeo)}
            />
          )}
        </div>

        {/* ============ STATUS MESSAGES ============ */}
        <div className={`pm-status ${panelOpen ? 'is-hidden-mobile' : ''}`} ref={statusRef}>
          {loading && <span className="pm-pill">Loading hazards…</span>}
          {!loading && loadFailed && <span className="pm-pill pm-pill-error">Live hazard data is unavailable right now</span>}
          {tilesDown && (
            <span className="pm-pill pm-pill-error">
              Map tiles temporarily unavailable. Hazard pins and barangay lines are still shown.
            </span>
          )}
          {!tilesDown && tileSwitchNote && (
            <span className="pm-pill">
              {tileSwitchNote}{' '}
              <button type="button" className="pm-pill-close" onClick={() => setTileSwitchNote('')} aria-label="Dismiss">×</button>
            </span>
          )}
          {!loading && hazards.length === 0 && !loadFailed && (
            <span className="pm-pill">No active hazards right now</span>
          )}
          {canCloseFires && reportedCount > 0 && (
            <span className="pm-pill pm-pill-reported">
              {reportedCount} fire report{reportedCount === 1 ? '' : 's'} waiting for DRRMO
            </span>
          )}
          {canCloseFires && reportNote && (
            <span className="pm-pill">
              {reportNote}{' '}
              <button type="button" className="pm-pill-close" onClick={() => setReportNote('')} aria-label="Dismiss">×</button>
            </span>
          )}
          {susceptibility.status === 'missing' && (
            <span className="pm-pill pm-pill-error">Hazard layer data not built yet</span>
          )}
          {view === 'past' && purokLevels?.error && (
            <span className="pm-pill pm-pill-error">Past-hazard colours couldn't load.</span>
          )}
        </div>

        <NorthArrow />

        {/* ============ LEGEND ============ */}
        <div className={`pm-legend ${panelOpen ? 'is-hidden-mobile' : ''} ${legendOpen ? '' : 'is-collapsed'}`}>
          <button
            type="button"
            className="pm-legend-toggle"
            aria-expanded={legendOpen}
            onClick={() => setLegendOpen((open) => !open)}
          >
            <span>{view === 'likely' ? 'Likely fire levels' : 'Past hazard levels'}</span>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
          </button>

          {view === 'likely' && (
            <>
              <p className="pm-legend-title">
                {!likelyHazards
                  ? `Likely in ${periodLabel(likelyPeriod)}: ${FIRE_ONLY_NOTE} Tick the Fire layer.`
                  : `Likely in ${periodLabel(likelyPeriod)}: each purok's fire level`}
              </p>
              <ul>
                {['Red', 'Orange', 'Green'].map((k) => (
                  <li key={k}>
                    <span className="pm-legend-swatch" style={{ background: SEVERITY[k].color }} />
                    {SEVERITY_WORD[k]}
                  </li>
                ))}
              </ul>
              {/* The explanations fold away with the legend; the warnings stay while its colours are on the map */}
              {likely?.error && <p className="pm-legend-note">Could not load the likelihood.</p>}
              {/* Where the colours come from; a past period also says what happened */}
              {legendOpen && likely && !likely.error && likelyLevels.size > 0 && (
                <>
                  <p className="pm-legend-note">
                    {`${FIRE_MODEL_LABEL}. Hover a barangay for its overall chance.`}
                    {likely.outcome && (likely.outcome.complete
                      ? ` It is over: ${likely.outcome.events} fire${likely.outcome.events === 1 ? '' : 's'} happened.`
                      : ` It has started: ${likely.outcome.events} fire${likely.outcome.events === 1 ? '' : 's'} so far.`)}
                  </p>
                  <p className="pm-legend-note">{PUROK_CAVEAT}</p>
                </>
              )}
              {unavailableLegend && <p className="pm-legend-note">{unavailableLegend}</p>}
            </>
          )}
          {legendOpen && viewNote && <p className="pm-legend-note">{viewNote}</p>}

          {legendOpen && (
            <>
              <p className="pm-legend-title pm-legend-title-sub">Pin colour</p>
              <ul>
                {Object.entries(SEVERITY).map(([code, sev]) => (
                  <li key={code} className="pm-legend-row">
                    <span className="pm-legend-dot" style={{ background: sev.color }} />
                    <span>
                      <strong>{sev.label}</strong>
                      <small>{sev.advice}</small>
                    </span>
                  </li>
                ))}
              </ul>

              <p className="pm-legend-title pm-legend-title-sub">Hazard symbols</p>
              <ul>
                {HAZARD_TYPES.map((type) => (
                  <li key={type}>
                    <span className="pm-legend-symbol" style={{ color: hazardColor(type) }} aria-hidden="true">
                      <svg viewBox="0 0 24 24"><path d={hazardIconPath(type)} /></svg>
                    </span>
                    {type}
                  </li>
                ))}
              </ul>

              <ul>
                <li>
                  <span className="pm-legend-overlap" aria-hidden="true" />
                  Overlaps another hazard zone
                </li>
              </ul>

              {/* The elevation licence requires these credits wherever the layers
                  are shown, so they fold away here rather than go */}
              {susceptibility.index?.sources?.length > 0 && (
                <details className="pm-legend-credits">
                  <summary>Data credits</summary>
                  {susceptibility.index.sources.map((source) => (
                    <p key={source} className="pm-legend-note pm-legend-source">{source}</p>
                  ))}
                </details>
              )}
            </>
          )}
        </div>

        {/* ============ BASE MAP TOGGLE ============ */}
        <div className={`pm-basemap ${panelOpen ? 'is-hidden-mobile' : ''}`} role="group" aria-label="Map style">
          {Object.entries(BASEMAPS).map(([key, b]) => (
            <button
              key={key}
              type="button"
              className={basemap === key ? 'is-active' : ''}
              aria-pressed={basemap === key}
              onClick={() => setBasemap(key)}
            >
              {b.label}
            </button>
          ))}
        </div>

        {/* ============ DETAILS PANELS ============ */}
        <HazardPanel
          item={selectedHazard}
          open={panelOpen && !!selectedHazard}
          onClose={() => setPanelOpen(false)}
          onResolved={handleResolved}
          onRetracted={handleRetracted}
          stack={stack}
          onPick={showStacked}
        />
        <BarangayPanel
          barangay={selectedBarangay}
          hazards={barangayHazards}
          allHazards={hazards}
          open={panelOpen && !!selectedBarangay}
          onClose={() => setPanelOpen(false)}
          onSelectHazard={selectHazard}
          spot={selection?.kind === 'barangay' ? selection.spot ?? null : null}
          susceptibilityIndex={susceptibility.index}
          rivers={susceptibility.rivers}
          purokId={selection?.kind === 'barangay' ? selection.purokId ?? null : null}
          onPickPurok={pickPurok}
          historyTypes={visibleTypeList}
          view={view}
          likelyPuroks={likelyPuroks}
          purokNames={purokNames}
          likelyLabel={periodLabel(likelyPeriod)}
          likelyUnavailable={!likelyHazards
            ? `${FIRE_ONLY_NOTE} Tick the Fire layer.`
            : unavailableLegend || (likely?.error ? 'Could not load the likelihood.' : '')}
        />
      </div>
    </div>
  );
}