/**
 * Safety cordons on the map, hatched in the colour of their hazard.
 *
 * A cordon is an instruction (keep clear of this ring), not a hazard level.
 * It used to be shaded one level below its hazard, so an Extreme fire's
 * ring was the same orange as a Moderate flood next to it, and only a
 * dashed line a viewer could switch off told them apart. Here it keeps its
 * hazard's colour, so the ring visibly belongs to the hazard, and texture
 * rather than colour says "cordon". Hatching also reads without colour
 * vision.
 *
 * The ring is `cordon_ring` from the server: the routed cordon less the
 * hazard, so the hatch never covers the hazard's own shading. It is drawn
 * as SVG, not in the hazard-level raster: a 10-100 m ring is only a few
 * raster cells wide, and the stripes here stay the same width at every
 * zoom. Always drawn, whatever the "Zone outlines" setting: residents need
 * to see where they are told to leave.
 *
 * The stripe patterns live in <CordonPatterns />, rendered once on the
 * page; a path's fill can point at a pattern in another inline SVG of the
 * same document.
 */

import { useMemo } from 'react';
import { GeoJSON, Pane } from 'react-leaflet';
import { SEVERITY, severityInfo } from './hazardInfo';

// The officer's draft while previewing a publish, same green as its outline
export const DRAFT_COLOR = '#0b6b3a';
// The legend shows the texture; its text says the colour follows the hazard
const LEGEND_COLOR = '#1c2e4a';

const PATTERN_COLORS = {
  ...Object.fromEntries(Object.entries(SEVERITY).map(([code, s]) => [code, s.color])),
  Other: severityInfo(null).color,
  Draft: DRAFT_COLOR,
  Legend: LEGEND_COLOR,
};

const patternKey = (severity) => (SEVERITY[severity] ? severity : 'Other');

/** The fill that hatches an area: 'Red', 'Orange', 'Green', 'Draft' or 'Legend'. */
export const cordonFill = (key) => `url(#gx-cordon-${PATTERN_COLORS[key] ? key : 'Other'})`;

/** Leaflet path options for a hatched cordon ring. */
export function cordonRingStyle(key, color) {
  return {
    color,
    weight: 2,
    opacity: 0.9,
    dashArray: '6 5',
    fillColor: cordonFill(key),
    fillOpacity: 1,
  };
}

/**
 * The stripe patterns, in an SVG that takes no space. Not display:none:
 * some browsers don't paint patterns defined inside a hidden SVG.
 */
export function CordonPatterns() {
  return (
    <svg className="gx-cordon-defs" width="0" height="0" aria-hidden="true" focusable="false">
      <defs>
        {Object.entries(PATTERN_COLORS).map(([key, color]) => (
          <pattern
            key={key}
            id={`gx-cordon-${key}`}
            patternUnits="userSpaceOnUse"
            width="8"
            height="8"
            patternTransform="rotate(45)"
          >
            <rect width="8" height="8" fill={color} fillOpacity="0.1" />
            {/* Off the tile edge, so the stroke isn't cut in half */}
            <line x1="2" y1="0" x2="2" y2="8" stroke={color} strokeWidth="2.5" strokeOpacity="0.8" />
          </pattern>
        ))}
      </defs>
    </svg>
  );
}

/** True when any of these hazards has a cordon to draw. */
export const hasCordon = (hazards) => hazards.some((h) => h.feature?.properties?.cordon_m);

/**
 * Every visible cordon. `hazards` are the map's items, each with the
 * GeoJSON feature it came from.
 */
export default function CordonLayer({ hazards }) {
  const data = useMemo(() => {
    const features = [];
    hazards.forEach((h) => {
      const p = h.feature?.properties;
      if (!p?.cordon_m) return;
      // A response cached from before cordon_ring existed has only the
      // whole cordon: outline it rather than hatch over the hazard.
      const geometry = p.cordon_ring || p.cordon;
      if (!geometry) return;
      features.push({
        type: 'Feature',
        properties: { severity: p.severity, ring: Boolean(p.cordon_ring) },
        geometry,
      });
    });
    return features.length ? { type: 'FeatureCollection', features } : null;
  }, [hazards]);

  // react-leaflet's GeoJSON only reads its data once, so remount it when the set changes
  const key = useMemo(
    () => hazards
      .filter((h) => h.feature?.properties?.cordon_m)
      .map((h) => `${h.id}:${h.severity}:${h.feature.properties.cordon_m}:${Boolean(h.feature.properties.cordon_ring)}`)
      .join('|'),
    [hazards],
  );

  if (!data) return null;
  return (
    // Above the hazard shading (350), below street names (450) and the
    // zone outlines in the overlay pane (400)
    <Pane name="cordons" style={{ zIndex: 360 }}>
      <GeoJSON
        key={key}
        data={data}
        interactive={false}
        style={(f) => {
          const { severity, ring } = f.properties || {};
          const color = severityInfo(severity).color;
          return ring
            ? cordonRingStyle(patternKey(severity), color)
            : { color, weight: 2, opacity: 0.9, dashArray: '6 5', fill: false };
        }}
      />
    </Pane>
  );
}
