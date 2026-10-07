import client from './axiosClient';

// Wraps the three real endpoints in apps/notifications/urls.py.
// The backend scopes everything to request.user, so no email/scope params.
export const notificationsApi = {
  // GET /api/notifications/            (optionally ?unread=true)
  list: async ({ unreadOnly = false } = {}) => {
    const res = await client.get('/api/notifications/', {
      params: unreadOnly ? { unread: 'true' } : undefined,
    });
    return res.data; // array of { id, hazard_alert, content, is_read, sent_at, read_at }
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