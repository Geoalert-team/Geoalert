import client, { BACKGROUND } from './axiosClient';

export const rainWatchApi = {
  // The three-day rain watch. `background` marks a timed poll, which doesn't
  // keep a session alive (as hazardsApi's refresh does).
  get: ({ background } = {}) =>
    client.get('/api/rain-watch/', background ? { ...BACKGROUND } : undefined).then((r) => r.data),

  // DRRMO and admins: the manual raises, and making or cancelling one
  overrides: () => client.get('/api/rain-watch/overrides/').then((r) => r.data),
  createOverride: ({ hazard, level, endsAt, note }) =>
    client
      .post('/api/rain-watch/overrides/', { hazard, level, ends_at: endsAt, note })
      .then((r) => r.data),
  cancelOverride: (id) => client.post(`/api/rain-watch/overrides/${id}/cancel/`).then((r) => r.data),
};
