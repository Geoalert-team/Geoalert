import { useEffect, useState } from 'react';

const BASE = `${process.env.PUBLIC_URL || ''}/hazard-index`;

// Five classes, lowest first. index.json carries the same list; this is the fallback.
export const SUSCEPTIBILITY_CLASSES = [
  { key: 'very-low', label: 'Very low', color: '#a8a8a8' },
  { key: 'low', label: 'Low', color: '#ffb100' },
  { key: 'medium', label: 'Medium', color: '#8fe800' },
  { key: 'high', label: 'High', color: '#1f3cff' },
  { key: 'very-high', label: 'Very high', color: '#ff0000' },
];

// Which layer each filter chip shows
export const LAYER_FOR_FILTER = { All: 'all', Flood: 'flood', Landslide: 'landslide', Fire: 'fire' };

export const LAYER_TITLE = {
  all: 'Highest susceptibility, any hazard',
  flood: 'Flood susceptibility',
  landslide: 'Landslide susceptibility',
  fire: 'Fire susceptibility',
};

export function layerUrl(index, key) {
  const file = index?.layers?.[key];
  return file ? `${BASE}/${file}?v=${encodeURIComponent(index.generated || '')}` : null;
}

// { status: 'loading' | 'ready' | 'missing', index, rivers }
export function useSusceptibility() {
  const [state, setState] = useState({ status: 'loading', index: null, rivers: null });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const res = await fetch(`${BASE}/index.json`, { cache: 'no-cache' });
        // The dev server answers unknown paths with index.html, so json() fails when the file is missing
        const index = await res.json();
        let rivers = null;
        try {
          const r = await fetch(`${BASE}/${index.rivers}?v=${encodeURIComponent(index.generated || '')}`);
          if (r.ok) rivers = await r.json();
        } catch {
          rivers = null;
        }
        if (!cancelled) setState({ status: 'ready', index, rivers });
      } catch {
        if (!cancelled) setState({ status: 'missing', index: null, rivers: null });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}