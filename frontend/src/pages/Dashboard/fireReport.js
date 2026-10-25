// What the incident report form asks, checks and sends. A fire report is
// when and where, the BFP fire log's columns A-F: when it started, a pin,
// and the purok (picked from the pin, or typed when it isn't on the list).
// Property type, casualties, damage and alarm level are DRRMO's, entered
// when the fire is closed. Other hazards keep "How serious is it?".
// The server checks the same rules (apps/reports/fire_report.py) with the
// same words.

import { purokAt, puroksOf } from '../../components/Map/purokStyle';

// The purok choice that opens a text box for the name
export const NOT_LISTED = 'other';

// A phone clock a few minutes fast is not a start time in the future
const CLOCK_SKEW_MS = 5 * 60 * 1000;
const UNNAMED = /^Unnamed area (\d+)$/;

export function isFireType(hazardTypes, id) {
  const type = (hazardTypes || []).find((t) => String(t.id) === String(id));
  return (type?.name || '').toLowerCase() === 'fire';
}

// The value a datetime-local input takes: YYYY-MM-DDTHH:mm in local time
export function localNow(now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

// The barangay's puroks for the dropdown: named ones A-Z, then the unnamed
// areas in number order, marked as having no name yet
export function purokOptions(geo, barangayId) {
  const features = puroksOf(geo, barangayId)?.features || [];
  const all = features.map((f) => ({ id: String(f.id), name: f.properties?.name || '' }));
  const named = all.filter((p) => !UNNAMED.test(p.name)).sort((a, b) => a.name.localeCompare(b.name));
  const unnamed = all.filter((p) => UNNAMED.test(p.name))
    .sort((a, b) => Number(a.name.match(UNNAMED)[1]) - Number(b.name.match(UNNAMED)[1]));
  return [
    ...named.map((p) => ({ id: p.id, label: p.name })),
    ...unnamed.map((p) => ({ id: p.id, label: `${p.name} (no name yet)` })),
  ];
}

// The purok under a pin ([lat, lng]) in this barangay, or null
export function purokAtPin(geo, barangayId, location) {
  if (!location) return null;
  const feature = purokAt(puroksOf(geo, barangayId), location[1], location[0]);
  return feature ? String(feature.id) : null;
}

export function validateReport(form, { fire, hasPuroks, now = new Date() }) {
  const e = {};
  if (!form.barangay) e.barangay = 'Choose the barangay where this is happening.';
  if (!form.hazard_type) e.hazard_type = 'Choose the type of hazard.';
  if (form.description.trim().length < 10) e.description = 'Describe what you are seeing in a sentence or two.';

  if (!fire) {
    if (!form.severity_estimate) e.severity_estimate = 'Choose how serious it looks.';
    return e;
  }
  if (!form.started_at) e.started_at = 'Say when the fire started.';
  else if (new Date(form.started_at).getTime() > now.getTime() + CLOCK_SKEW_MS) {
    e.started_at = "The start time can't be in the future.";
  }
  if (!form.location) e.location = 'Drop a pin where the fire is.';
  const typed = (form.purok_other || '').trim();
  const chosen = form.purok === NOT_LISTED ? typed : form.purok;
  if (hasPuroks && !chosen) e.purok = "Choose the purok or sitio, or pick 'Not on the list' and type its name.";
  return e;
}

// What reportsApi.submit is given (photos are added by the caller)
export function reportPayload(form, { fire }) {
  const body = {
    barangay: Number(form.barangay),
    hazard_type: Number(form.hazard_type),
    description: form.description.trim(),
    position: form.position,
    agency: form.agency,
    location: form.location,
  };
  if (!fire) return { ...body, severity_estimate: form.severity_estimate };

  body.started_at = new Date(form.started_at).toISOString();
  const typed = (form.purok_other || '').trim();
  if (form.purok && form.purok !== NOT_LISTED) body.purok = Number(form.purok);
  else if (typed) body.purok_other = typed;
  return body;
}

// Where a report says it is: its purok, or the name typed for one not on the list
export function placeLabel(report) {
  if (report.purok_name) return report.purok_name;
  if (report.purok_other) return `${report.purok_other} (not on the list)`;
  return null;
}
