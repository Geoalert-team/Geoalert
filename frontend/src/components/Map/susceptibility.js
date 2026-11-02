import { useEffect, useState } from 'react';

const BASE = `${process.env.PUBLIC_URL || ''}/hazard-index`;

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