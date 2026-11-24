import React, { useMemo } from 'react';
import { GeoJSON, Pane } from 'react-leaflet';
import { floodOverlayFeatures, floodOverlayStyle } from './floodMarks';

/**
 * "Likely by month" with Flood ticked: grey, dashed areas the flood model has
 * not assessed, and a dashed outline on areas whose level is uncertain. Not
 * interactive; it sits above the purok fills.
 *
 * geo     every purok outline (/api/barangays/puroks/)
 * levels  purokLikelyLevels() of the forecast response
 * types   the ticked predicted hazards: with Fire, a fire colour is never greyed
 */
export default function FloodOverlay({ geo, levels, types = ['Flood'] }) {
  const marked = useMemo(() => floodOverlayFeatures(geo, levels, types), [geo, levels, types]);
  if (!marked) return null;
  // react-leaflet's GeoJSON only reads its data once: remount when the marks change
  const key = marked.features.map((f) => `${f.id ?? f.properties.id}:${f.properties.flood}`).join('|');
  return (
    <Pane name="flood-marks" style={{ zIndex: 365, pointerEvents: 'none' }}>
      <GeoJSON key={key} data={marked} style={floodOverlayStyle} interactive={false} />
    </Pane>
  );
}
