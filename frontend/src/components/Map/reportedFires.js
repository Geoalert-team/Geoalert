// Fire reports a barangay has sent that DRRMO has not decided yet. BFP is
// told of each one as soon as it is sent (backend apps/hazards/alerts.py,
// tell_bfp_of_report), so staff see where it is on the map and on the BFP
// dashboard while DRRMO reviews it. Residents never see these: only a fire
// DRRMO has approved goes on the public map and alerts anyone.

// How far back the map looks for reports still waiting
export const REPORTED_WINDOW_HOURS = 24;

/** Still waiting for DRRMO: pending, and not yet put on the map as a zone. */
export function awaitingDrrmo(report) {
  return report?.status === 'Pending' && !report?.hazard_zone;
}

/**
 * Where a report's pins go, as [{ key, position: [lat, lng], place }]: one at
 * each purok it names (the point the server gives inside that purok), or the
 * pin the reporter dropped when it names none. Empty when it has neither.
 */
export function reportSpots(report) {
  const puroks = (report?.puroks || []).filter((p) => p.lat != null && p.lng != null);
  if (puroks.length) {
    return puroks.map((p) => ({ key: `${report.id}-${p.id}`, position: [p.lat, p.lng], place: p.name }));
  }
  if (report?.latitude != null && report?.longitude != null) {
    return [{ key: String(report.id), position: [report.latitude, report.longitude], place: null }];
  }
  return [];
}
