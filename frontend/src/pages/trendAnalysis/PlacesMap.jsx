import React, { useEffect, useMemo } from 'react';
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const CITY_CENTRE = [10.2447, 123.8494];
// Five navy steps, light to dark; a barangay with no events stays unshaded
export const STEPS = ['#e3eaf4', '#b6c7de', '#7f9cc4', '#4a6e9f', '#1c2e4a'];

/** The shade for a density, given the highest density on the map. */
export function shadeFor(perKm2, max) {
  if (!perKm2 || !max) return null;
  const i = Math.min(STEPS.length - 1, Math.floor((perKm2 / max) * STEPS.length));
  return STEPS[i];
}

function Fit({ data }) {
  const map = useMap();
  useEffect(() => {
    try { map.fitBounds(L.geoJSON(data).getBounds(), { padding: [12, 12] }); } catch { /* keep the view */ }
  }, [map, data]);
  return null;
}

/**
 * Barangays shaded by events per km² over the range: areas differ in size,
 * so a raw count would make big barangays look worse. Counts are in each
 * tooltip and in the table beside the map. A barangay with no outline is in
 * the table only.
 *
 * Props: rows (places answer's barangays), features (barangay GeoJSON
 * features), selected (a barangay id to outline)
 */
export default function PlacesMap({ rows, features, selected }) {
  const byId = useMemo(() => new Map(rows.map((r) => [String(r.id), r])), [rows]);
  const max = Math.max(0, ...rows.map((r) => r.per_km2 || 0));
  const data = useMemo(() => ({
    type: 'FeatureCollection',
    features: features.filter((f) => f.geometry && byId.has(String(f.id ?? f.properties?.id))),
  }), [features, byId]);
  const key = `${rows.map((r) => `${r.id}:${r.total}`).join(',')}|${selected}`;

  if (!data.features.length) return <p className="db-empty">No barangay outlines to draw.</p>;

  return (
    <div className="ta-map" role="img" aria-label="Map of barangays shaded by hazard events per square kilometre">
      <MapContainer center={CITY_CENTRE} zoom={12} scrollWheelZoom={false} style={{ height: '100%' }}>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
        <GeoJSON
          key={key}
          data={data}
          style={(f) => {
            const row = byId.get(String(f.id ?? f.properties?.id));
            const fill = shadeFor(row?.per_km2, max);
            const picked = selected && String(selected) === String(row?.id);
            return { color: picked ? '#d64545' : '#1c2e4a', weight: picked ? 3 : 1, fillColor: fill || '#ffffff',
              fillOpacity: fill ? 0.75 : 0.15 };
          }}
          onEachFeature={(f, layer) => {
            const row = byId.get(String(f.id ?? f.properties?.id));
            if (!row) return;
            const density = row.per_km2 === null ? '—' : row.per_km2.toLocaleString();
            layer.bindTooltip(`${row.name}: ${row.total.toLocaleString()} events, ${density} per km²`, { sticky: true });
          }}
        />
        <Fit data={data} />
      </MapContainer>
      <div className="ta-legend" aria-hidden="true">
        <span>Fewer for its size</span>
        {STEPS.map((c) => <i key={c} style={{ background: c }} />)}
        <span>More</span>
      </div>
    </div>
  );
}
