import { useEffect, useState } from 'react';
import { hazardsApi } from '../api/hazardsApi';

// Fetches the hazard GeoJSON for a given bbox, refetching whenever bbox or
// refreshKey changes (refreshKey is bumped after a publish/resolve action
// so the map picks up the change immediately).
export function useHazards(bbox, refreshKey) {
  const [hazards, setHazards] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    hazardsApi
      .list(bbox)
      .then((data) => {
        if (!cancelled) {
          setHazards(data);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [bbox, refreshKey]);

  return { hazards, loading, error };
}
