import React, { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, Circle, ZoomControl } from 'react-leaflet';
import L from 'leaflet';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import HazardPanel from '../components/Map/HazardPanel';
import BarangayPanel from '../components/Map/BarangayPanel';
import { HAZARD_TYPES, SEVERITY, severityInfo, hazardKey, hazardIconPath, hazardColor } from '../components/Map/hazardInfo';
import { hazardsApi } from '../api/hazardsApi';
import { barangaysApi } from '../api/barangaysApi';
import { SAMPLE_HAZARDS, SHOW_SAMPLE_DATA } from '../data/sampleHazards';
import './css/PublicMap.css';
import './css/PublicMapGis.css';

// Talisay City, Cebu
const TALISAY_CENTER = [10.2446, 123.8473];
const PANEL_WIDTH = 400; // keep in sync with .pm-panel width in PublicMap.css
const MOBILE_BREAKPOINT = 860; // keep in sync with the @media rule in PublicMap.css

// Base maps. Satellite uses Esri imagery with a road/place-name overlay on top.
const BASEMAPS = {
  satellite: {
    label: 'Satellite',
    layers: [
      {
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
      },
      {
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}',
        attribution: '',
      },
      {
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
        attribution: '',
      },
    ],
  },
  street: {
    label: 'Map',
    layers: [
      {
        url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attribution: '&copy; OpenStreetMap contributors',
      },
    ],
  },
};

// Risk halo around each hazard: one circle filled with a radial gradient that
// blends Extreme -> Moderate -> Low and fades out at the edge (no outline).
// An Extreme hazard runs red -> orange -> green; Moderate runs orange -> green;
// Low is green only. Stops are [offset, severity code, opacity].
const HALO = {
  Red: {
    scale: 2, // outer edge = 2x the core radius
    stops: [[0, 'Red', 0.62], [0.34, 'Red', 0.55], [0.56, 'Orange', 0.46], [0.72, 'Orange', 0.38], [0.86, 'Green', 0.3], [1, 'Green', 0]],
  },
  Orange: {
    scale: 1.6,
    stops: [[0, 'Orange', 0.56], [0.45, 'Orange', 0.46], [0.72, 'Green', 0.34], [1, 'Green', 0]],
  },
  Green: {
    scale: 1.3,
    stops: [[0, 'Green', 0.5], [0.6, 'Green', 0.36], [1, 'Green', 0]],
  },
};
const haloFor = (code) => HALO[code] || HALO.Green;
const DEFAULT_RADIUS = 120; // meters, for sample pins without a drawn zone
const MIN_RADIUS = 60;
const MAX_RADIUS = 600;

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

// Core ring radius from the size of the drawn zone: half its shorter side
function coreRadius(bounds) {
  const c = bounds.getCenter();
  const width = L.latLng(c.lat, bounds.getWest()).distanceTo(L.latLng(c.lat, bounds.getEast()));
  const height = L.latLng(bounds.getSouth(), c.lng).distanceTo(L.latLng(bounds.getNorth(), c.lng));
  return Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, Math.min(width, height) / 2));
}

// Gradient definitions used by the halos (referenced as fill="url(#pm-halo-Red)").
// Kept in a tiny off-screen SVG; display:none would stop some browsers rendering them.
function HaloGradients() {
  return (
    <svg className="pm-halo-defs" width="0" height="0" aria-hidden="true" focusable="false">
      <defs>
        {Object.entries(HALO).map(([code, halo]) => (
          <radialGradient key={code} id={`pm-halo-${code}`} cx="50%" cy="50%" r="50%">
            {halo.stops.map(([offset, sev, opacity]) => (
              <stop
                key={offset}
                offset={offset}
                stopColor={severityInfo(sev).color}
                stopOpacity={opacity}
              />
            ))}
          </radialGradient>
        ))}
      </defs>
    </svg>
  );
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

// Real hazards link to a barangay by id; sample pins only have a name
function isInBarangay(hazard, barangay) {
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
  const [basemap, setBasemap] = useState('satellite');

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
  const hazards = usingSample ? SAMPLE_HAZARDS : liveHazards;

  const barangays = useMemo(
    () => (barangayGeo?.features || []).map(featureToBarangay),
    [barangayGeo],
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

    // Zoom so the whole risk halo fills the space next to (or above) the panel
    const code = HALO[item.severity] ? item.severity : 'Green';
    const haloRadius = (item.radius || DEFAULT_RADIUS) * haloFor(code).scale;
    const bounds = L.latLng(item.position).toBounds(haloRadius * 1.1);
    map.flyToBounds(bounds, { ...panelPadding(), maxZoom: 18, duration: 0.8 });
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

  function barangayStyle(feature) {
    const selected = selectedBarangayId != null && String(featureId(feature)) === String(selectedBarangayId);
    const line = basemap === 'satellite' ? '#ffffff' : '#1c2e4a';
    return selected
      ? { className: 'pm-brgy', color: line, weight: 3, opacity: 0.95, fillColor: line, fillOpacity: 0.08 }
      : { className: 'pm-brgy', color: line, weight: 1, opacity: 0.6, fillOpacity: 0.02 };
  }

  return (
    <div className="pm">
      <HaloGradients />
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
          {BASEMAPS[basemap].layers.map((layer) => (
            <TileLayer
              key={layer.url}
              url={layer.url}
              attribution={layer.attribution}
              maxNativeZoom={19}
              maxZoom={20}
            />
          ))}
          <ZoomControl position="bottomright" />

          {/* Barangay outlines: hover for the name, click for barangay-specific hazards */}
          {barangayGeo && (
            <GeoJSON
              key={`brgy-${selectedBarangayId ?? 'none'}-${basemap}`}
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

          {/* Risk halos: gradient fill, no outline, fades out at the edge */}
          {visibleHazards.map((h) => {
            const selected = h.id === selectedHazardId;
            const code = HALO[h.severity] ? h.severity : 'Green';
            return (
              <Circle
                key={`halo-${h.id}-${selected}`}
                center={h.position}
                radius={(h.radius || DEFAULT_RADIUS) * haloFor(code).scale}
                pathOptions={{
                  stroke: false,
                  fillColor: `url(#pm-halo-${code})`,
                  fillOpacity: selected ? 1 : 0.85,
                  className: 'pm-halo',
                }}
                eventHandlers={{ click: () => selectHazard(h) }}
              />
            );
          })}

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
        </div>

        {/* ============ LEGEND ============ */}
        <div className={`pm-legend ${panelOpen ? 'is-hidden-mobile' : ''}`}>
          <p className="pm-legend-title">Risk level</p>
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