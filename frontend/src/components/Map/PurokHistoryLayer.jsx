import React, { useMemo } from 'react';
import { GeoJSON, Pane } from 'react-leaflet';
import { filledPuroks, purokFillStyle } from './purokLevels';
import usePurokHover from './usePurokHover';

/**
 * Past hazards, citywide: every purok with a level for the ticked types is
 * filled in its colour (purokLevels.js), at every zoom, under the purok and
 * barangay lines. Hovering a filled purok names it with its counts.
 *
 * geo           every purok outline (/api/barangays/puroks/)
 * levels        byPurok() of /api/history/purok-levels/
 * types         the hazard types ticked in Layers
 * tooltipFor    the hover text for a purok
 * skipBarangay  the barangay whose own puroks PurokLayer is naming, so a
 *               purok there gets one tooltip, not two
 */
export default function PurokHistoryLayer({ geo, levels, types, tooltipFor, skipBarangay = null }) {
  const filled = useMemo(() => filledPuroks(geo, levels, types), [geo, levels, types]);
  const hoverable = useMemo(() => {
    if (!filled || skipBarangay == null) return filled;
    const features = filled.features.filter((f) => String(f.properties?.barangay) !== String(skipBarangay));
    return features.length ? { type: 'FeatureCollection', features } : null;
  }, [filled, skipBarangay]);
  // Its tooltip names the barangay too, so the barangay's own steps aside (PublicMap.css)
  usePurokHover(hoverable, tooltipFor, 'pm-on-past-purok');

  if (!filled) return null;
  // react-leaflet's GeoJSON only reads its data once: remount when the fills change
  const key = filled.features.map((f) => `${f.id ?? f.properties.id}:${f.properties.level}`).join('|');
  return (
    <Pane name="purok-fills" style={{ zIndex: 360, pointerEvents: 'none' }}>
      <GeoJSON key={key} data={filled} style={purokFillStyle} interactive={false} />
    </Pane>
  );
}
