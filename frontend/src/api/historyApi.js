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

  // Fire's likelihood per barangay (a prediction model since 2026-11-22) and flood susceptibility
  // per purok (since 2026-11-24, the same in every month); landslide is being rebuilt. Fire's
  // chance is 0 to 1; level (Low, Moderate, High) is on the month's chance.
  // params: month (1-12), or month and year, or date; hazards: 'Fire', 'Flood' or 'Fire,Flood'
  // (see hazardsParam) or hazard_type_name: 'Fire' or 'Flood' (not both; any other hazard is a
  // 400); barangay (adds that barangay's 12-month fire profile)
  // response: results (one row per barangay: method 'model' with probability, level, in_training;
  // or method 'unavailable' with reason), model_hazards, unavailable_hazards, by_barangay, profile;
  // with Flood asked: flood ({ available, reason, source 'model' or 'noah', basis,
  // varies_by_month: false }) and flood_results (one row per purok: level or null,
  // not_assessed_reason, uncertain, estimated_outline)
  forecast: (params) =>
    client.get('/api/history/forecast/', { params }).then((r) => r.data),

  // Whether there is enough located flood data to improve the flood predictions: { located_flood_days,
  // forecast_days_needed: { min, max }, enough_for_forecasting, flood_map, since_publishing } (counts only)
  forecastReadiness: () =>
    client.get('/api/history/forecast/readiness/').then((r) => r.data),

  // How the fire model did on fires it never saw: { hazards: [{ hazard: 'Fire', kind, status, reason?, ... }] }
  forecastAccuracy: () =>
    client.get('/api/history/forecast/accuracy/').then((r) => r.data),

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

  // DRRMO: the records as a file in the BFP fire log's columns A-W, newest
  // first (a Blob). params: file ('xlsx' or 'csv'), types ('Fire,Flood';
  // every type when left out) and the list's barangay, purok, date_from, date_to
  export: (params) =>
    client.get('/api/history/export/', { params, responseType: 'blob' }).then((r) => r.data),

  // DRRMO: the BFP fire log or the flood and landslide log (.xlsx). Without
  // save it only checks the file. Answers { kind, kind_label, read, new,
  // already, linked, barangay_only, problems: [{ label, rows }], unlinked:
  // [{ barangay, place, count, close }], to_check, saved }.
  importFile: (file, { save = false, includeWarnings = false } = {}) => {
    const form = new FormData();
    form.append('file', file, file.name);
    if (save) form.append('save', 'true');
    if (includeWarnings) form.append('include_warnings', 'true');
    // multipart, not the client's JSON default, or the file is lost (see reportApi.create)
    return client
      .post('/api/history/import/', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => r.data);
  },
};
