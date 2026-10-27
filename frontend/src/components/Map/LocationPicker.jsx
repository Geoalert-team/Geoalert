import React, { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './css/LocationPicker.css';

// Middle of Talisay City, for when no barangay outline is known
const CITY_CENTRE = [10.2447, 123.8494];

const PIN = L.divIcon({
  className: '',
  html: '<div class="lp-pin"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

function ClickToPlace({ onPick }) {
  useMapEvents({ click: (e) => onPick([e.latlng.lat, e.latlng.lng]) });
  return null;
}

// Keeps the view on the chosen puroks, else the barangay, when they change
function FitTo({ data }) {
  const map = useMap();
  useEffect(() => {
    if (!data) return;
    try { map.fitBounds(L.geoJSON(data).getBounds(), { padding: [12, 12], maxZoom: 17 }); } catch { /* keep the view */ }
  }, [data, map]);
  return null;
}

/**
 * A small map for dropping one pin where a hazard was seen. Optional on a
 * report: when several reports of one event carry a pin, DRRMO can draw the
 * zone around them instead of guessing the edge.
 *
 * Props:
 *   value      [lat, lng] or null
 *   onChange   (value | null) => void
 *   barangay   GeoJSON feature of the barangay to show and centre on, or null
 *   puroks     the chosen puroks' GeoJSON features, outlined and framed
 *              ahead of the barangay
 */
export default function LocationPicker({ value, onChange, barangay = null, puroks = [] }) {
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState('');
  const outline = useMemo(() => (barangay?.geometry ? barangay : null), [barangay]);
  const chosen = useMemo(
    () => (puroks.length ? { type: 'FeatureCollection', features: puroks } : null),
    [puroks],
  );
  const chosenKey = puroks.map((f) => f.id).join(',');

  function useMyLocation() {
    if (!navigator.geolocation) {
      setGeoError('This device cannot share its location.');
      return;
    }
    setLocating(true);
    setGeoError('');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        onChange([pos.coords.latitude, pos.coords.longitude]);
      },
      () => {
        setLocating(false);
        setGeoError('Could not get your location. Tap the map instead.');
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  return (
    <div className="lp">
      <div className="lp-map">
        <MapContainer center={value || CITY_CENTRE} zoom={15} scrollWheelZoom={false} style={{ height: '100%' }}>
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution="&copy; OpenStreetMap contributors"
          />
          {outline && (
            <GeoJSON
              key={String(outline.id ?? outline.properties?.id)}
              data={outline}
              interactive={false}
              style={{ color: '#1c2e4a', weight: 2, fillOpacity: 0.04 }}
            />
          )}
          {chosen && (
            <GeoJSON
              key={`p-${chosenKey}`}
              data={chosen}
              interactive={false}
              style={{ color: '#d64545', weight: 2, fillOpacity: 0.12 }}
            />
          )}
          {!value && <FitTo data={chosen || outline} />}
          {value && <Marker position={value} icon={PIN} interactive={false} />}
          <ClickToPlace onPick={onChange} />
        </MapContainer>
      </div>
      <div className="lp-actions">
        <button type="button" className="lp-btn" onClick={useMyLocation} disabled={locating}>
          {locating ? 'Finding you…' : 'Use my location'}
        </button>
        {value && (
          <button type="button" className="lp-btn" onClick={() => onChange(null)}>Remove pin</button>
        )}
        <span className="lp-status">
          {value ? `Pinned at ${value[0].toFixed(5)}, ${value[1].toFixed(5)}` : 'Tap the map where you saw it.'}
        </span>
      </div>
      {geoError && <p className="lp-error" role="alert">{geoError}</p>}
    </div>
  );
}
