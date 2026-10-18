import React from 'react';
import { MapContainer, TileLayer, Marker } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
// The same pin the reporter placed, so the officer reviewing the report
// sees the mark they made rather than a different-looking one.
import './css/LocationPicker.css';
import './css/ReportLocationMap.css';

const PIN = L.divIcon({
  className: '',
  html: '<div class="lp-pin"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

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
 *   zoom                  starting zoom, 16 is about one block across
 */
export default function ReportLocationMap({ latitude, longitude, zoom = 16 }) {
  const hasPin = Number.isFinite(latitude) && Number.isFinite(longitude);

  if (!hasPin) {
    return <p className="rlm-none">No pin was dropped on this report.</p>;
  }

  const position = [latitude, longitude];
  return (
    <div className="rlm">
      <div className="rlm-map">
        <MapContainer
          center={position}
          zoom={zoom}
          scrollWheelZoom={false}
          style={{ height: '100%' }}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution="&copy; OpenStreetMap contributors"
          />
          <Marker position={position} icon={PIN} interactive={false} />
        </MapContainer>
      </div>
      <p className="rlm-coords">
        Pinned at {latitude.toFixed(5)}, {longitude.toFixed(5)}
      </p>
    </div>
  );
}
