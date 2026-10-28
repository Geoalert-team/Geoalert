// The DRRMO's "Validate and push" on a report: approve it as a new hazard
// pinned at its puroks, attach it to a live one of its type nearby, or
// reject it. Fires, floods and landslides alike. The officer doesn't choose a
// level: it is the highest among the report's puroks' history of that type.
// The server (apps/reports/decide.py) holds the same rules.

export const LEVELS = [
  { code: 'Green', label: 'Low' },
  { code: 'Orange', label: 'Moderate' },
  { code: 'Red', label: 'Extreme' },
];

export function levelLabel(code) {
  return LEVELS.find((l) => l.code === code)?.label || code;
}

export function isFireReport(report) {
  return (report?.hazard_type_details?.name || '').toLowerCase() === 'fire';
}

// A report not yet on the map: still pending, or validated without being
// pushed (a flood validated on its own, or a fire from before this flow)
export function canPush(report) {
  return report.status === 'Pending' || (report.status === 'Validated' && !report.hazard_zone);
}

// "fire", "flood", "landslide": what the report is about, in words
export function hazardNoun(report) {
  return (report?.hazard_type_details?.name || 'hazard').toLowerCase();
}

export function historyLine(purok, years, noun = 'fire') {
  const past = purok.count === 0 ? `no ${noun}s` : `${purok.count} ${noun}${purok.count === 1 ? '' : 's'}`;
  return `${purok.name}: ${past} in ${years} years → ${levelLabel(purok.level || 'Green')}`;
}

// Where a report's pins go on the map: one per purok it names, else its own
// location. The same shape PurokPreviewMap takes.
export function reportPins(report) {
  const puroks = report.puroks || [];
  if (puroks.length) return puroks.map((p) => ({ id: String(p.id), name: p.name, lat: p.lat, lng: p.lng }));
  if (report.latitude != null && report.longitude != null) {
    return [{ id: 'report', name: '', lat: report.latitude, lng: report.longitude }];
  }
  return [];
}

// The outlines of the puroks a report names, picked from the purok layer
// (barangaysApi.puroks()). [] until the layer has loaded.
export function reportPurokShapes(geo, report) {
  const ids = new Set((report?.puroks || []).map((p) => String(p.id)));
  return (geo?.features || []).filter((f) => ids.has(String(f.id)));
}
