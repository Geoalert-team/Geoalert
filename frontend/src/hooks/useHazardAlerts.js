import { useState, useEffect, useCallback, useRef } from 'react';
import { hazardsApi } from '../api/hazardsApi';
import { activeAlerts } from '../utils/hazardAlerts';

/**
 * The hazard alerts a resident sees: every Active zone on the public map,
 * from the map's own feed (GET /api/hazards/). No login, so it works for
 * anyone.
 *
 * Polls like useNotifications: every 30s while the tab is visible, and once
 * when the tab comes back. The request is a background one with the map's
 * ETag, so an unchanged map costs the server nothing.
 *
 * Returns alerts (worst first), or null until the first load succeeds, so a
 * failed request is never mistaken for "no alerts".
 */
export function useHazardAlerts({ enabled = true, intervalMs = 30000 } = {}) {
  const [alerts, setAlerts] = useState(null);
  const tag = useRef(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const { data, etag } = await hazardsApi.listTagged();
      if (!mounted.current || (etag && etag === tag.current)) return;
      tag.current = etag;
      setAlerts(activeAlerts(data));
    } catch {
      // A failed refresh keeps the alerts already shown
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    if (!enabled) return () => { mounted.current = false; };

    refresh();
    const timer = setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      refresh();
    }, intervalMs);
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      mounted.current = false;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [enabled, intervalMs, refresh]);

  return alerts;
}
