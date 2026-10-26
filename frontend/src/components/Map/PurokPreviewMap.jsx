import React, { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './css/LocationPicker.css';

const CITY_CENTRE = [10.2447, 123.8494];

const PIN = L.divIcon({
  className: '',
  html: '<div class="lp-pin"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

// Frames the chosen puroks, or the barangay before any is chosen
function FitTo({ data }) {
  const map = useMap();
  useEffect(() => {
    if (!data) return;
    try { map.fitBounds(L.geoJSON(data).getBounds(), { padding: [16, 16], maxZoom: 17 }); } catch { /* keep the view */ }
  }, [data, map]);
  return null;
}

/**
 * Where a fire report says the fire is: the barangay's outline, each chosen
 * purok outlined, and a pin at a point inside each. A preview only. The
 * reporter picks puroks from the list, not by tapping, so clicks do nothing.
 *
 *   barangay  the barangay's GeoJSON feature, or null
 *   puroks    the chosen puroks' GeoJSON features
 *   pins      [{ id, name, lat, lng }] from purokPins()
 */
export default function PurokPreviewMap({ barangay = null, puroks = [], pins = [] }) {
  const chosen = useMemo(
    () => (puroks.length ? { type: 'FeatureCollection', features: puroks } : null),
    [puroks],
  );
  const chosenKey = puroks.map((f) => f.id).join(',');

  return (
    <div className="lp">
      <div className="lp-map" style={{ cursor: 'default' }}>
        <MapContainer center={CITY_CENTRE} zoom={15} scrollWheelZoom={false} style={{ height: '100%', cursor: 'default' }}>
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution="&copy; OpenStreetMap contributors"
          />
          {barangay?.geometry && (
            <GeoJSON
              key={`b-${barangay.id ?? barangay.properties?.id}`}
              data={barangay}
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
          {pins.filter((p) => p.lat != null && p.lng != null).map((p) => (
            <Marker key={p.id} position={[p.lat, p.lng]} icon={PIN} interactive={false} title={p.name} />
          ))}
          <FitTo data={chosen || (barangay?.geometry ? barangay : null)} />
        </MapContainer>
      </div>
      <span className="lp-status">
        {pins.length ? 'The pins show the puroks you chose.' : 'Choose a purok and its pin shows here.'}
      </span>
    </div>
  );
}
