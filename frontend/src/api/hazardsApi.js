import client from './axiosClient';

export const hazardsApi = {
  types: () => client.get('/api/hazards/types/').then((r) => r.data),
  list: (bbox) => client.get('/api/hazards/', { params: bbox ? { bbox } : {} }).then((r) => r.data),
  detail: (id) => client.get(`/api/hazards/${id}/`).then((r) => r.data),
  create: (payload) => client.post('/api/hazards/create/', payload).then((r) => r.data),
  update: (id, payload) => client.patch(`/api/hazards/${id}/`, payload).then((r) => r.data),

  // Per-type active counts and the colour legend, for the map's layer panel (F6)
  layers: () => client.get('/api/hazards/layers/').then((r) => r.data),

  // Resolved/archived zones — /api/hazards/ only returns Active ones, so
  // anything that needs past zones (dashboard counters, history) uses this.
  resolved: (limit) =>
    client.get('/api/hazards/resolved/', { params: limit ? { limit } : {} }).then((r) => r.data),
};