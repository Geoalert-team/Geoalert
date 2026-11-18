// Helpers for the "Next 3 days" rain watch (GET /api/rain-watch/). The public
// gets Orange and Red only; Green and Yellow arrive as 'none'.

export const RAIN_LEVELS = {
  Red:     { label: 'Red',     color: '#c81e1e', rank: 3 },
  Orange:  { label: 'Orange',  color: '#ef7d22', rank: 2 },
  Yellow:  { label: 'Yellow',  color: '#f4c430', rank: 1 },
  Green:   { label: 'Green',   color: '#3a9d5d', rank: 0 },
  none:    { label: 'No rain watch', color: null, rank: -1 },
  unknown: { label: 'Out of date', color: '#9aa3b2', rank: -2 },
};

export const RAIN_FILL_OPACITY = 0.4;

export const RAIN_WATCH_NOTE =
  'Automatic estimate from weather forecasts (NOAA GFS) and PAGASA alerts. Not an official warning. Follow DRRMO and PAGASA.';
export const RAIN_WATCH_CREDITS =
  'Forecast: NOAA GFS (dynamical.org when NOAA is late). Alerts: PAGASA, CC BY 4.0. Rain so far: NASA POWER.';

export const rainLevel = (level) => RAIN_LEVELS[level] || RAIN_LEVELS.none;
const has = (types, t) => (types instanceof Set ? types.has(t) : (types || []).includes(t));
const escapeHtml = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// A forecast older than the answer's stale_hours is out of date (12 when the server does not say)
export const STALE_HOURS = 12;

const FLOOR_REASON = /^Raised (to|by DRRMO)/;

/**
 * The answer as the map should read it. When the last answer is more than
 * STALE_HOURS old but not marked stale (a poll has been failing), the forecast
 * levels go 'unknown' as the server does when stale; a level raised by a PAGASA
 * or DRRMO floor (its reasons say 'Raised to' / 'Raised by DRRMO') stays.
 */
export function withClientStale(data, now = Date.now()) {
  if (!data || data.stale || data.updated_at == null) return data;
  const h = hoursSince(data.updated_at, now);
  const limit = Number(data.stale_hours) > 0 ? Number(data.stale_hours) : STALE_HOURS;
  if (h == null || h <= limit) return data;
  const part = (p) => (p && !(p.reasons || []).some((r) => FLOOR_REASON.test(r)) ? { ...p, level: 'unknown' } : p);
  return {
    ...data,
    stale: true,
    days: (data.days || []).map((d) => ({
      ...d,
      barangays: (d.barangays || []).map((b) => ({ ...b, flood: part(b.flood), landslide: part(b.landslide) })),
    })),
  };
}

/**
 * The map level for one barangay on one day. No data for the day is 'unknown'.
 * With no runs at all the map reads like a stale one: a part with no real level
 * is grey, but a level the server sent from a floor (Orange or Red, Yellow for staff) shows.
 */
export function mapLevel(data, dayKey, barangayId, activeTypes) {
  if (!data) return 'unknown';
  const noRuns = data.updated_at == null;
  const day = dayData(data, dayKey);
  if (!day) return 'unknown';
  const row = (day.barangays || []).find((b) => String(b.id) === String(barangayId));
  if (!row) return data.stale || noRuns ? 'unknown' : 'none';
  const level = barangayLevel(row, activeTypes);
  return noRuns && rainLevel(level).rank < 1 && level !== 'unknown' ? 'unknown' : level;
}

export const dayData = (data, key) => (data?.days || []).find((d) => d.key === key) || null;

const worst = (levels) => levels.reduce((a, b) => (rainLevel(b).rank > rainLevel(a).rank ? b : a));
// Orange or Red wins; otherwise an out-of-date part beats a calm one, so an old map never looks calm
const worstOrUnknown = (levels) => {
  const top = worst(levels);
  return rainLevel(top).rank < 2 && levels.includes('unknown') ? 'unknown' : top;
};

/** The worst of the ticked hazards' levels for one barangay row; a null landslide is skipped */
export function barangayLevel(row, activeTypes) {
  const levels = [];
  if (row?.flood && has(activeTypes, 'Flood')) levels.push(row.flood.level);
  if (row?.landslide && has(activeTypes, 'Landslide')) levels.push(row.landslide.level);
  return levels.length ? worstOrUnknown(levels) : 'none';
}

function dayAlert(day, activeTypes) {
  const alerting = (day?.barangays || [])
    .map((b) => barangayLevel(b, activeTypes))
    .filter((l) => l === 'Orange' || l === 'Red');
  if (!alerting.length) return null;
  const level = worst(alerting);
  return { level, count: alerting.filter((l) => l === level).length };
}

/** The first day after `currentKey` with Orange or Red: {key, level, count}, else null */
export function laterDayHint(data, activeTypes, currentKey) {
  const days = data?.days || [];
  const at = days.findIndex((d) => d.key === currentKey);
  for (const day of days.slice(at + 1)) {
    const alert = dayAlert(day, activeTypes);
    if (alert) return { key: day.key, ...alert };
  }
  return null;
}

/** The first day, from Today, with Orange or Red: {key, level, count}, else null */
export function bannerInfo(data, activeTypes) {
  for (const day of data?.days || []) {
    const alert = dayAlert(day, activeTypes);
    if (alert) return { key: day.key, ...alert };
  }
  return null;
}

/** 'Today', 'Tomorrow', then the weekday ('Wed') of a Manila calendar date */
export function dayLabel(day, index) {
  if (index === 0) return 'Today';
  if (index === 1) return 'Tomorrow';
  if (!day?.date) return 'Day after';
  return new Date(`${day.date}T00:00:00Z`).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' });
}

export function hoursSince(updatedAt, now = Date.now()) {
  const t = updatedAt ? new Date(updatedAt).getTime() : NaN;
  return Number.isNaN(t) ? null : Math.max(0, (now - t) / 3600000);
}

export function updatedText(updatedAt, now = Date.now()) {
  const h = hoursSince(updatedAt, now);
  if (h == null) return 'No forecast yet';
  if (h < 1) return 'Updated just now';
  return `Updated ${Math.floor(h)} h ago`;
}

/** Tooltip HTML: the three days' colours, then the chosen day's reasons for each ticked hazard */
export function rainWatchTooltip(name, barangayId, data, dayKey, activeTypes) {
  const days = data?.days || [];
  const rowOf = (day) => (day?.barangays || []).find((b) => String(b.id) === String(barangayId));
  const strip = days
    .map((day, i) => {
      const row = rowOf(day);
      const level = row ? barangayLevel(row, activeTypes) : 'none';
      const text = level === 'none' || level === 'Green' ? '–' : level === 'unknown' ? 'Out of date' : level;
      return `${dayLabel(day, i)} ${text}`;
    })
    .join(' · ');
  const row = rowOf(dayData(data, dayKey));
  const lines = [];
  [['Flood', 'flood'], ['Landslide', 'landslide']].forEach(([hazard, field]) => {
    const part = row?.[field];
    if (!part || !has(activeTypes, hazard)) return;
    const reasons = (part.reasons || []).map(escapeHtml).join('; ');
    lines.push(`${hazard}: ${rainLevel(part.level).label}${reasons ? `. ${reasons}` : ''}`);
  });
  return [`<strong>${escapeHtml(name)}</strong>`, strip, ...lines].filter(Boolean).join('<br>');
}

/**
 * A short fingerprint of what the Next 3 days map shows: the stale flag, the floors, and
 * every barangay's levels and reasons. It goes in the map layer's key so the tooltips are
 * rebuilt when the answer changes without a new run.
 */
export function rainWatchSignature(data) {
  if (!data) return '';
  const parts = [data.stale ? 's' : 'f', data.updated_at ?? '', JSON.stringify(data.floors || [])];
  (data.days || []).forEach((d) => {
    parts.push(d.key);
    (d.barangays || []).forEach((b) => {
      parts.push(`${b.id}:${b.flood?.level ?? '-'}:${(b.flood?.reasons || []).join('|')}:${b.landslide?.level ?? '-'}:${(b.landslide?.reasons || []).join('|')}`);
    });
  });
  const text = parts.join('|');
  let h = 5381;
  for (let i = 0; i < text.length; i += 1) h = ((h * 33) ^ text.charCodeAt(i)) >>> 0;
  return `${text.length.toString(36)}-${h.toString(36)}`;
}
