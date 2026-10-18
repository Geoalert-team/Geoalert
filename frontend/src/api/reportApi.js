import client from './axiosClient';


export const reportsApi = {
  // Barangay Personnel: list their own reports
  // DRRMO/Admin: list all reports (optional ?status= filter)
  list: (status) =>
    client.get('/api/reports/incidents/', { params: status ? { status } : {} }).then((r) => r.data),



  // Barangay Personnel: submit a new incident report.
  // photos is an optional array of File objects from an <input type="file" multiple>.
  submit: ({
    barangay, hazard_type, description,
    agency = '', position = '', severity_estimate = '', photos = [],
  }) => {
    const body = { barangay, hazard_type, description, agency, position, severity_estimate };

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