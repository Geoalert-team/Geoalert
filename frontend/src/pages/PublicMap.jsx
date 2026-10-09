import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, Circle, ZoomControl, ScaleControl, Pane, ImageOverlay, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import PublishHazardPanel from '../components/Publish/PublishHazardPanel';
import LayerControl from '../components/Map/LayerControl';
import HazardPanel from '../components/Map/HazardPanel';
import BarangayPanel from '../components/Map/BarangayPanel';
import { useSusceptibility } from '../components/Map/susceptibility';
import { HAZARD_LEVELS, useHazardLevelLayer } from '../components/Map/hazardLevels';
import { HAZARD_TYPES, SEVERITY, severityInfo, hazardKey, hazardIconPath, hazardColor } from '../components/Map/hazardInfo';
import { hazardsApi } from '../api/hazardsApi';
import { barangaysApi } from '../api/barangaysApi';
import { SAMPLE_HAZARDS, SHOW_SAMPLE_DATA, SHOW_TEST_PINS, TEST_HAZARDS } from '../data/sampleHazards';
import './css/PublicMap.css';
import './css/PublicMapGis.css';
import './css/PublicMapLayers.css';
import '../components/Publish/css/PublishHazard.css';

// Talisay City, Cebu
const TALISAY_CENTER = [10.2446, 123.8473];
const PANEL_WIDTH = 400; // keep in sync with .pm-panel width in PublicMap.css
const MOBILE_BREAKPOINT = 860; // keep in sync with the @media rule in PublicMap.css

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

// Size limits for a drawn zone's core (used for zooming to sample pins)
const MIN_RADIUS = 60;
const MAX_RADIUS = 600;
const SAMPLE_ZOOM_RADIUS = 500; // meters shown around a pin when it is selected

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
    verificationStatus: p.verification_status || 'Pending',
    verifiedByName: p.verified_by_name,
    verifiedAt: p.verified_at,
    verificationNote: p.verification_note,
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
// on a white disc. The corner badge shows the barangay check.
const BADGES = {
  Confirmed: '<span class="pm-drop-badge is-confirmed"><svg viewBox="0 0 24 24"><path d="M5.5 12.5l4 4 9-9"/></svg></span>',
  Disputed: '<span class="pm-drop-badge is-disputed">!</span>',
  Pending: '<span class="pm-drop-badge is-pending"></span>',
};

function pinIcon(item, selected, overlapping) {
  const sev = severityInfo(item.severity);
  const badge = BADGES[item.verificationStatus] || BADGES.Pending;
  return L.divIcon({
    className: 'pm-drop-wrap',
    html: `<span class="pm-drop${selected ? ' is-selected' : ''}${overlapping ? ' has-overlap' : ''}">
             <svg viewBox="0 0 44 56" aria-hidden="true">
               <path class="pm-drop-body" style="fill:${sev.color}" d="M22 54s-17-19.6-17-32a17 17 0 0 1 34 0c0 12.4-17 32-17 32z"/>
               <circle cx="22" cy="22" r="12.5" fill="#fff"/>
               <path d="${hazardIconPath(item.type)}" transform="translate(13 13) scale(0.75)" fill="${hazardColor(item.type)}"/>
             </svg>
             ${badge}
           </span>`,
    iconSize: [44, 56],
    iconAnchor: [22, 54],
  });
}

// Clicking empty map either places a publish point or closes the panel
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
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  // Have real hazards ever arrived? Decides whether an empty map means
  // "nothing active" or "backend has no data yet, show the samples".
  const [hadLiveData, setHadLiveData] = useState(false);

  // Publishing: 'off' until DRRMO starts, 'placing' while waiting for a tap,
  // then the form opens with draftPoint set.
  const { canPublish } = useAuth();
  const [publishMode, setPublishMode] = useState('off');
  const [draftPoint, setDraftPoint] = useState(null);
  const [draftRadius, setDraftRadius] = useState(250);

  // F6: several hazard layers can be visible at once, so this is a set of
  // type names rather than the old single-select filter.
  const [activeTypes, setActiveTypes] = useState(() => new Set(HAZARD_TYPES));
  const [layerTypes, setLayerTypes] = useState([]);   // from /api/hazards/layers/
  const [layersFailed, setLayersFailed] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(true);
  const [query, setQuery] = useState('');
  const [selection, setSelection] = useState(null); // { kind: 'hazard' | 'barangay', id }
  const [panelOpen, setPanelOpen] = useState(false);
  const [basemap, setBasemap] = useState('streets');
  const susceptibility = useSusceptibility();
  const [searchParams, setSearchParams] = useSearchParams();

  // Load hazards. Pulled out of the effect so publishing can re-run it —
  // POST /api/hazards/create/ returns the plain serializer, not GeoJSON, so
  // featureToItem can't build a pin from the response.
  const loadHazards = useCallback(() => {
    return hazardsApi
      .list()
      .then((data) => {
        const features = data?.features || data?.results?.features || [];
        const items = features
          .filter((f) => !f.properties?.status || f.properties.status === 'Active')
          .map(featureToItem)
          .filter(Boolean);
        setLiveHazards(items);
        if (items.length > 0) setHadLiveData(true);
      })
      .catch(() => setLoadFailed(true));
  }, []);

  // Load hazards and barangay outlines once
  useEffect(() => {
    loadHazards().finally(() => setLoading(false));
    barangaysApi.list().then(setBarangayGeo).catch(() => {});
  }, [loadHazards]);

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

  // Use real hazards when there are any; otherwise show the labelled samples
  // Samples are a first-run placeholder only. Without the hadLiveData guard,
  // resolving the last real hazard empties liveHazards and the sample pins
  // pop back in — which looks like the resolve created new hazards.
  const usingSample = SHOW_SAMPLE_DATA && !loading && !hadLiveData && liveHazards.length === 0;
  // Test pins from sampleHazards.js are added on top while SHOW_TEST_PINS is true
  const rawHazards = useMemo(() => {
    const base = usingSample ? SAMPLE_HAZARDS : liveHazards;
    return SHOW_TEST_PINS ? [...base, ...TEST_HAZARDS] : base;
  }, [usingSample, liveHazards]);

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

  const selectedHazard = hazards.find((h) => h.id === selectedHazardId) || null;
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
  // points at /map?zone=<id>. Runs once, then strips the parameter so a later
  // refresh doesn't reopen a panel the user has closed.
  const deepLinked = useRef(false);
  useEffect(() => {
    if (deepLinked.current || loading) return;
    const zoneId = searchParams.get('zone');
    if (!zoneId) return;

    const target = hazards.find((h) => String(h.id) === String(zoneId));
    if (!target) return;

    deepLinked.current = true;
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
    setSelection({ kind: 'hazard', id: item.id });
    setPanelOpen(true);
    setQuery('');
    if (!map) return;

    // Zoom to the area around the pin, beside the panel
    const bounds = L.latLng(item.position).toBounds(SAMPLE_ZOOM_RADIUS * 2);
    map.flyToBounds(bounds, { ...panelPadding(), maxZoom: 17, duration: 0.8 });
  }

  function selectBarangay(barangay) {
    setSelection({ kind: 'barangay', id: barangay.id });
    setPanelOpen(true);
    setQuery('');
    if (!map || !barangay.feature?.geometry) return;

    const bounds = L.geoJSON(barangay.feature).getBounds();
    if (!bounds.isValid()) return;

    // Fit the barangay into the part of the map the panel doesn't cover
    map.flyToBounds(bounds, { ...panelPadding(), maxZoom: 16, duration: 0.8 });
  }

  function selectResult(result) {
    if (result.kind === 'barangay') selectBarangay(result.item);
    else selectHazard(result.item);
  }

  function handleSearchKey(e) {
    if (e.key === 'Enter' && searchResults.length > 0) selectResult(searchResults[0]);
  }

  // Swap in the updated zone after barangay personnel confirm or dispute it
  function handleVerified(feature) {
    const updated = featureToItem(feature);
    if (!updated) return;
    setLiveHazards((prev) => prev.map((h) => (h.id === updated.id ? updated : h)));
  }

  // A resolved zone is no longer active, so drop its pin and close the panel.
  // PATCH /api/hazards/<id>/ returns the plain serializer rather than GeoJSON,
  // so featureToItem can't be reused here — match on the id instead.
  function handleResolved(zone) {
    const resolvedId = zone?.id ?? selectedHazardId;
    setLiveHazards((prev) => prev.filter((h) => String(h.id) !== String(resolvedId)));
    setSelection(null);
    setPanelOpen(false);
  }

  /* ---------- Publishing ---------- */

  function startPublish() {
    setSelection(null);
    setPanelOpen(false);
    setDraftPoint(null);
    setPublishMode('placing');
  }

  function cancelPublish() {
    setPublishMode('off');
    setDraftPoint(null);
  }

  // One handler for every map click: place a draft point while publishing,
  // otherwise close whichever details panel is open.
  function handleMapClick(latlng) {
    if (publishMode === 'placing' || publishMode === 'editing') {
      setDraftPoint([latlng.lat, latlng.lng]);
      setPublishMode('editing');
      return;
    }
    setPanelOpen(false);
  }

  async function handlePublished() {
    cancelPublish();
    await loadHazards();
  }

  // Which barangay the draft point falls inside, so DRRMO doesn't pick it
  // by hand and can't file a hazard against the wrong one.
  const draftBarangay = useMemo(() => {
    if (!draftPoint) return null;
    const home = barangays.find((b) => containsPoint(b.feature, draftPoint));
    return home ? { id: home.id, name: home.name } : null;
  }, [draftPoint, barangays]);

  // Thin dark boundaries, like sub-catchment lines on a GIS map. Transparent fill keeps them clickable.
  function barangayStyle(feature) {
    // Bold only while its panel is open
    const selected =
      panelOpen && selectedBarangayId != null && String(featureId(feature)) === String(selectedBarangayId);
    return selected
      ? { className: 'pm-brgy', color: '#111111', weight: 2.6, opacity: 1, fillColor: '#1c2e4a', fillOpacity: 0.07 }
      : { className: 'pm-brgy', color: '#2b2b2b', weight: 1, opacity: 0.8, fillOpacity: 0 };
  }

  const visibleTypeList = useMemo(() => [...activeTypes], [activeTypes]);
  const levelUrl = useHazardLevelLayer(susceptibility.index, hazards, visibleTypeList);
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

      <div className={`pm-stage ${publishMode === 'placing' ? 'is-placing' : ''}`}>
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
            />
          )}
          <ZoomControl position="bottomright" />
          <ScaleControl position="bottomright" imperial={false} />
          <MapClickHandler onMapClick={handleMapClick} />

          {/* Hazard levels from active reports, spread over susceptible ground */}
          <Pane name="hazard-levels" style={{ zIndex: 350 }}>
            {levelUrl && (
              <ImageOverlay
                key={levelUrl.length}
                url={levelUrl}
                bounds={susceptibility.index.bounds}
                opacity={BASEMAPS[basemap].layerOpacity}
                className="pm-levels"
              />
            )}
          </Pane>

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
              key={`brgy-${selectedBarangayId ?? 'none'}-${panelOpen}-${publishMode}`}
              data={barangayGeo}
              style={barangayStyle}
              bubblingMouseEvents={false}
              onEachFeature={(feature, layer) => {
                layer.bindTooltip(feature.properties?.name || 'Barangay', {
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
                  if (f) selectBarangay(featureToBarangay(f));
                },
              }}
            />
          )}


          {/* Draft circle while a hazard is being published */}
          {draftPoint && (
            <Circle
              center={draftPoint}
              radius={draftRadius}
              pathOptions={{ color: '#1c2e4a', weight: 2, dashArray: '6 4', fillOpacity: 0.12 }}
            />
          )}

          {visibleHazards.map((h) => (
            <Marker
              key={h.id}
              position={h.position}
              icon={pinIcon(h, h.id === selectedHazardId, overlaps.has(h.id))}
              title={`${h.location}: ${h.type}, ${severityInfo(h.severity).label}`}
              eventHandlers={{
                click: (e) => {
                  if (publishMode !== 'off') { handleMapClick(e.latlng); return; }
                  selectHazard(h);
                },
              }}
            />
          ))}
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
            />
          )}
        </div>

        {/* ============ STATUS MESSAGES ============ */}
        <div className={`pm-status ${panelOpen ? 'is-hidden-mobile' : ''}`}>
          {loading && <span className="pm-pill">Loading hazards…</span>}
          {!loading && loadFailed && <span className="pm-pill pm-pill-error">Live hazard data is unavailable right now</span>}
          {!loading && !usingSample && hazards.length === 0 && !loadFailed && (
            <span className="pm-pill">No active hazards right now</span>
          )}
          {susceptibility.status === 'missing' && (
            <span className="pm-pill pm-pill-error">Hazard layer data not built yet</span>
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

          <p className="pm-legend-title">Hazard level: {layerName.toLowerCase()}</p>
          <ul>
            {[...HAZARD_LEVELS].reverse().map((l) => (
              <li key={l.key}>
                <span className="pm-legend-swatch" style={{ background: l.color }} />
                {l.label}
              </li>
            ))}
          </ul>

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

              <p className="pm-legend-title pm-legend-title-sub">Barangay check</p>
              <ul>
                <li>
                  <span className="pm-drop-badge is-confirmed is-static">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5.5 12.5l4 4 9-9" /></svg>
                  </span>
                  Confirmed on the ground
                </li>
                <li><span className="pm-drop-badge is-disputed is-static" aria-hidden="true">!</span>Barangay reported changes</li>
                <li><span className="pm-drop-badge is-pending is-static" />Not yet confirmed</li>
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
          onVerified={handleVerified}
          onResolved={handleResolved}
          overlaps={selectedHazard ? overlaps.get(selectedHazard.id) || [] : []}
        />
        {publishMode === 'placing' && (
          <div className="pub-hint">
            <span>Tap the map where the hazard is</span>
            <button type="button" onClick={cancelPublish}>Cancel</button>
          </div>
        )}

        {publishMode === 'editing' && draftPoint && (
          <PublishHazardPanel
            center={draftPoint}
            radius={draftRadius}
            onRadius={setDraftRadius}
            barangay={draftBarangay}
            onCancel={cancelPublish}
            onPublished={handlePublished}
          />
        )}

        <BarangayPanel
          barangay={selectedBarangay}
          hazards={barangayHazards}
          open={panelOpen && !!selectedBarangay}
          onClose={() => setPanelOpen(false)}
          onSelectHazard={selectHazard}
        />
      </div>
    </div>
  );
}