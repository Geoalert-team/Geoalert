import { useState, useEffect, useCallback, useRef } from 'react';
import notificationsApi from '../api/notificationsApi';

/**
 * Polls the real /api/notifications/ endpoint.
 *
 * @param {object}  opts
 * @param {boolean} opts.enabled    Set false when logged out so it doesn't poll (avoids 403s).
 * @param {number}  opts.intervalMs Poll interval, default 30s.
 * @param {number}  opts.limit      How many rows to fetch, default 30.
 *
 * Returns: { notifications, unreadCount, loading, error, refresh, markRead, markAllRead }
 *
 * unreadCount comes from the server, not from counting the fetched rows —
 * the endpoint only returns the most recent `limit` notifications, so a
 * local count would stop rising once the user had more unread than that.
 */
export function useNotifications({ enabled = true, intervalMs = 30000, limit = 30 } = {}) {
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const data = await notificationsApi.list({ limit });
      if (!mounted.current) return;
      setNotifications(Array.isArray(data?.results) ? data.results : []);
      setUnreadCount(Number(data?.unread_count) || 0);
      setError(null);
    } catch (err) {
      if (mounted.current) setError(err.message);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    mounted.current = true;

    if (!enabled) {
      setNotifications([]);
      setUnreadCount(0);
      setError(null);
      return () => { mounted.current = false; };
    }

    setLoading(true);
    refresh();

    const timer = setInterval(() => {
      // A backgrounded tab doesn't need to keep hitting the API; the next
      // visible tick catches up. Saves a poll every 30s per open tab.
      if (document.visibilityState === 'hidden') return;
      refresh();
    }, intervalMs);

    // Catch up immediately when the user comes back to the tab
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

  // Optimistic update, corrected by a re-fetch if the request fails.
  const markRead = useCallback(async (id) => {
    const now = new Date().toISOString();
    let wasUnread = false;

    setNotifications((prev) =>
      prev.map((n) => {
        if (n.id !== id) return n;
        if (!n.is_read) wasUnread = true;
        return { ...n, is_read: true, read_at: now };
      })
    );
    if (wasUnread) setUnreadCount((c) => Math.max(0, c - 1));

    try {
      await notificationsApi.markRead(id);
    } catch (err) {
      setError(err.message);
      refresh();
    }
  }, [refresh]);

  const markAllRead = useCallback(async () => {
    const now = new Date().toISOString();
    setNotifications((prev) =>
      prev.map((n) => (n.is_read ? n : { ...n, is_read: true, read_at: now }))
    );
    setUnreadCount(0);

    try {
      await notificationsApi.markAllRead();
    } catch (err) {
      setError(err.message);
      refresh();
    }
  }, [refresh]);

  return { notifications, unreadCount, loading, error, refresh, markRead, markAllRead };
}

export default useNotifications;