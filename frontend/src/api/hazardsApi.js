import client, { BACKGROUND } from './axiosClient';

export const hazardsApi = {
  types: () => client.get('/api/hazards/types/').then((r) => r.data),
  list: (bbox) => client.get('/api/hazards/', { params: bbox ? { bbox } : {} }).then((r) => r.data),
  // The map's timed refresh: a background request (doesn't keep a session
  // alive), with the ETag so the map can skip a refresh that found nothing new.
  // The browser revalidates with If-None-Match, so an unchanged map costs the
  // server no queries.
  listTagged: () =>
    client.get('/api/hazards/', BACKGROUND).then((r) => ({ data: r.data, etag: r.headers?.etag || null })),
  detail: (id) => client.get(`/api/hazards/${id}/`).then((r) => r.data),
  create: (payload) => client.post('/api/hazards/create/', payload).then((r) => r.data),

  // Who received this zone's latest alert and who has opened it, by barangay
  receipts: (id) => client.get(`/api/hazards/${id}/receipts/`).then((r) => r.data),

  // What a publish would do, without doing it: the clipped shape, the
  // barangays and number of accounts it reaches, overlapping zones of the
  // same type, and whether it needs a second officer. Saves nothing.
  // Resolved or archived zones of a type near a spot, each with corners to start from
  pastZones: ({ type, lat, lng, radius }) =>
    client.get('/api/hazards/past-zones/', { params: { type, lat, lng, ...(radius ? { radius } : {}) } })
      .then((r) => r.data),
  preview: (payload) => client.post('/api/hazards/preview/', payload).then((r) => r.data),

  // Extreme alerts waiting for a second officer, and approving one (sends it).
  // To refuse one, withdraw it with retract() and a reason.
  awaiting: () => client.get('/api/hazards/awaiting/', BACKGROUND).then((r) => r.data),
  approve: (id) => client.post(`/api/hazards/${id}/approve/`).then((r) => r.data),

  // Don't raise a live zone to Extreme after all; it stays at its current
  // level and the officer who asked is told the reason.
  refuseRaise: (id, reason) =>
    client.post(`/api/hazards/${id}/raise/refuse/`, { reason }).then((r) => r.data),

  // DRRMO: close a fire with the BFP figures (the fire log's columns G-W).
  // A fire still on the map is put out in the same step: the all-clear goes
  // and one history record is filed. Answers { zone, record_id }.
  closeFire: (id, figures) => client.post(`/api/hazards/${id}/close/`, figures).then((r) => r.data),

  update: (id, payload) => client.patch(`/api/hazards/${id}/`, payload).then((r) => r.data),

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