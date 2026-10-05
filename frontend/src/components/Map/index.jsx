import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, useMapEvents } from 'react-leaflet';
import { barangaysApi } from '../../api/barangaysApi';
import { useHazards } from '../../hooks/useHazards';
import { severityColor } from '../../utils/severityColor';

// Talisay City, Cebu â€” used purely to center the map.
const TALISAY_CENTER = [10.2446, 123.8473];

function BboxWatcher({ onBboxChange }) {
  useMapEvents({
    moveend(e) {
      const b = e.target.getBounds();
      onBboxChange(`${b.getWest()},${b.getSouth()},${b.getEast()},${b.getNorth()}`);
    },
  });
  return null;
}

export default function Map({ onSelectHazard, refreshKey }) {
  const [barangays, setBarangays] = useState(null);
  const [bbox, setBbox] = useState(null);
  const { hazards, error } = useHazards(bbox, refreshKey);

  useEffect(() => {
    barangaysApi.list().then(setBarangays).catch(() => {});
  }, []);

  return (
    <div style={{ height: '100%', width: '100%' }}>
      {error && <div style={{ color: 'var(--sev-red)', padding: 8 }}>{error}</div>}
      <MapContainer center={TALISAY_CENTER} zoom={13} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <BboxWatcher onBboxChange={setBbox} />
        {barangays && (
          <GeoJSON
            data={barangays}
            style={{ color: '#33454A', weight: 1, fillColor: '#1F2B2E', fillOpacity: 0.3 }}
          />
        )}
        {hazards && (
          <GeoJSON
            key={JSON.stringify(hazards).length}
            data={hazards}
            style={(feature) => ({ color: severityColor(feature.properties.severity), weight: 2, fillOpacity: 0.35 })}
            onEachFeature={(feature, layer) => {
              layer.on('click', () => onSelectHazard?.(feature.properties.id));
            }}
          />
        )}
      </MapContainer>
    </div>
  );
}
