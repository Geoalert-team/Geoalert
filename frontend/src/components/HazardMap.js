import React, { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, useMapEvents } from 'react-leaflet';
import { api } from '../api/client';

const SEV_COLOR = { Red: '#D6483F', Orange: '#E08A3C', Green: '#4E9E6E' };
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

export default function HazardMap({ onSelectHazard, refreshKey }) {
  const [barangays, setBarangays] = useState(null);
  const [hazards, setHazards] = useState(null);
  const [bbox, setBbox] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.barangays().then(setBarangays).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    api.hazards(bbox).then(setHazards).catch((e) => setError(e.message));
  }, [bbox, refreshKey]);

  const hazardStyle = useMemo(() => (feature) => ({
    color: SEV_COLOR[feature.properties.severity] || '#7E9296',
    weight: 2,
    fillOpacity: 0.35,
  }), []);

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
            style={hazardStyle}
            onEachFeature={(feature, layer) => {
              layer.on('click', () => onSelectHazard?.(feature.properties.id));
            }}
          />
        )}
      </MapContainer>
    </div>
  );
}
