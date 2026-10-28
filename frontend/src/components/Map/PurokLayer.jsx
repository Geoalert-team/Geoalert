import React from 'react';
import { GeoJSON, Pane } from 'react-leaflet';
import { PUROK_ATTRIBUTION, PUROK_HOVER, PUROK_SELECTED, purokStyle, purokTooltip } from './purokStyle';
import usePurokHover from './usePurokHover';

const idOf = (f) => f?.id ?? f?.properties?.id;

/**
 * The purok outlines of the selected barangay. Hovering a purok (tapping it
 * on a phone) tints it and names it, with tooltipFor's text. The purok the
 * panel shows (selectedId) is drawn bold.
 *
 * The lines aren't interactive (see usePurokHover). Their own pane, under
 * the barangay outlines (400), keeps the barangay line on top.
 */
export default function PurokLayer({ geo, selectedId = null, tooltipFor = purokTooltip }) {
  const hovered = usePurokHover(geo, tooltipFor);

  if (!geo) return null;
  const barangay = geo.features[0]?.properties?.barangay;
  const selected = selectedId == null ? null : geo.features.find((f) => String(idOf(f)) === String(selectedId));
  return (
    <Pane name="puroks" style={{ zIndex: 370, pointerEvents: 'none' }}>
      <GeoJSON
        key={`puroks-${barangay}-${geo.features.length}`}
        data={geo}
        style={purokStyle}
        interactive={false}
        attribution={PUROK_ATTRIBUTION}
      />
      {selected && (
        <GeoJSON
          key={`purok-selected-${idOf(selected)}`}
          data={selected}
          style={(f) => ({ ...purokStyle(f), ...PUROK_SELECTED })}
          interactive={false}
        />
      )}
      {hovered && (
        <GeoJSON
          key={`purok-hover-${idOf(hovered)}`}
          data={hovered}
          style={(f) => ({ ...purokStyle(f), ...PUROK_HOVER })}
          interactive={false}
        />
      )}
    </Pane>
  );
}
