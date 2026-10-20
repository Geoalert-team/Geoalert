// Severity codes as stored, the words shown for them, and the one order they
// are listed in. Kept apart from chartTheme.js (which pulls in Chart.js) so
// plain helpers and their tests can use it.

export const SEVERITY_LABEL = { Red: 'Extreme', Orange: 'Moderate', Green: 'Low' };

// Worst first, always: a list sorted by count would move Extreme around
// between periods, and severity is a scale, not a set of names
export const SEVERITY_ORDER = ['Red', 'Orange', 'Green'];

/**
 * One row per known severity in SEVERITY_ORDER, with count 0 where the input
 * has none, then any unknown codes in their original order.
 */
export function inSeverityOrder(rows = [], key = 'severity') {
  const byCode = new Map(rows.map((r) => [r[key], r]));
  const known = SEVERITY_ORDER.map((code) => byCode.get(code) || { [key]: code, count: 0 });
  const unknown = rows.filter((r) => !SEVERITY_ORDER.includes(r[key]));
  return [...known, ...unknown];
}
