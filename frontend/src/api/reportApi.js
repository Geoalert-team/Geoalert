import client from './axiosClient';


export const reportsApi = {
  // F7: record that a generated report was printed, before the browser
  // opens its print dialog. criteria is the filters, as text.
  // via is 'print', 'pdf' or 'csv'; report may also be 'analytics'.
  printed: (report, criteria, via = 'print') =>
    client.post('/api/reports/printed/', { report, criteria, via }).then((r) => r.data),

  // F7 analytics dashboard: { kpis, monthly, zones_by_type, zones_by_severity,
  // barangays, hazard_type, ... } for the last `months` months (3, 6, 12 or
  // 24). Optional hazard_type (id) counts one type only; include_samples=true
  // counts seeded test rows.
  analytics: (params) =>
    client.get('/api/reports/analytics/', { params }).then((r) => r.data),

  // Barangay Personnel: list their own reports
  // DRRMO/Admin: list all reports (optional ?status= filter)
  list: (status) =>
    client.get('/api/reports/incidents/', { params: status ? { status } : {} }).then((r) => r.data),

  // Pinned, non-rejected reports of one hazard type from the last hours, for
  // drawing a zone around where they were seen. DRRMO/Admin.
  located: (hazardTypeName, sinceHours = 72) =>
    client.get('/api/reports/incidents/', {
      params: { located: 'true', hazard_type_name: hazardTypeName, since_hours: sinceHours },
    }).then((r) => r.data),

  // Barangay Personnel: submit a new incident report.
  // photos is an optional array of File objects from an <input type="file" multiple>.
  submit: ({
    barangay, hazard_type, description,
    agency = '', position = '', severity_estimate = '', photos = [], location = null,
    started_at = null, purok = null, purok_other = '',
  }) => {
    const body = { barangay, hazard_type, description, agency, position, severity_estimate };
    // Optional map pin [lat, lng]: sent only when one was placed
    if (location) {
      body.latitude = Number(location[0].toFixed(6));
      body.longitude = Number(location[1].toFixed(6));
    }
    // Fire reports: when it started and which purok (or the name typed for
    // one that isn't on the list). Sent only when set.
    if (started_at) body.started_at = started_at;
    if (purok) body.purok = purok;
    if (purok_other) body.purok_other = purok_other;

    if (!photos || photos.length === 0) {
      return client.post('/api/reports/incidents/', body).then((r) => r.data);
    }

    const form = new FormData();
    Object.entries(body).forEach(([k, v]) => form.append(k, v ?? ''));
    // Appended under the same key once per file. DRF reads them back with
    // getlist(), so all of them arrive rather than only the last.
    photos.forEach((file) => form.append('photos', file, file.name));

    // The Content-Type override is not optional. axiosClient sets
    // 'application/json' as a default header, and axios turns FormData into
    // JSON whenever the content type says JSON — the files would be sent as
    // "photos":{} and the request would still come back 201, so the report
    // would save with no photos and nothing would look wrong. Naming
    // multipart here keeps the FormData intact; axios replaces this value
    // with the real boundary before sending.
    return client
      .post('/api/reports/incidents/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },



  // DRRMO/Admin: validate or reject a report
  review: (id, { status, review_note }) =>
    client.patch(`/api/reports/incidents/${id}/review/`, { status, review_note }).then((r) => r.data),



  // DRRMO/Admin: hazard summary & response status reports
  hazardSummary: (params) =>
    client.get('/api/reports/hazard-summary/', { params }).then((r) => r.data),


  
  responseStatus: (params) =>
    client.get('/api/reports/response-status/', { params }).then((r) => r.data),
};