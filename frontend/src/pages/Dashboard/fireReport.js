// What the incident report form asks, checks and sends. A fire report is
// when and where, the BFP fire log's columns A-F: when it started and the
// puroks it is in, picked from the barangay's list. The reporter doesn't
// place a pin: the map shows one at each chosen purok, and the server sets
// the report's location from them. Property type, casualties, damage and
// alarm level are DRRMO's, entered when the fire is closed. Other hazards
// keep the clickable pin and "How serious is it?".
// The server checks the same rules (apps/reports/fire_report.py) with the
// same words.

import { puroksOf } from '../../components/Map/purokStyle';

export const MAX_PUROKS = 10;

// A phone clock a few minutes fast is not a start time in the future
const CLOCK_SKEW_MS = 5 * 60 * 1000;
const UNNAMED = /^Unnamed area (\d+)$/;
// Errors that belong to one hazard type's fields, cleared when it changes
const HAZARD_FIELD_ERRORS = ['started_at', 'puroks', 'location', 'severity_estimate'];

export function isFireType(hazardTypes, id) {
  const type = (hazardTypes || []).find((t) => String(t.id) === String(id));
  return (type?.name || '').toLowerCase() === 'fire';
}

// The value a datetime-local input takes: YYYY-MM-DDTHH:mm in local time
export function localNow(now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

// The barangay's puroks not chosen yet, for "+ Add another": named ones
// A-Z, then the unnamed areas in number order, marked as having no name yet
export function purokOptions(geo, barangayId, chosen = []) {
  const taken = new Set(chosen.map(String));
  const all = (puroksOf(geo, barangayId)?.features || [])
    .map((f) => ({ id: String(f.id), name: f.properties?.name || '' }))
    .filter((p) => !taken.has(p.id));
  const named = all.filter((p) => !UNNAMED.test(p.name)).sort((a, b) => a.name.localeCompare(b.name));
  const unnamed = all.filter((p) => UNNAMED.test(p.name))
    .sort((a, b) => Number(a.name.match(UNNAMED)[1]) - Number(b.name.match(UNNAMED)[1]));
  return [
    ...named.map((p) => ({ id: p.id, label: p.name })),
    ...unnamed.map((p) => ({ id: p.id, label: `${p.name} (no name yet)` })),
  ];
}

// Where the map puts a pin for each chosen purok: a point inside it
export function purokPins(geo, ids) {
  const byId = new Map((geo?.features || []).map((f) => [String(f.id), f]));
  return ids.map(String).map((id) => byId.get(id)).filter(Boolean).map((f) => ({
    id: String(f.id),
    name: f.properties?.name || '',
    lat: f.properties?.label_point?.[1],
    lng: f.properties?.label_point?.[0],
  }));
}

// Choosing Fire sets the start time to now, unless the reporter already
// changed it: a dashboard left open since morning must not date a fire then
export function withHazardType(form, id, { fire, now = new Date() }) {
  const next = { ...form, hazard_type: id };
  if (fire && !form.started_at_edited) next.started_at = localNow(now);
  return next;
}

// Another barangay's puroks don't belong to this report
export function withBarangay(form, id) {
  return { ...form, barangay: id, puroks: [] };
}

export function hazardSwitchErrors(errors) {
  const next = { ...errors };
  HAZARD_FIELD_ERRORS.forEach((k) => delete next[k]);
  return next;
}

export function validateReport(form, { fire, hasPuroks, purokStatus, now = new Date() }) {
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
  const puroks = form.puroks || [];
  if (purokStatus === 'failed') e.puroks = "The purok list didn't load. Try again.";
  else if (puroks.length > MAX_PUROKS) e.puroks = `Choose at most ${MAX_PUROKS} puroks.`;
  else if (hasPuroks && puroks.length === 0) e.puroks = 'Choose the purok or sitio where the fire is.';
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
  };
  if (!fire) return { ...body, location: form.location, severity_estimate: form.severity_estimate };
  return {
    ...body,
    started_at: new Date(form.started_at).toISOString(),
    puroks: (form.puroks || []).map(Number),
  };
}

// Where a report says it is: the puroks it names
export function placeLabel(report) {
  const names = (report.puroks || []).map((p) => p.name).filter(Boolean);
  return names.length ? names.join(', ') : null;
}
