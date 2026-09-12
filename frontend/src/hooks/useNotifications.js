import { useEffect, useState } from 'react';
import { reportsApi } from '../api/mockApi';

// Stand-in for apps/notifications, which has no backend yet. Polls the
// mock incident-report list on an interval and reports how many are
// still pending, scoped either to everyone (DRRMO/Admin badge) or just
// the current user's own submissions (Barangay Personnel badge).
export function useNotifications({ scope = 'all', email = null, intervalMs = 30000 } = {}) {
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    let active = true;

    async function poll() {
      const reports = await reportsApi.list();
      const pending = reports.filter((r) => r.status === 'Pending');
      const count = scope === 'mine' ? pending.filter((r) => r.reported_by === email).length : pending.length;
      if (active) setPendingCount(count);
    }

    poll();
    const id = setInterval(poll, intervalMs);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [scope, email, intervalMs]);

  return { pendingCount };
}
