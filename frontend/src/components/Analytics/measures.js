// The four month-by-month measures of the Analytics tab, and the wording
// helpers its sections share. No Chart.js here, so tests can import it.

export const MEASURES = [
  { key: 'zones', label: 'Zones published', unit: { one: 'zone', many: 'zones' } },
  { key: 'alerts', label: 'Alerts issued', unit: { one: 'alert', many: 'alerts' } },
  { key: 'incidents', label: 'Incident reports', unit: { one: 'report', many: 'reports' } },
  { key: 'events', label: 'Recorded hazard events', unit: { one: 'event', many: 'events' } },
];

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** '2026-03' -> 'Mar 2026' */
export const monthLabel = (ym) => {
  const [y, m] = ym.split('-').map(Number);
  return `${MONTH_SHORT[m - 1]} ${y}`;
};

/** 95 minutes -> "1 h 35 min"; 3000 -> "2.1 days" */
export function duration(minutes) {
  if (minutes === null || minutes === undefined) return '—';
  if (minutes < 60) return `${Math.round(minutes)} min`;
  if (minutes < 48 * 60) {
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return m ? `${h} h ${m} min` : `${h} h`;
  }
  return `${(minutes / 1440).toFixed(1)} days`;
}
