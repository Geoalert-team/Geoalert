// Residents' hazard alerts, built from the same feed the map reads
// (GET /api/hazards/, Active zones as GeoJSON). Kept apart from the bell so
// the sorting, wording and "new" bookkeeping can be tested without rendering.

import { SEVERITY_ORDER } from './severity';

/**
 * One alert per Active zone, worst severity first, newest first within a
 * severity. Each names the barangay it is filed under.
 */
export function activeAlerts(featureCollection) {
  const features = featureCollection?.features || featureCollection?.results?.features || [];
  const rank = (code) => {
    const i = SEVERITY_ORDER.indexOf(code);
    return i === -1 ? SEVERITY_ORDER.length : i;
  };
  return features
    .map((f) => ({ id: f.id ?? f.properties?.id, ...f.properties }))
    .filter((p) => p.id != null && (!p.status || p.status === 'Active'))
    .map((p) => ({
      id: p.id,
      type: p.hazard_type_name || 'Hazard',
      severity: p.severity,
      barangays: [p.barangay_name].filter(Boolean),
      activatedAt: p.activated_at || null,
      sample: !!p.is_sample,
    }))
    .sort((a, b) => rank(a.severity) - rank(b.severity)
      || new Date(b.activatedAt || 0) - new Date(a.activatedAt || 0));
}

// What "seen" remembers about an alert. The severity is part of it, so a
// zone raised from Moderate to Extreme counts as new again.
export const alertKey = (alert) => `${alert.id}:${alert.severity}`;

// Alerts this browser has not seen yet. Residents have no account, so
// "read" lives in the browser (see ResidentAlertBell), not on the server.
export function unseenAlerts(alerts = [], seenKeys = []) {
  const seen = new Set(seenKeys);
  return alerts.filter((a) => !seen.has(alertKey(a)));
}

// "Bulacao", "Bulacao and Lawaan I", "Bulacao, Lawaan I and 2 more"
export function placesText(barangays = [], shown = 2) {
  if (barangays.length === 0) return 'Talisay City';
  if (barangays.length === 1) return barangays[0];
  if (barangays.length <= shown + 1) {
    return `${barangays.slice(0, -1).join(', ')} and ${barangays[barangays.length - 1]}`;
  }
  return `${barangays.slice(0, shown).join(', ')} and ${barangays.length - shown} more`;
}
