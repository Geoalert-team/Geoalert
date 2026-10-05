// mockApi.js
// ---------------------------------------------------------------
// Stand-in for endpoints that do not exist in the Django backend yet:
// apps/reports, apps/guidance, and user/system management under
// apps/admin_dashboard are all still empty on the backend side.
//
// Everything here lives in memory and resets on page refresh. Each
// function is written to match the shape a real REST call would
// return, so swapping a real axios call in for the mock body later is
// a small, contained change, not a rewrite of the pages that use it.
// ---------------------------------------------------------------

function delay(ms = 300) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
function uid(prefix) {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

// ---- Incident reports (Barangay Personnel submit, DRRMO/Admin validate) ----
let incidentReports = [
  {
    id: uid('rep'), barangay_name: 'Tabunoc', hazard_type: 'Flood',
    description: 'Ankle-deep water along the main road near the chapel, still rising.',
    reported_by: 'Liza Cabrera', status: 'Pending',
    created_at: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    reviewed_by: null, reviewed_at: null, review_note: '',
  },
  {
    id: uid('rep'), barangay_name: 'Maghaway', hazard_type: 'Landslide',
    description: 'Cracks appearing on the slope behind Purok 3, residents worried.',
    reported_by: 'Liza Cabrera', status: 'Validated',
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 20).toISOString(),
    reviewed_by: 'Edgar Nacario', reviewed_at: new Date(Date.now() - 1000 * 60 * 60 * 18).toISOString(),
    review_note: 'Confirmed on-site, escalated to active hazard zone.',
  },
];

export const reportsApi = {
  list: async () => { await delay(); return [...incidentReports].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)); },
  submit: async ({ barangay_name, hazard_type, description, reported_by }) => {
    await delay();
    const report = {
      id: uid('rep'), barangay_name, hazard_type, description, reported_by,
      status: 'Pending', created_at: new Date().toISOString(),
      reviewed_by: null, reviewed_at: null, review_note: '',
    };
    incidentReports = [report, ...incidentReports];
    return report;
  },
  review: async (id, { status, review_note, reviewed_by }) => {
    await delay();
    incidentReports = incidentReports.map((r) =>
      r.id === id ? { ...r, status, review_note, reviewed_by, reviewed_at: new Date().toISOString() } : r
    );
    return incidentReports.find((r) => r.id === id);
  },
};

// ---- Safety guidance content (DRRMO/Admin manage, everyone reads) ----
let guidanceArticles = [
  {
    id: uid('gd'), title: 'Before a flood', hazard_type: 'Flood',
    body: 'Move valuables and electrical items above expected water level. Keep a battery radio and flashlight ready. Know your barangay\'s evacuation route in advance.',
    created_by: 'Edgar Nacario', updated_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 3).toISOString(),
  },
  {
    id: uid('gd'), title: 'During a landslide warning', hazard_type: 'Landslide',
    body: 'Evacuate immediately if you hear cracking sounds, see new cracks in the ground, or notice leaning trees or poles. Do not return until DRRMO clears the area.',
    created_by: 'Edgar Nacario', updated_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
  },
];

export const guidanceApi = {
  list: async () => { await delay(); return [...guidanceArticles].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at)); },
  create: async ({ title, hazard_type, body, created_by }) => {
    await delay();
    const article = { id: uid('gd'), title, hazard_type, body, created_by, updated_at: new Date().toISOString() };
    guidanceArticles = [article, ...guidanceArticles];
    return article;
  },
  update: async (id, patch) => {
    await delay();
    guidanceArticles = guidanceArticles.map((a) => (a.id === id ? { ...a, ...patch, updated_at: new Date().toISOString() } : a));
    return guidanceArticles.find((a) => a.id === id);
  },
  remove: async (id) => {
    await delay();
    guidanceArticles = guidanceArticles.filter((a) => a.id !== id);
  },
};

// ---- User management (System Admin) ----
let mockUsers = [
  { id: uid('usr'), full_name: 'Rosario Villamor', email: 'admin@geoalert.gov.ph', role: 'System_Admin', is_active: true, created_at: '2026-08-01T00:00:00Z' },
  { id: uid('usr'), full_name: 'Edgar Nacario', email: 'officer@geoalert.gov.ph', role: 'DRRMO_Officer', is_active: true, created_at: '2026-08-03T00:00:00Z' },
  { id: uid('usr'), full_name: 'Liza Cabrera', email: 'barangay@geoalert.gov.ph', role: 'Barangay_Personnel', is_active: true, created_at: '2026-08-05T00:00:00Z' },
];

export const usersApi = {
  list: async () => { await delay(); return [...mockUsers]; },
  create: async ({ full_name, email, role }) => {
    await delay();
    const user = { id: uid('usr'), full_name, email, role, is_active: true, created_at: new Date().toISOString() };
    mockUsers = [...mockUsers, user];
    return user;
  },
  update: async (id, patch) => {
    await delay();
    mockUsers = mockUsers.map((u) => (u.id === id ? { ...u, ...patch } : u));
    return mockUsers.find((u) => u.id === id);
  },
  setActive: async (id, is_active) => {
    await delay();
    mockUsers = mockUsers.map((u) => (u.id === id ? { ...u, is_active } : u));
    return mockUsers.find((u) => u.id === id);
  },
};

// ---- System settings (System Admin) ----
let systemSettings = {
  site_name: 'GeoAlert â€” Talisay City DRRMO',
  alert_lock_threshold: 5,
  lock_duration_minutes: 15,
  maintenance_mode: false,
};

export const settingsApi = {
  get: async () => { await delay(); return { ...systemSettings }; },
  update: async (patch) => { await delay(); systemSettings = { ...systemSettings, ...patch }; return { ...systemSettings }; },
};

// ---- System logs + performance (System Admin) ----
const logLevels = ['INFO', 'INFO', 'INFO', 'WARNING', 'ERROR'];
const logMessages = [
  'User logged in', 'Hazard zone published', 'Hazard zone resolved',
  'Failed login attempt', 'Account locked after 5 failed attempts',
  '2FA enabled for account', 'Incident report submitted', 'Incident report validated',
];
let systemLogs = Array.from({ length: 14 }).map((_, i) => ({
  id: uid('log'),
  timestamp: new Date(Date.now() - i * 1000 * 60 * 37).toISOString(),
  level: logLevels[Math.floor(Math.random() * logLevels.length)],
  message: logMessages[Math.floor(Math.random() * logMessages.length)],
}));

export const logsApi = {
  list: async () => { await delay(); return [...systemLogs].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)); },
  metrics: async () => {
    await delay();
    return {
      uptime_pct: 99.6,
      avg_response_ms: 142,
      active_sessions: 7,
      db_status: 'Connected',
    };
  },
};
