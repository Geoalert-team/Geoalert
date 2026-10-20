// Order for the barangay activity table: the chosen count, most first; ties
// by the other count, then by name, so the order never depends on the API's.

const OTHER = { zones: 'incidents', incidents: 'zones' };

export function sortBarangays(rows, key) {
  const other = OTHER[key];
  return [...rows].sort((a, b) => (
    b[key] - a[key] || b[other] - a[other] || a.barangay.localeCompare(b.barangay)
  ));
}
