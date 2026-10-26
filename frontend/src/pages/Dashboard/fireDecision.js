// The DRRMO's decision on a fire report: approve it as a new fire, attach it
// to a fire nearby, or reject it. The officer doesn't choose a level: it is
// the highest among the report's puroks' fire history. The server
// (apps/reports/decide.py) holds the same rules.

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

// A fire report not yet on the map: still pending, or validated before the
// fire decision existed and never published
export function canDecide(report) {
  if (!isFireReport(report)) return false;
  return report.status === 'Pending' || (report.status === 'Validated' && !report.hazard_zone);
}

export function historyLine(purok, years) {
  const fires = purok.count === 0 ? 'no fires' : `${purok.count} fire${purok.count === 1 ? '' : 's'}`;
  return `${purok.name}: ${fires} in ${years} years → ${levelLabel(purok.level || 'Green')}`;
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
