import client from './axiosClient';

export const hazardsApi = {
  types: () => client.get('/api/hazards/types/').then((r) => r.data),
  list: (bbox) => client.get('/api/hazards/', { params: bbox ? { bbox } : {} }).then((r) => r.data),
  detail: (id) => client.get(`/api/hazards/${id}/`).then((r) => r.data),
  create: (payload) => client.post('/api/hazards/create/', payload).then((r) => r.data),

  // What a publish would do, without doing it: the clipped shape, the
  // barangays and number of accounts it reaches, overlapping zones of the
  // same type, and whether it needs a second officer. Saves nothing.
  preview: (payload) => client.post('/api/hazards/preview/', payload).then((r) => r.data),

  // Extreme alerts waiting for a second officer, and approving one (sends it).
  // To refuse one, withdraw it with retract() and a reason.
  awaiting: () => client.get('/api/hazards/awaiting/').then((r) => r.data),
  approve: (id) => client.post(`/api/hazards/${id}/approve/`).then((r) => r.data),
  update: (id, payload) => client.patch(`/api/hazards/${id}/`, payload).then((r) => r.data),

  // Ground confirmation from the barangay: status is 'Confirmed' or 'Disputed'.
  // Only Barangay Personnel may call this, and only for their own barangay.
  verify: (id, { status, note }) =>
    client.post(`/api/hazards/${id}/verify/`, { status, note }).then((r) => r.data),

  // Active zones touching the signed-in user's barangay, for the barangay
  // dashboard. ?pending=true narrows to the ones nobody has answered yet.
  forBarangay: (params) =>
    client.get('/api/hazards/for-barangay/', { params }).then((r) => r.data),

  // Per-type active counts and the colour legend, for the map's layer panel (F6)
  layers: () => client.get('/api/hazards/layers/').then((r) => r.data),

  // Resolved/archived zones — /api/hazards/ only returns Active ones, so
  // anything that needs past zones (dashboard counters, history) uses this.
  resolved: (limit) =>
    client.get('/api/hazards/resolved/', { params: limit ? { limit } : {} }).then((r) => r.data),

  // Withdraw a zone published in error. Not the same call as resolving:
  // resolving files a historical record, which would invent an incident that
  // never happened. A reason is required and goes out to everyone who
  // received the original alert. DRRMO only.
  retract: (id, reason) =>
    client.post(`/api/hazards/${id}/retract/`, { reason }).then((r) => r.data),

  // Withdrawn zones, for the DRRMO accountability list. They are off the
  // public map and out of the reports, so this is the only place they show.
  retracted: (limit) =>
    client.get('/api/hazards/retracted/', { params: limit ? { limit } : {} }).then((r) => r.data),
};