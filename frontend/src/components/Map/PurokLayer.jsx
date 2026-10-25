import React, { useEffect, useState } from 'react';
import L from 'leaflet';
import { GeoJSON, Pane, useMap } from 'react-leaflet';
import { PUROK_ATTRIBUTION, PUROK_HOVER, purokAt, purokStyle, purokTooltip } from './purokStyle';

// Over these the pointer belongs to something else (a hazard pin, its popup)
const NOT_THE_MAP = '.leaflet-marker-icon, .leaflet-popup, .leaflet-tooltip, .leaflet-control';

/**
 * The purok outlines of the selected barangay. Hovering a purok (tapping it
 * on a phone) tints it and names it.
 *
 * The lines aren't interactive: this works out which purok is under the
 * pointer instead, so the barangay underneath keeps its clicks (moving the
 * spot the panel reads) and so do field marks and the drawing tools. Its own
 * pane, under the barangay outlines (400), keeps the barangay line on top.
 */
export default function PurokLayer({ geo }) {
  const map = useMap();
  const [hovered, setHovered] = useState(null);

  useEffect(() => {
    if (!geo) return undefined;
    const box = map.getContainer();
    const tooltip = L.tooltip({ direction: 'top', offset: [0, -10], className: 'pm-purok-tip' });
    const clear = () => {
      setHovered(null);
      map.closeTooltip(tooltip);
    };
    const find = (e) => {
      if (e.target.closest?.(NOT_THE_MAP)) {
        clear();
        return;
      }
      const latlng = map.mouseEventToLatLng(e);
      const purok = purokAt(geo, latlng.lng, latlng.lat);
      if (!purok) {
        clear();
        return;
      }
      setHovered(purok);
      tooltip.setLatLng(latlng).setContent(purokTooltip(purok));
      if (!map.hasLayer(tooltip)) map.openTooltip(tooltip);
    };
    box.addEventListener('mousemove', find);
    box.addEventListener('click', find); // phones have no hover: a tap names the purok
    box.addEventListener('mouseleave', clear);
    return () => {
      box.removeEventListener('mousemove', find);
      box.removeEventListener('click', find);
      box.removeEventListener('mouseleave', clear);
      clear();
    };
  }, [map, geo]);

  if (!geo) return null;
  const barangay = geo.features[0]?.properties?.barangay;
  return (
    <Pane name="puroks" style={{ zIndex: 370, pointerEvents: 'none' }}>
      <GeoJSON
        key={`puroks-${barangay}-${geo.features.length}`}
        data={geo}
        style={purokStyle}
        interactive={false}
        attribution={PUROK_ATTRIBUTION}
      />
      {hovered && (
        <GeoJSON
          key={`purok-hover-${hovered.id ?? hovered.properties.id}`}
          data={hovered}
          style={(f) => ({ ...purokStyle(f), ...PUROK_HOVER })}
          interactive={false}
        />
      )}
    </Pane>
  );
}
