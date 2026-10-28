import client from './axiosClient';

export const historyApi = {
  list: (params) =>
    client.get('/api/history/', { params }).then((r) => r.data),

  // One page of records: { count, results, type_counts }. params may include
  // barangay, hazard_type_name, limit and offset.
  page: (params) =>
    client.get('/api/history/', { params }).then((r) => r.data),

  detail: (id) =>
    client.get(`/api/history/${id}/`).then((r) => r.data),

  trends: (params) =>
    client.get('/api/history/trends/', { params }).then((r) => r.data),

  // Seasonal likelihood per barangay for a month (rule-based, see backend apps/history/forecast.py).
  // params: month (1-12), hazard_type_name, barangay (adds that barangay's 12-month profile)
  forecast: (params) =>
    client.get('/api/history/forecast/', { params }).then((r) => r.data),

  // Per purok and hazard type: past events in the period and their level,
  // { thresholds, results: [{ purok, type, count, level }] }. types: names, all when omitted.
  purokLevels: (types) =>
    client.get('/api/history/purok-levels/', { params: types?.length ? { types: types.join(',') } : {} })
      .then((r) => r.data),

  // One barangay's past hazards, or one purok's in it. params: barangay,
  // purok (id or 'none'), types ('Fire,Flood'), period ('all' for all time)
  area: (params) =>
    client.get('/api/history/area/', { params }).then((r) => r.data),

  // DRRMO: the fire close form's lists, { property_types: {category: [sub]}, alarm_levels: [...] }
  bfpOptions: () => client.get('/api/history/bfp-options/').then((r) => r.data),
  // The flood and landslide close form's list: sub categories by hazard type
  eventOptions: () => client.get('/api/history/event-options/').then((r) => r.data),
};