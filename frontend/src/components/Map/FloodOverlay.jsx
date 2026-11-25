import React, { useMemo } from 'react';
import { GeoJSON, Pane } from 'react-leaflet';
import { floodOverlayFeatures, floodOverlayStyle } from './floodMarks';
import { overlayInput } from '../Forecast/forecastLevels';

/**
 * "Likely by month" with Flood ticked: grey, dashed areas the flood model has
 * not assessed, and a dashed outline on areas whose level is uncertain. Not
 * interactive; it sits above the purok fills.
 *
 * geo     every purok outline (/api/barangays/puroks/)
 * levels  purokLikelyLevels() of the forecast response
 * types   the ticked predicted hazards: an area with another ticked hazard's colour is never greyed
 * hazard  'Flood' (default) or 'Landslide': whose rows to mark
 */
export default function FloodOverlay({ geo, levels, types = ['Flood'], hazard = 'Flood' }) {
  const marked = useMemo(() => {
    const input = overlayInput(levels, hazard, types);
    return floodOverlayFeatures(geo, input.levels, input.types);
  }, [geo, levels, types, hazard]);
  if (!marked) return null;
  // react-leaflet's GeoJSON only reads its data once: remount when the marks change
  const key = marked.features.map((f) => `${f.id ?? f.properties.id}:${f.properties.flood}`).join('|');
  return (
    <Pane name={`${hazard.toLowerCase()}-marks`} style={{ zIndex: hazard === 'Landslide' ? 366 : 365, pointerEvents: 'none' }}>
      <GeoJSON key={`${hazard}:${key}`} data={marked} style={floodOverlayStyle} interactive={false} />
    </Pane>
  );
}
