import client from './axiosClient';

// Wraps the three endpoints in apps/notifications/urls.py.
// The backend scopes everything to request.user, so no email/scope params.
export const notificationsApi = {
  // GET /api/notifications/?unread=true&limit=30
  // -> { unread_count, count, results: [{ id, hazard_alert, hazard, content,
  //                                       is_read, sent_at, read_at }] }
  // `hazard` carries { alert_id, zone_id, type, severity, barangay, status }
  // or null for a notification with no alert behind it.
  list: async ({ unreadOnly = false, limit } = {}) => {
    const params = {};
    if (unreadOnly) params.unread = 'true';
    if (limit) params.limit = limit;

    const res = await client.get('/api/notifications/', {
      params: Object.keys(params).length ? params : undefined,
    });
    return res.data;
  },

  // PATCH /api/notifications/<uuid>/read/
  markRead: async (id) => {
    const res = await client.patch(`/api/notifications/${id}/read/`);
    return res.data;
  },

  // POST /api/notifications/read-all/  -> { marked_read: <count> }
  markAllRead: async () => {
    const res = await client.post('/api/notifications/read-all/');
    return res.data;
  },
};

export default notificationsApi;