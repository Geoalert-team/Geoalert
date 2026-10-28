// The short facts a live hazard's panel leads with: the puroks it is at,
// when it started and how long it has been active. Plain functions so they
// test without the panel.

// The puroks its pins name, in order and once each; 'Talisay City' for a zone
// drawn with no report (it has no pins)
export function placeLine(item) {
  const names = [...new Set((item?.pins || []).map((p) => p.purok_name).filter(Boolean))];
  return names.length ? names.join(', ') : 'Talisay City';
}

// 'Oct 27, 2026, 1:59 PM'
export function formatWhen(iso) {
  if (!iso) return 'Not recorded';
  return new Date(iso).toLocaleString('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

// How long since `iso`: 'Under an hour', '5 hours', '1 day', '3 days'
export function activeFor(iso, now = new Date()) {
  if (!iso) return 'Not recorded';
  const hours = Math.floor((now.getTime() - new Date(iso).getTime()) / 3600000);
  if (hours < 1) return 'Under an hour';
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'}`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? '' : 's'}`;
}
