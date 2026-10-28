import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, Polygon, Polyline, ZoomControl, ScaleControl, Pane, CircleMarker, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import PublishHazardPanel from '../components/Publish/PublishHazardPanel';
import LayerControl from '../components/Map/LayerControl';
import HazardPanel, { clearHistoryCache } from '../components/Map/HazardPanel';
import BarangayPanel from '../components/Map/BarangayPanel';
import { useSusceptibility } from '../components/Map/susceptibility';
import PurokLayer from '../components/Map/PurokLayer';
import PurokHistoryLayer from '../components/Map/PurokHistoryLayer';
import { PUROK_OF_HAZARD, hasEstimates, purokAt, purokStyle, purokTooltip, puroksOf } from '../components/Map/purokStyle';
import { PUROK_LEVELS, byPurok, historyLine, thresholdText } from '../components/Map/purokLevels';
import { HAZARD_TYPES, SEVERITY, severityInfo, hazardKey, hazardIconPath, hazardColor } from '../components/Map/hazardInfo';
import { MIN_CORNERS, middleOf } from '../utils/drawnZone';
import { boundaryRings, snapPoint } from '../utils/snap';
import { hazardsApi } from '../api/hazardsApi';
import { barangaysApi } from '../api/barangaysApi';
import { historyApi } from '../api/historyApi';
import {
  LIKELIHOOD, FORECAST_DISCLAIMER, defaultPeriod, likelihoodInfo, periodIn, periodLabel, periodParams, periodYearsText,
  yearSpan,
} from '../components/Forecast/forecastLevels';
import ForecastPeriodPicker from '../components/Forecast/ForecastPeriodPicker';
import { hazardPuroks, markerSpots } from '../components/Map/hazardPins';
import './css/PublicMap.css';
import './css/PublicMapGis.css';
import './css/PublicMapLayers.css';
import '../components/Publish/css/PublishHazard.css';

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
// (components/Map/purokLevels.js); its legend says the thresholds.
const VIEWS = [
  { key: 'past', label: 'Past hazards', note: null },
  // Seasonal likelihood per barangay for a chosen month, from past years.
  // Rule-based counting (backend apps/history/forecast.py), not AI.
  { key: 'likely', label: 'Likely by month', note: FORECAST_DISCLAIMER },
];

// Barangay fill per likelihood level in the 'likely' view
const LIKELY_FILL = { High: 0.42, Moderate: 0.32, Low: 0.22, None: 0 };

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
    // Ground confirmation from the barangay. Only shown once somebody has
    // answered — an unanswered hazard says nothing about itself.
    verificationStatus: p.verification_status || 'Pending',
    verificationNote: p.verification_note || '',
    verifiedAt: p.verified_at,
    verifiedByName: p.verified_by_name,
    // Each barangay's own answer, and DRRMO's reply to a dispute
    verifications: p.verifications || [],
    reviewNote: p.review_note || '',
    reviewedAt: p.reviewed_at,
    reviewedByName: p.reviewed_by_name,
    // Extreme alerts: approved by a second officer, or sent on its own
    approvedByName: p.approved_by_name,
    // 'Red' while a raise to Extreme waits for a second officer
    pendingSeverity: p.pending_severity || '',
    // A fire made from reports: one pin per purok, shown instead of the
    // zone's shading and outline (see components/Map/hazardPins.js)
    pins: p.pins || [],
    autoReleased: !!p.auto_released,
    // Generated by `manage.py seed_fake_hazards`, not reported by anyone
    sample: !!p.is_sample,
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

// Corner handle for the outline being drawn, numbered in drawing order so
// officers can tell corners apart ("move corner 3"). Drawn as a div so it can
// be styled in CSS and is big enough to grab on a phone. Cached per number:
// a new icon object every render would make Leaflet rebuild each handle.
const cornerIcons = new Map();
function cornerIcon(n) {
  if (!cornerIcons.has(n)) {
    cornerIcons.set(n, L.divIcon({
      className: 'pub-corner-wrap',
      html: `<span class="pub-corner">${n}</span>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    }));
  }
  return cornerIcons.get(n);
}

// Clicking empty map either adds a publish corner or closes the panel
function MapClickHandler({ onMapClick }) {
  useMapEvents({ click: (e) => onMapClick(e.latlng) });
  return null;
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

  // Publishing: 'off' until DRRMO starts, 'placing' while waiting for the
  // first tap, then 'editing' with the form open while more corners of the
  // outline are tapped in.
  const { canPublish } = useAuth();
  const [publishMode, setPublishMode] = useState('off');
  const [draftPoints, setDraftPoints] = useState([]);
  // Which shaping method the publish panel is on. Hand drawing treats a tap
  // as a corner, which is what the map does below. A generating method will
  // treat a tap as a seed instead, and this is what it reads to tell them
  // apart — nothing branches on it yet.
  const [draftMethod, setDraftMethod] = useState('hand');
  // The officer's last tap while publishing: the starting point for a
  // generating method (water depth, past zone), which then hands back corners.
  const [draftSeed, setDraftSeed] = useState(null);
  const [publishNotice, setPublishNotice] = useState('');
  // The shape as the server will save it (cut at the city boundary), shown
  // while the officer checks the summary before sending
  const [previewShape, setPreviewShape] = useState(null);
  // Alt held down: place corners exactly where tapped, without snapping
  const altHeld = useRef(false);

  // F6: several hazard layers can be visible at once, so this is a set of
  // type names rather than the old single-select filter.
  const [activeTypes, setActiveTypes] = useState(() => new Set(HAZARD_TYPES));
  const [layerTypes, setLayerTypes] = useState([]);   // from /api/hazards/layers/
  const [layersFailed, setLayersFailed] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(true);
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

  // Load hazards. Pulled out of the effect so publishing can re-run it —
  // POST /api/hazards/create/ returns the plain serializer, not GeoJSON, so
  // featureToItem can't build a pin from the response.
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

  // Publishing and resolving each change more of the map than the thing the
  // user was looking at: the pins, the per-type counts in the Layers panel,
  // the purok colours and the past-incident lists. Rather than have every
  // action remember which of those to refresh, they both come back here.
  const refreshMap = useCallback(() => {
    clearHistoryCache();
    loadLayers();
    return Promise.all([loadHazards(), loadPurokLevels()]);
  }, [loadHazards, loadPurokLevels, loadLayers]);

  // Close the panel with the Escape key
  useEffect(() => {
    function onKey(e) {
      if (e.key !== 'Escape') return;
      if (publishMode !== 'off') { cancelPublish(); return; }
      setPanelOpen(false);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [publishMode]);

  // Sample hazards now come from the database like real ones, flagged
  // is_sample, so the map just needs to say when any are showing.
  const rawHazards = liveHazards;
  const showingSamples = liveHazards.some((h) => h.sample);

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
    if (!map || loading || hasFitted.current || hazards.length === 0) return;
    hasFitted.current = true;
    const bounds = L.latLngBounds(hazards.map((h) => h.position));
    map.fitBounds(bounds, { padding: [120, 120], maxZoom: 15 });
  }, [map, loading, hazards]);

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

  // Ground confirmation doesn't move a hazard anywhere, so the pin stays and
  // only its own state changes. Patched in place rather than reloading, so the
  // panel the user is reading doesn't close under them.
  function handleVerified(zone) {
    if (!zone?.id) return;
    setLiveHazards((prev) =>
      prev.map((h) =>
        String(h.id) === String(zone.id)
          ? {
              ...h,
              verificationStatus: zone.verification_status || 'Pending',
              verificationNote: zone.verification_note || '',
              verifiedAt: zone.verified_at,
              verifiedByName: zone.verified_by_name,
              verifications: zone.verifications || [],
              reviewNote: zone.review_note || '',
              reviewedAt: zone.reviewed_at,
              reviewedByName: zone.reviewed_by_name,
            }
          : h,
      ),
    );
  }

  /* ---------- Publishing ---------- */

  // Every barangay line and the coast, for snapping corners onto them
  const snapRings = useMemo(() => boundaryRings(barangays.map((b) => b.feature)), [barangays]);

  useEffect(() => {
    const track = (e) => { altHeld.current = e.altKey; };
    const release = () => { altHeld.current = false; };
    window.addEventListener('keydown', track);
    window.addEventListener('keyup', track);
    window.addEventListener('blur', release);
    return () => {
      window.removeEventListener('keydown', track);
      window.removeEventListener('keyup', track);
      window.removeEventListener('blur', release);
    };
  }, []);

  // A corner within a few pixels of a barangay line lands on the line, so
  // a zone meant to stop at a border stops exactly there. Hold Alt to skip.
  function snapLatLng(latlng) {
    if (!map || altHeld.current || !snapRings.length) return latlng;
    const { point } = snapPoint(
      [latlng.lat, latlng.lng],
      snapRings,
      (ll) => map.latLngToLayerPoint(ll),
      (pt) => {
        const ll = map.layerPointToLatLng(L.point(pt.x, pt.y));
        return [ll.lat, ll.lng];
      },
    );
    return { lat: point[0], lng: point[1] };
  }

  function startPublish() {
    setSelection(null);
    setPanelOpen(false);
    setDraftPoints([]);
    setDraftSeed(null);
    setPublishMode('placing');
  }

  function cancelPublish() {
    setPublishMode('off');
    setDraftPoints([]);
    setDraftSeed(null);
    setPreviewShape(null);
  }

  // One handler for every map click: add a corner to the outline while
  // publishing, otherwise close whichever details panel is open.
  function handleMapClick(clicked) {
    const latlng = publishMode === 'off' ? clicked : snapLatLng(clicked);
    if (publishMode === 'placing' || publishMode === 'editing') {
      // Hand drawing reads a tap as a corner. A generating method takes the
      // tap as its starting point (unsnapped: it is where the officer saw the
      // hazard) and hands back a finished outline through onReplacePoints.
      // Before the panel opens the method is still 'hand', so the very first
      // tap is both; the panel replaces that lone corner once it generates.
      if (draftMethod === 'hand') {
        setDraftPoints((pts) => [...pts, [latlng.lat, latlng.lng]]);
      }
      setDraftSeed([clicked.lat, clicked.lng]);
      setPublishMode('editing');
      return;
    }
    setPanelOpen(false);
  }

  function moveDraftCorner(index, latlng) {
    setDraftPoints((pts) => pts.map((p, i) => (i === index ? [latlng.lat, latlng.lng] : p)));
  }

  function undoDraftCorner() {
    setDraftPoints((pts) => pts.slice(0, -1));
  }

  async function handlePublished(zone) {
    cancelPublish();
    // A held Extreme alert isn't on the map yet, so without a word here the
    // officer would see nothing happen and might publish it again.
    if (zone?.status === 'Awaiting_Approval') {
      const due = zone.approval?.due_at ? new Date(zone.approval.due_at) : null;
      setPublishNotice(
        'Sent for approval. Another DRRMO officer has to approve this Extreme alert before it goes out'
        + (due ? `, or it goes out on its own at ${due.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}.` : '.'),
      );
    }
    // A new zone changes the pins and the Layers counts, and it may raise the
    // shading a level where it overlaps past events.
    await refreshMap();
  }

  // Roughly which barangay the outline sits in, so DRRMO can see it before
  // publishing. The server makes the final call from the actual overlap.
  // The middle of the outline is tried first; for an odd shape whose middle
  // falls outside, the first corner that lands in a barangay is used.
  const draftBarangay = useMemo(() => {
    if (!draftPoints.length) return null;
    const probes = [middleOf(draftPoints), ...draftPoints];
    for (const p of probes) {
      const home = barangays.find((b) => containsPoint(b.feature, p));
      if (home) return { id: home.id, name: home.name };
    }
    return null;
  }, [draftPoints, barangays]);

  const draftOutsideCorners = useMemo(
    () => draftPoints.filter((p) => !barangays.some((b) => containsPoint(b.feature, p))).length,
    [draftPoints, barangays],
  );

  // Seasonal likelihood, fetched only while that view is open
  useEffect(() => {
    if (view !== 'likely') return undefined;
    let cancelled = false;
    historyApi.forecast(periodParams(likelyPeriod))
      .then((d) => { if (!cancelled) setLikely(d); })
      .catch(() => { if (!cancelled) setLikely({ error: true, results: [] }); });
    return () => { cancelled = true; };
  }, [view, likelyPeriod]);

  // Per barangay: its rows for the hazard types shown, worst first. The
  // layer checkboxes apply here too, so "Fire only" shows fire likelihood.
  const likelyByBarangay = useMemo(() => {
    const map = new Map();
    (likely?.results || [])
      .filter((r) => activeTypes.has(hazardKey(r.hazard_type)))
      .forEach((r) => {
        const key = String(r.barangay_id);
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(r);
      });
    map.forEach((rows) => rows.sort((a, b) => likelihoodInfo(b.level).rank - likelihoodInfo(a.level).rank
      || b.probability - a.probability));
    return map;
  }, [likely, activeTypes]);

  // Thin dark boundaries, like sub-catchment lines on a GIS map. Transparent fill keeps them clickable.
  function barangayStyle(feature) {
    if (view === 'likely') {
      const rows = likelyByBarangay.get(String(featureId(feature))) || [];
      const level = rows[0]?.level || 'None';
      const info = likelihoodInfo(level);
      return {
        className: 'pm-brgy', color: '#2b2b2b', weight: 1, opacity: 0.8,
        fillColor: info.color, fillOpacity: LIKELY_FILL[level] ?? 0,
      };
    }
    // Bold only while its panel is open
    const selected =
      panelOpen && selectedBarangayId != null && String(featureId(feature)) === String(selectedBarangayId);
    return selected
      ? { className: 'pm-brgy', color: '#111111', weight: 2.6, opacity: 1, fillColor: '#46923c', fillOpacity: 0.07 }
      : { className: 'pm-brgy', color: '#2b2b2b', weight: 1, opacity: 0.8, fillOpacity: 0 };
  }

  const visibleTypeList = useMemo(() => [...activeTypes], [activeTypes]);
  const viewNote = VIEWS.find((m) => m.key === view).note;
  const levels = purokLevels?.levels || null;
  const thresholds = purokLevels?.thresholds || null;
  // What hovering a purok says: its name, and in Past hazards its counts.
  // Stable between renders, since the hover listeners are rebuilt when it changes.
  const purokTip = useCallback((f) => {
    const line = view === 'past' && levels
      ? historyLine(levels.get(String(f.id ?? f.properties?.id)), visibleTypeList, thresholds.years)
      : '';
    return line ? `${purokTooltip(f)}<br>${line}` : purokTooltip(f);
  }, [view, levels, thresholds, visibleTypeList]);
  const layerName =
    activeTypes.size === HAZARD_TYPES.length ? 'all hazards'
      : activeTypes.size === 0 ? 'no layers shown'
        : visibleTypeList.join(', ');

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
        className={[
          'pm-stage',
          publishMode !== 'off' ? 'is-placing' : '',
          // The drawing card sits bottom-right, where the zoom buttons are
          publishMode === 'editing' ? 'has-pub-panel' : '',
        ].filter(Boolean).join(' ')}
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

          {/* Purok outlines of the selected barangay, under the barangay lines;
              hovering one names it, and the one the panel shows is bold */}
          <PurokLayer
            geo={selectedPuroks}
            selectedId={selection?.kind === 'barangay' ? selection.purokId ?? null : null}
            tooltipFor={purokTip}
          />

          {/* The puroks of the hazard the panel shows: bold and lightly
              filled, over the past-hazard fills, under the barangay lines */}
          {selectedHazardPuroks && (
            <Pane name="hazard-puroks" style={{ zIndex: 380, pointerEvents: 'none' }}>
              <GeoJSON
                key={`hazard-puroks-${selectedHazardId}-${selectedHazardPuroks.features.map((f) => f.id).join(',')}`}
                data={selectedHazardPuroks}
                style={(f) => ({ ...purokStyle(f), ...PUROK_OF_HAZARD })}
                interactive={false}
              />
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
              key={`brgy-${selectedBarangayId ?? 'none'}-${panelOpen}-${publishMode}-${view}-${periodLabel(likelyPeriod)}-${likely?.results?.length ?? 0}-${[...activeTypes].join('')}-${!!selectedPuroks}`}
              data={barangayGeo}
              style={barangayStyle}
              bubblingMouseEvents={false}
              onEachFeature={(feature, layer) => {
                // Inside the selected barangay its puroks name themselves on hover
                if (selectedPuroks && String(featureId(feature)) === String(selectedBarangayId)) return;
                const name = feature.properties?.name || 'Barangay';
                let tip = name;
                if (view === 'likely') {
                  const rows = likelyByBarangay.get(String(featureId(feature))) || [];
                  // A past period also says what happened in it
                  const happened = (r) => (r.actual == null ? '' : `; ${r.actual || 'none'} happened`);
                  tip = rows.length
                    ? `<strong>${name}</strong><br>${rows.slice(0, 3)
                      .map((r) => `${r.hazard_type}: ${likelihoodInfo(r.level).label} (${periodYearsText(r, likelyPeriod)}${happened(r)})`)
                      .join('<br>')}`
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
                  // Barangay polygons cover the whole city, so while a hazard
                  // is being placed they have to pass the click through
                  // instead of opening the barangay panel.
                  if (publishMode !== 'off') {
                    handleMapClick(e.latlng);
                    return;
                  }
                  const f = e.propagatedFrom?.feature || e.layer?.feature;
                  if (!f) return;
                  // The first tap opens the barangay; a tap inside it after
                  // that picks the purok there, or the whole barangay again
                  // where no purok is drawn
                  const barangay = featureToBarangay(f);
                  const open = panelOpen && selection?.kind === 'barangay'
                    && String(selection.id) === String(barangay.id);
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
              pathOptions={{ color: '#1f3d1c', weight: 2, fillColor: '#ffffff', fillOpacity: 1 }}
            />
          )}

          {/* Outline being drawn while a hazard is published. Not
              interactive, so taps on it pass through and add corners. */}

          {/* What will actually be saved: the outline cut at the city boundary */}
          {previewShape && (
            <GeoJSON
              key={JSON.stringify(previewShape).length}
              data={previewShape}
              interactive={false}
              style={{ color: '#0b6b3a', weight: 2, fillColor: '#1f9d55', fillOpacity: 0.35 }}
            />
          )}

          {/* Starting point of a generating method */}
          {publishMode === 'editing' && draftSeed && draftMethod !== 'hand' && (
            <Marker
              position={draftSeed}
              interactive={false}
              icon={L.divIcon({ className: '', html: '<div class="pub-seed"></div>', iconSize: [18, 18], iconAnchor: [9, 9] })}
            />
          )}

          {draftPoints.length >= MIN_CORNERS && (
            <Polygon
              positions={draftPoints}
              interactive={false}
              pathOptions={{ color: '#1f3d1c', weight: 2, dashArray: '6 4', fillOpacity: 0.12 }}
            />
          )}
          {draftPoints.length === 2 && (
            <Polyline
              positions={draftPoints}
              interactive={false}
              pathOptions={{ color: '#1f3d1c', weight: 2, dashArray: '6 4' }}
            />
          )}
          {draftPoints.map((p, i) => (
            <Marker
              key={`corner-${i}`}
              position={p}
              icon={cornerIcon(i + 1)}
              draggable
              keyboard={false}
              title={`Corner ${i + 1}. Drag to move.`}
              // 'drag' fires on every mouse move, so the outline and the
              // area follow the corner live instead of jumping on release.
              eventHandlers={{
                drag: (e) => moveDraftCorner(i, e.target.getLatLng()),
                dragend: (e) => moveDraftCorner(i, snapLatLng(e.target.getLatLng())),
              }}
            />
          ))}

          {visibleHazards.flatMap((h) => markerSpots(h).map((spot) => (
            <Marker
              key={spot.key}
              position={spot.position}
              icon={pinIcon(h, h.id === selectedHazardId, overlaps.has(h.id))}
              title={`${spot.purok || h.location}: ${h.type}, ${severityInfo(h.severity).label}`}
              eventHandlers={{
                click: (e) => {
                  // A pin's click reports the pin's own position; while
                  // drawing, the corner belongs where the finger landed.
                  if (publishMode !== 'off') {
                    handleMapClick(map && e.originalEvent ? map.mouseEventToLatLng(e.originalEvent) : e.latlng);
                    return;
                  }
                  selectHazard(h);
                },
              }}
            />
          )))}
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

          <div className="pm-chips" role="group" aria-label="Map layers">
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

            {canPublish && publishMode === 'off' && (
              <button type="button" className="pm-chip pm-chip-publish" onClick={startPublish}>
                + Publish hazard
              </button>
            )}
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
        <div className={`pm-status ${panelOpen ? 'is-hidden-mobile' : ''}`}>
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
          {!loading && showingSamples && (
            <span className="pm-pill">Includes sample data, not real hazards</span>
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
            <span>Legend</span>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
          </button>

          {view === 'likely' ? (
            <>
              <p className="pm-legend-title">
                Likely in {periodLabel(likelyPeriod)}: {layerName.toLowerCase()}
              </p>
              <ul>
                {['High', 'Moderate', 'Low', 'None'].map((k) => (
                  <li key={k}>
                    <span
                      className="pm-legend-swatch"
                      style={{ background: LIKELIHOOD[k].color, opacity: k === 'None' ? 0.35 : 1 }}
                    />
                    {LIKELIHOOD[k].label}
                  </li>
                ))}
              </ul>
              {likely?.error && <p className="pm-legend-note">Could not load the likelihood.</p>}
              {/* The past years the colours come from, so a coming year reads as
                  the usual pattern; a past period also says what happened */}
              {likely && !likely.error && (
                <p className="pm-legend-note">
                  {likely.years?.length
                    ? `From ${periodIn(likelyPeriod)} in ${yearSpan(likely.years)}.`
                    : `Nothing on record for ${periodIn(likelyPeriod)} in past years.`}
                  {likely.outcome && (likely.outcome.complete
                    ? ` It is over: ${likely.outcome.events} event${likely.outcome.events === 1 ? '' : 's'} happened.`
                    : ` It has started: ${likely.outcome.events} event${likely.outcome.events === 1 ? '' : 's'} so far.`)}
                </p>
              )}
              {likely?.limited && likely.years?.length > 0 && (
                <p className="pm-legend-note">
                  Only {likely.years.length} past year{likely.years.length === 1 ? '' : 's'} on record, so these
                  levels are rough.
                </p>
              )}
              {likely?.basis?.sample_records > 0 && (
                <p className="pm-legend-note">
                  Includes {likely.basis.sample_records} sample records made for testing.
                </p>
              )}
            </>
          ) : (
            <>
              <p className="pm-legend-title">Past hazards: {layerName.toLowerCase()}</p>
              <ul>
                {PUROK_LEVELS.map((l) => (
                  <li key={l.code}>
                    <span className="pm-legend-swatch" style={{ background: l.color }} />
                    {l.label}
                  </li>
                ))}
              </ul>
              {thresholds && <p className="pm-legend-note">{thresholdText(thresholds)}</p>}
              <p className="pm-legend-note">Pins: active hazards, coloured by alert level</p>
            </>
          )}
          {legendOpen && (
            <>
            {viewNote && <p className="pm-legend-note">{viewNote}</p>}
            {/* The susceptibility layers are built offline from elevation
                and river data; say when, so nobody mistakes them for live. */}
            {susceptibility.index?.generated && (
              <p className="pm-legend-note">
                Susceptibility data as of{' '}
                {new Date(susceptibility.index.generated).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })}.
              </p>
            )}
            {/* Data credits the elevation licence requires wherever the layers are shown */}
            {(susceptibility.index?.sources || []).map((source) => (
              <p key={source} className="pm-legend-note pm-legend-source">{source}</p>
            ))}
            </>
          )}

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
          onVerified={handleVerified}
          stack={stack}
          onPick={showStacked}
        />
        {publishNotice && (
          <div className="pub-notice" role="status">
            <span>{publishNotice}</span>
            <button type="button" onClick={() => setPublishNotice('')}>OK</button>
          </div>
        )}
        {publishMode === 'placing' && (
          <div className="pub-hint">
            <span>Tap the map to start outlining the affected area</span>
            <button type="button" onClick={cancelPublish}>Cancel</button>
          </div>
        )}

        {publishMode === 'editing' && (
          <PublishHazardPanel
            points={draftPoints}
            onUndo={undoDraftCorner}
            onClear={() => { setDraftPoints([]); setDraftSeed(null); }}
            barangay={draftBarangay}
            outsideCorners={draftOutsideCorners}
            boundariesReady={barangays.length > 0}
            onCancel={cancelPublish}
            onPublished={handlePublished}
            onPreviewShape={setPreviewShape}
            onReplacePoints={setDraftPoints}
            onMethodChange={setDraftMethod}
            seed={draftSeed}
            susceptibilityIndex={susceptibility.index}
          />
        )}

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
        />
      </div>
    </div>
  );
}