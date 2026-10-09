import client from './axiosClient';


export const reportsApi = {
  // Barangay Personnel: list their own reports
  // DRRMO/Admin: list all reports (optional ?status= filter)
  list: (status) =>
    client.get('/api/reports/incidents/', { params: status ? { status } : {} }).then((r) => r.data),



  // Barangay Personnel: submit a new incident report
  submit: ({
    barangay, hazard_type, description,
    casualties_dead = 0, casualties_injured = 0, casualties_missing = 0, displaced = 0,
    agency = '', position = '', severity_estimate = '',
  }) =>
    client
      .post('/api/reports/incidents/', {
        barangay, hazard_type, description,
        casualties_dead, casualties_injured, casualties_missing, displaced,
        agency, position, severity_estimate,
      })
      .then((r) => r.data),



  // DRRMO/Admin: validate or reject a report
  review: (id, { status, review_note }) =>
    client.patch(`/api/reports/incidents/${id}/review/`, { status, review_note }).then((r) => r.data),



  // DRRMO/Admin: hazard summary & response status reports
  hazardSummary: (params) =>
    client.get('/api/reports/hazard-summary/', { params }).then((r) => r.data),


  
  responseStatus: (params) =>
    client.get('/api/reports/response-status/', { params }).then((r) => r.data),
};