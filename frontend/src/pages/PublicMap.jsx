import React, { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, ZoomControl } from 'react-leaflet';
import L from 'leaflet';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import HazardPanel from '../components/Map/HazardPanel';
import { HAZARD_TYPES, SEVERITY, severityInfo, hazardKey, hazardIconPath } from '../components/Map/hazardInfo';
import { hazardsApi } from '../api/hazardsApi';
import { barangaysApi } from '../api/barangaysApi';
import { SAMPLE_HAZARDS, SHOW_SAMPLE_DATA } from '../data/sampleHazards';
import './css/PublicMap.css';

// Talisay City, Cebu
const TALISAY_CENTER = [10.2446, 123.8473];
const PANEL_WIDTH = 400; // keep in sync with .pm-panel width in PublicMap.css

/* ---------- Helpers ---------- */

// Turns one GeoJSON feature from /api/hazards/ into the shape this page uses
function featureToItem(feature) {
  const p = feature.properties || {};
  let center;
  try {
    center = L.geoJSON(feature).getBounds().getCenter();
  } catch {
    return null; // skip hazards without a valid shape
  }
  return {
    id: feature.id ?? p.id,
    location: p.barangay_name || p.location_name || `${p.hazard_type_name || 'Hazard'} zone`,
    type: p.hazard_type_name || 'Hazard',
    severity: p.severity,
    status: p.status,
    description: p.description,
    activatedAt: p.activated_at,
    position: [center.lat, center.lng],
    feature,
  };
}

// Round pin with the hazard icon, colored by severity
function pinIcon(item, selected) {
  const sev = severityInfo(item.severity);
  const classes = ['pm-pin', selected ? 'is-selected' : '', item.severity === 'Red' ? 'is-high' : '']
    .join(' ')
    .trim();
  return L.divIcon({
    className: 'pm-pin-wrap',
    html: `<span class="${classes}" style="--pin:${sev.color}">
             <svg viewBox="0 0 24 24" aria-hidden="true"><path d="${hazardIconPath(item.type)}"/></svg>
           </span>`,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });
}

/* ---------- Page ---------- */

export default function PublicMap() {
  const [map, setMap] = useState(null);
  const [liveHazards, setLiveHazards] = useState([]);
  const [barangays, setBarangays] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  const [typeFilter, setTypeFilter] = useState('All');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);

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

    barangaysApi.list().then(setBarangays).catch(() => {});
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

  const visibleHazards = useMemo(
    () => hazards.filter((h) => typeFilter === 'All' || hazardKey(h.type) === typeFilter),
    [hazards, typeFilter],
  );

  const searchResults = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return hazards.filter((h) => `${h.location} ${h.type}`.toLowerCase().includes(q));
  }, [hazards, query]);

  const selected = hazards.find((h) => h.id === selectedId) || null;

  // Zoom the map to fit all pins once, after they first load
  const hasFitted = useRef(false);
  useEffect(() => {
    if (!map || loading || hasFitted.current || hazards.length === 0) return;
    hasFitted.current = true;
    const bounds = L.latLngBounds(hazards.map((h) => h.position));
    map.fitBounds(bounds, { padding: [120, 120], maxZoom: 15 });
  }, [map, loading, hazards]);

  function selectHazard(item) {
    setSelectedId(item.id);
    setPanelOpen(true);
    setQuery('');
    if (!map) return;

    // Center the pin in the space next to the panel (desktop) or above it (mobile)
    const zoom = Math.max(map.getZoom(), 15);
    const isDesktop = window.innerWidth > 860;
    const offset = isDesktop ? L.point(-PANEL_WIDTH / 2, 0) : L.point(0, map.getSize().y * 0.25);
    const target = map.unproject(map.project(item.position, zoom).add(offset), zoom);
    map.flyTo(target, zoom, { duration: 0.8 });
  }

  function handleSearchKey(e) {
    if (e.key === 'Enter' && searchResults.length > 0) selectHazard(searchResults[0]);
  }

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
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <ZoomControl position="bottomright" />

          {barangays && (
            <GeoJSON
              data={barangays}
              style={{ color: '#1c2e4a', weight: 1, opacity: 0.5, fillOpacity: 0.02 }}
              interactive={false}
            />
          )}

          {/* Real hazard zones are shaded lightly under their pins */}
          {visibleHazards
            .filter((h) => h.feature)
            .map((h) => (
              <GeoJSON
                key={`zone-${h.id}-${h.id === selectedId}`}
                data={h.feature}
                style={{ color: severityInfo(h.severity).color, weight: 2, fillOpacity: h.id === selectedId ? 0.3 : 0.15 }}
                eventHandlers={{ click: () => selectHazard(h) }}
              />
            ))}

          {visibleHazards.map((h) => (
            <Marker
              key={h.id}
              position={h.position}
              icon={pinIcon(h, h.id === selectedId)}
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
                  <li className="pm-results-empty">No hazards match "{query.trim()}".</li>
                )}
                {searchResults.map((h) => {
                  const sev = severityInfo(h.severity);
                  return (
                    <li key={h.id}>
                      <button type="button" onClick={() => selectHazard(h)}>
                        <span className="pm-results-dot" style={{ background: sev.color }} />
                        <span>
                          <strong>{h.location}</strong>
                          <small>{h.type}, {sev.label.toLowerCase()}</small>
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
        </div>

        {/* ============ DETAILS PANEL ============ */}
        <HazardPanel item={selected} open={panelOpen && !!selected} onClose={() => setPanelOpen(false)} />
      </div>
    </div>
  );
}