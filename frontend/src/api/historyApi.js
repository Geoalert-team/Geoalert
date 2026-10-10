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

  // Where past hazards happened (centre, radius, severity, date), for the map's heat shading
  heat: (years) =>
    client.get('/api/history/heat/', { params: years ? { years } : {} }).then((r) => r.data),
};