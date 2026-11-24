// Filters for Reports & Analytics and for Trend Analysis: a period, a hazard
// type and a barangay. Each page has its own presets (`kind`), but both keep
// them in the address (?period=&from=&to=&hazard=&barangay=) so a link or a
// refresh shows the same figures, and the backend applies them
// (apps/reports/filters.py) to every figure on the page.

// Reports & Analytics: recent operational periods
export const PRESETS = [
  { key: '3m', label: '3 months' },
  { key: '6m', label: '6 months' },
  { key: '12m', label: '12 months' },
  { key: 'year', label: 'This year' },
  { key: '5y', label: '5 years' },
  { key: 'all', label: 'All records' },
  { key: 'custom', label: 'Custom' },
];

// Trend Analysis: whole calendar years, the whole archive by default
export const TREND_PRESETS = [
  { key: 'all', label: 'All records' },
  { key: 'y10', label: '10 years' },
  { key: 'y5', label: '5 years' },
  { key: 'y3', label: '3 years' },
  { key: 'year', label: 'This year' },
  { key: 'custom', label: 'Custom' },
];

export const DEFAULT_FILTERS = { period: '12m', from: '', to: '', hazard: '', barangay: '' };
const TREND_DEFAULTS = { ...DEFAULT_FILTERS, period: 'all' };

export const presetsFor = (kind = 'reports') => (kind === 'trends' ? TREND_PRESETS : PRESETS);
export const defaultFilters = (kind = 'reports') => (kind === 'trends' ? TREND_DEFAULTS : DEFAULT_FILTERS);

const KEYS = Object.keys(DEFAULT_FILTERS);
const MONTHS = { '3m': 3, '6m': 6, '12m': 12, '5y': 60 };
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const isDate = (v) => /^\d{4}-\d{2}-\d{2}$/.test(v || '');
const isId = (v) => /^[1-9]\d*$/.test(v || '');

/** A local date as 2026-11-24. */
export function ymd(d) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function filtersFromParams(params, kind = 'reports') {
  const fallback = defaultFilters(kind).period;
  const period = presetsFor(kind).some((p) => p.key === params.get('period')) ? params.get('period') : fallback;
  const custom = period === 'custom';
  const pick = (key, ok) => (ok(params.get(key)) ? params.get(key) : '');
  return {
    period,
    from: custom ? pick('from', isDate) : '',
    to: custom ? pick('to', isDate) : '',
    hazard: pick('hazard', isId),
    barangay: pick('barangay', isId),
  };
}

/** The filters written into a copy of `base`, leaving its other keys (a section) alone. */
export function filtersToParams(filters, base, kind = 'reports') {
  const defaults = defaultFilters(kind);
  const next = new URLSearchParams(base);
  KEYS.forEach((key) => {
    next.delete(key);
    const value = filters[key];
    const dated = key === 'from' || key === 'to';
    if (value && value !== defaults[key] && (!dated || filters.period === 'custom')) next.set(key, value);
  });
  return next;
}

/** { from, to } as YYYY-MM-DD; from is null for "everything on record". */
export function resolveRange(filters, today) {
  const to = ymd(today);
  if (filters.period === 'custom') return { from: filters.from || null, to: filters.to || to };
  if (filters.period === 'all') return { from: null, to };
  if (filters.period === 'year') return { from: ymd(new Date(today.getFullYear(), 0, 1)), to };
  const years = /^y(\d+)$/.exec(filters.period);
  if (years) return { from: ymd(new Date(today.getFullYear() - (Number(years[1]) - 1), 0, 1)), to };
  const months = MONTHS[filters.period] || 12;
  return { from: ymd(new Date(today.getFullYear(), today.getMonth() - (months - 1), 1)), to };
}

export function rangeError(filters, today = new Date()) {
  if (filters.period !== 'custom') return null;
  if (filters.from && filters.to && filters.from > filters.to) return 'The start date is after the end date.';
  if (filters.from && !filters.to && filters.from > ymd(today)) return 'The start date is in the future.';
  return null;
}

/** Query parameters for /api/reports/* */
export function requestParams(filters, today) {
  const { from, to } = resolveRange(filters, today);
  const out = {};
  if (from) out.date_from = from;
  out.date_to = to;
  if (filters.hazard) out.hazard_type = filters.hazard;
  if (filters.barangay) out.barangay = filters.barangay;
  return out;
}

/**
 * Names for the picked hazard and barangay. An id the loaded list does not
 * hold is named as unknown (a stale link), never read as "all"; before the
 * lists load it is named by its number.
 */
export function namesFor(filters, hazardTypes = [], barangays = []) {
  const name = (list, id, word, unknown) => {
    if (!id) return null;
    if (!list.length) return `${word} #${id}`;
    return list.find((x) => String(x.id) === String(id))?.name || `${unknown} (#${id})`;
  };
  return {
    hazardName: name(hazardTypes, filters.hazard, 'Hazard type', 'Unknown hazard type'),
    barangayName: name(barangays, filters.barangay, 'Barangay', 'Unknown barangay'),
  };
}

const parts = (iso) => iso.split('-').map(Number);
const monthWords = (iso) => { const [y, m] = parts(iso); return `${MON[m - 1]} ${y}`; };
const dayWords = (iso) => { const [y, m, d] = parts(iso); return `${d} ${MON[m - 1]} ${y}`; };

/** "Dec 2025 – Nov 2026 · Flood · Lagtang" */
export function describeFilters(filters, { hazardName, barangayName } = {}, today) {
  const { from, to } = resolveRange(filters, today);
  const words = filters.period === 'custom' ? dayWords : monthWords;
  const range = from ? `${words(from)} – ${words(to)}` : `All records to ${words(to)}`;
  return [range, hazardName || 'All hazards', barangayName || 'All barangays'].join(' · ');
}

/** The filters as the audit log has always written them for reports. */
export function criteriaText(filters, { hazardName, barangayName } = {}, today) {
  const { from, to } = resolveRange(filters, today);
  return `date_from=${from || '-'} date_to=${to} barangay=${barangayName || 'all'} hazard_type=${hazardName || 'all'}`;
}

/**
 * The same two lines from a loaded answer's own range and filters, so an
 * export always describes the figures it carries, whatever the controls say.
 */
export function answerWords(answer) {
  if (!answer?.range) return { words: '', criteria: '' };
  const { from, to } = answer.range;
  const hazard = answer.filters?.hazard_type?.name;
  const barangay = answer.filters?.barangay?.name;
  const range = from ? `${dayWords(from)} – ${dayWords(to)}` : `All records to ${dayWords(to)}`;
  return {
    words: [range, hazard || 'All hazards', barangay || 'All barangays'].join(' · '),
    criteria: `date_from=${from || '-'} date_to=${to} barangay=${barangay || 'all'} hazard_type=${hazard || 'all'}`,
  };
}

export function isDefault(filters, kind = 'reports') {
  const defaults = defaultFilters(kind);
  return KEYS.every((key) => (filters[key] || '') === defaults[key]);
}

export function sameFilters(a, b) {
  return KEYS.every((key) => (a[key] || '') === (b[key] || ''));
}
