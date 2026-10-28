import React, { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
// The same pin the reporter placed, so the officer reviewing the report
// sees the mark they made rather than a different-looking one.
import './css/LocationPicker.css';
import './css/ReportLocationMap.css';

const CITY_CENTRE = [10.2447, 123.8494];

const PIN = L.divIcon({
  className: '',
  html: '<div class="lp-pin"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

// Frames the puroks named, and the pin with them when there is one
function FitTo({ data, lat, lng }) {
  const map = useMap();
  useEffect(() => {
    if (!data) return;
    try {
      const bounds = L.geoJSON(data).getBounds();
      if (lat != null) bounds.extend([lat, lng]);
      map.fitBounds(bounds, { padding: [16, 16], maxZoom: 17 });
    } catch { /* keep the view */ }
  }, [data, lat, lng, map]);
  return null;
}

/**
 * Where a report said the hazard was, read only.
 *
 * The pin is optional on a report, so this says so plainly when there
 * isn't one: an officer deciding whether to validate needs to tell
 * "nobody marked a spot" apart from "the map failed to load".
 *
 * Panning and zooming are left on — an officer judging a flood report
 * wants to see which street it sits on — but there is nothing to click
 * and no way to move the pin. Scroll-wheel zoom is off so the page
 * doesn't trap the wheel inside a small map in a modal.
 *
 * Props:
 *   latitude, longitude   numbers, or null/undefined when no pin was dropped
 *   puroks                the outlines of the puroks the report names
 *                         (GeoJSON features), drawn and framed with the pin
 *   zoom                  starting zoom, 16 is about one block across
 */
export default function ReportLocationMap({ latitude, longitude, puroks = [], zoom = 16 }) {
  const hasPin = Number.isFinite(latitude) && Number.isFinite(longitude);
  const outlines = useMemo(
    () => (puroks.length ? { type: 'FeatureCollection', features: puroks } : null),
    [puroks],
  );
  const outlineKey = puroks.map((f) => f.id).join(',');

  if (!hasPin && !outlines) {
    return <p className="rlm-none">No pin was dropped on this report.</p>;
  }

  const outlined = puroks.length === 1 ? 'The red outline is the purok it names.' : 'The red outlines are the puroks it names.';
  return (
    <div className="rlm">
      <div className="rlm-map">
        <MapContainer
          center={hasPin ? [latitude, longitude] : CITY_CENTRE}
          zoom={zoom}
          scrollWheelZoom={false}
          style={{ height: '100%' }}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution="&copy; OpenStreetMap contributors"
          />
          {outlines && (
            <GeoJSON
              key={outlineKey}
              data={outlines}
              interactive={false}
              style={{ color: '#d64545', weight: 2, fillOpacity: 0.12 }}
            />
          )}
          {hasPin && <Marker position={[latitude, longitude]} icon={PIN} interactive={false} />}
          <FitTo data={outlines} lat={hasPin ? latitude : null} lng={hasPin ? longitude : null} />
        </MapContainer>
      </div>
      <p className="rlm-coords">
        {hasPin ? `Pinned at ${latitude.toFixed(5)}, ${longitude.toFixed(5)}.` : 'No pin was dropped.'}
        {outlines && ` ${outlined}`}
      </p>
    </div>
  );
}
