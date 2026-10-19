import React, { useEffect, useState } from 'react';
import { loadClassGrid } from './hazardLevels';
import { loadElevation, loadTerrain, readSpot } from '../../utils/terrain';
import { makeGrid } from '../../utils/gridGeometry';
import {
  ACCURACY_NOTE, describeSpot, describeSusceptibility, formatDistance, nearestNamedRiver,
} from '../../utils/spotText';

const LAYERS = ['flood', 'landslide', 'fire'];

// Susceptibility class grids, read once per index build
const classGrids = new Map(); // `${layer}@${generated}` -> Promise<grid | null>

function classGrid(index, layer) {
  if (!index?.layers?.[layer]) return Promise.resolve(null);
  const key = `${layer}@${index.generated || ''}`;
  if (!classGrids.has(key)) classGrids.set(key, loadClassGrid(index, layer).catch(() => null));
  return classGrids.get(key);
}

// Class 1-5 under [lat, lng], or 0 off the grid or without one
function classAt(grid, bounds, lat, lng) {
  if (!grid) return 0;
  const [fx, fy] = makeGrid(bounds, grid.width, grid.height).toCell(lat, lng);
  const x = Math.floor(fx);
  const y = Math.floor(fy);
  if (x < 0 || y < 0 || x >= grid.width || y >= grid.height) return 0;
  return grid.cls[y * grid.width + x];
}

/**
 * "This spot": what the ground is like where the map was tapped, in the
 * style of a Project NOAH point query. Shows nothing outside the city or
 * when the index has no elevation data (an older build), so the panel is
 * then exactly as it was.
 *
 * spot    [lat, lng] of the tap, or null
 * index   hazard-index metadata (index.json)
 * rivers  rivers.geojson, for the nearest named river
 */
export default function SpotReading({ spot, index, rivers }) {
  const [state, setState] = useState(null); // null | { loading: true } | { lines: [...] }
  const lat = spot?.[0];
  const lng = spot?.[1];

  useEffect(() => {
    if (lat == null || lng == null || !index) {
      setState(null);
      return undefined;
    }
    let current = true;
    setState({ loading: true });
    Promise.all([loadElevation(index), loadTerrain(index), ...LAYERS.map((layer) => classGrid(index, layer))])
      .then(([elevation, terrain, ...grids]) => {
        if (!current) return; // a newer tap replaced this one
        const reading = readSpot(terrain, elevation, lat, lng);
        if (!reading.inCity) {
          setState(null);
          return;
        }
        const { ground, waterway } = describeSpot(reading);
        const river = nearestNamedRiver(rivers, lat, lng);
        const classes = Object.fromEntries(LAYERS.map((layer, i) => [layer, classAt(grids[i], index.bounds, lat, lng)]));
        setState({
          lines: [
            ground && `Ground: ${ground}`,
            waterway,
            river && `Nearest named river: ${river.name}, ${formatDistance(river.distanceM)} away`,
            describeSusceptibility(classes, index.classes),
          ].filter(Boolean),
        });
      });
    return () => { current = false; };
  }, [lat, lng, index, rivers]);

  if (!state) return null;
  return (
    <section className="pm-spot" aria-live="polite">
      <h3>This spot</h3>
      {state.loading ? (
        <p>Reading the ground here…</p>
      ) : (
        <>
          {state.lines.map((line) => <p key={line}>{line}</p>)}
          <small>{ACCURACY_NOTE}</small>
        </>
      )}
    </section>
  );
}
