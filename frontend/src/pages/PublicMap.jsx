import React, { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, ZoomControl, ScaleControl, Pane, ImageOverlay } from 'react-leaflet';
import L from 'leaflet';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import HazardPanel from '../components/Map/HazardPanel';
import BarangayPanel from '../components/Map/BarangayPanel';
import { LAYER_FOR_FILTER, useSusceptibility } from '../components/Map/susceptibility';
import { HAZARD_LEVELS, useHazardLevelLayer } from '../components/Map/hazardLevels';
import { HAZARD_TYPES, SEVERITY, severityInfo, hazardKey, hazardIconPath, hazardColor } from '../components/Map/hazardInfo';
import { hazardsApi } from '../api/hazardsApi';
import { barangaysApi } from '../api/barangaysApi';
import { SAMPLE_HAZARDS, SHOW_SAMPLE_DATA, SHOW_TEST_PINS, TEST_HAZARDS } from '../data/sampleHazards';
import './css/PublicMap.css';
import './css/PublicMapGis.css';
import './css/PublicMapLayers.css';

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

function pinIcon(item, selected) {
  const sev = severityInfo(item.severity);
  const badge = BADGES[item.verificationStatus] || BADGES.Pending;
  return L.divIcon({
    className: 'pm-drop-wrap',
    html: `<span class="pm-drop${selected ? ' is-selected' : ''}">
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

  const [typeFilter, setTypeFilter] = useState('All');
  const [query, setQuery] = useState('');
  const [selection, setSelection] = useState(null); // { kind: 'hazard' | 'barangay', id }
  const [panelOpen, setPanelOpen] = useState(false);
  const [basemap, setBasemap] = useState('streets');
  const susceptibility = useSusceptibility();

  // Load hazards and barangay outlines once
  useEffect(() => {
    hazardsApi
      .list()
      .then((data) => {
        const features = data?.features || data?.results?.features || [];
        const items = features
          .filter((f) => !f.properties?.status || f.properties.status === 'Active')
          .map(featureToItem)
          .filter(Boolean);
        setLiveHazards(items);
      })
      .catch(() => setLoadFailed(true))
      .finally(() => setLoading(false));

    barangaysApi.list().then(setBarangayGeo).catch(() => {});
  }, []);

  // Close the panel with the Escape key
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') setPanelOpen(false);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Use real hazards when there are any; otherwise show the labelled samples
  const usingSample = SHOW_SAMPLE_DATA && !loading && liveHazards.length === 0;
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
    () => hazards.filter((h) => typeFilter === 'All' || hazardKey(h.type) === typeFilter),
    [hazards, typeFilter],
  );

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

  // Paddings that keep a zoomed area clear of the details panel and search bar
  function panelPadding() {
    return isDesktop()
      ? { paddingTopLeft: [PANEL_WIDTH + 32, 96], paddingBottomRight: [32, 32] }
      : { paddingTopLeft: [24, 140], paddingBottomRight: [24, map.getSize().y * 0.62] };
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

  // Thin dark boundaries, like sub-catchment lines on a GIS map. Transparent fill keeps them clickable.
  function barangayStyle(feature) {
    const selected = selectedBarangayId != null && String(featureId(feature)) === String(selectedBarangayId);
    return selected
      ? { className: 'pm-brgy', color: '#111111', weight: 2.6, opacity: 1, fillColor: '#1c2e4a', fillOpacity: 0.07 }
      : { className: 'pm-brgy', color: '#2b2b2b', weight: 1, opacity: 0.8, fillOpacity: 0 };
  }

  const layerKey = LAYER_FOR_FILTER[typeFilter] || 'all';
  const levelUrl = useHazardLevelLayer(susceptibility.index, hazards, layerKey);
  const layerName = typeFilter === 'All' ? 'All hazards' : typeFilter;

  return (
    <div className="pm">
      <PublicNavbar />

      <div className="pm-stage">
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
              key={`brgy-${selectedBarangayId ?? 'none'}`}
              data={barangayGeo}
              style={barangayStyle}
              onEachFeature={(feature, layer) => {
                layer.bindTooltip(feature.properties?.name || 'Barangay', {
                  sticky: true,
                  direction: 'top',
                  className: 'pm-brgy-tip',
                });
              }}
              eventHandlers={{
                click: (e) => {
                  const f = e.propagatedFrom?.feature || e.layer?.feature;
                  if (f) selectBarangay(featureToBarangay(f));
                },
              }}
            />
          )}


          {visibleHazards.map((h) => (
            <Marker
              key={h.id}
              position={h.position}
              icon={pinIcon(h, h.id === selectedHazardId)}
              title={`${h.location}: ${h.type}, ${severityInfo(h.severity).label}`}
              eventHandlers={{ click: () => selectHazard(h) }}
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

          <div className="pm-chips" role="group" aria-label="Filter by hazard">
            {['All', ...HAZARD_TYPES].map((type) => (
              <button
                key={type}
                type="button"
                className={`pm-chip ${typeFilter === type ? 'is-active' : ''}`}
                aria-pressed={typeFilter === type}
                onClick={() => setTypeFilter(type)}
              >
                {type === 'All' ? 'All hazards' : type}
              </button>
            ))}
          </div>
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
        <div className={`pm-legend ${panelOpen ? 'is-hidden-mobile' : ''}`}>
          <p className="pm-legend-title">Hazard level: {layerName.toLowerCase()}</p>
          <ul>
            {[...HAZARD_LEVELS].reverse().map((l) => (
              <li key={l.key}>
                <span className="pm-legend-swatch" style={{ background: l.color }} />
                {l.label}
              </li>
            ))}
          </ul>
          <p className="pm-legend-title pm-legend-title-sub">Pin color</p>
          <ul>
            {Object.entries(SEVERITY).map(([code, sev]) => (
              <li key={code}>
                <span className="pm-legend-dot" style={{ background: sev.color }} />
                {sev.label}
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
          </ul>
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
        />
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