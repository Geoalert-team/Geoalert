import { useEffect, useState } from 'react';
import L from 'leaflet';
import { useMap } from 'react-leaflet';
import { purokAt } from './purokStyle';

// Over these the pointer belongs to something else (a hazard pin, its popup)
const NOT_THE_MAP = '.leaflet-marker-icon, .leaflet-popup, .leaflet-tooltip, .leaflet-control';

/**
 * The purok of `geo` under the pointer, named in a tooltip by
 * tooltipFor(feature). The outlines and fills aren't interactive: this
 * works out which purok is under the pointer instead, so the barangay
 * underneath keeps its clicks (moving the spot the panel reads) and so do
 * the drawing tools. A tap names the purok on a phone, which has no hover.
 */
export default function usePurokHover(geo, tooltipFor) {
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
      tooltip.setLatLng(latlng).setContent(tooltipFor(purok));
      if (!map.hasLayer(tooltip)) map.openTooltip(tooltip);
    };
    box.addEventListener('mousemove', find);
    box.addEventListener('click', find);
    box.addEventListener('mouseleave', clear);
    return () => {
      box.removeEventListener('mousemove', find);
      box.removeEventListener('click', find);
      box.removeEventListener('mouseleave', clear);
      clear();
    };
  }, [map, geo, tooltipFor]);

  return hovered;
}
