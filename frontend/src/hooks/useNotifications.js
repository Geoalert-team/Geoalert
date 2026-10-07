import { useState, useEffect, useCallback, useRef } from 'react';
import notificationsApi from '../api/notificationsApi';

/**
 * Polls the real /api/notifications/ endpoint.
 *
 * @param {object}  opts
 * @param {boolean} opts.enabled    Set false when logged out so it doesn't poll (avoids 403s).
 * @param {number}  opts.intervalMs Poll interval, default 30s.
 *
 * Returns: { notifications, unreadCount, loading, error, refresh, markRead, markAllRead }
 */
export function useNotifications({ enabled = true, intervalMs = 30000 } = {}) {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const data = await notificationsApi.list();
      if (!mounted.current) return;
      setNotifications(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err) {
      if (mounted.current) setError(err.message);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;

    if (!enabled) {
      setNotifications([]);
      setError(null);
      return () => { mounted.current = false; };
    }

    setLoading(true);
    refresh();
    const timer = setInterval(refresh, intervalMs);

    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [enabled, intervalMs, refresh]);

  // Optimistic update, rolled back by a re-fetch if the request fails.
  const markRead = useCallback(async (id) => {
    const now = new Date().toISOString();
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, is_read: true, read_at: now } : n))
    );
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
    try {
      await notificationsApi.markAllRead();
    } catch (err) {
      setError(err.message);
      refresh();
    }
  }, [refresh]);

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return { notifications, unreadCount, loading, error, refresh, markRead, markAllRead };
}

export default useNotifications;