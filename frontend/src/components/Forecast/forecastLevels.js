// Seasonal likelihood levels from GET /api/history/forecast/. Rule-based
// statistics on past seasons; shown as a heads-up, never as an alert.

export const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export const LIKELIHOOD = {
  High:     { label: 'High',     color: '#d64545', tint: '#fcebeb', text: '#a12f2f', rank: 3 },
  Moderate: { label: 'Moderate', color: '#d99a00', tint: '#fdf5de', text: '#7a5700', rank: 2 },
  Low:      { label: 'Low',      color: '#1f9d55', tint: '#e8f6ee', text: '#16693a', rank: 1 },
  None:     { label: 'None on record', color: '#9aa3b2', tint: '#f1f3f6', text: '#4a5262', rank: 0 },
};

export const likelihoodInfo = (level) => LIKELIHOOD[level] || LIKELIHOOD.None;

/** 1-12 for next month, the default view: what to prepare for. */
export function nextMonth(now = new Date()) {
  return (now.getMonth() + 1) % 12 + 1;
}

/** "3 of 4 past Novembers" */
export function yearsText(row, monthName) {
  const n = row.years_considered;
  return `${row.years_hit} of ${n} past ${monthName}${n === 1 ? '' : 's'}`;
}

// The time a likelihood is for. 'month': that month, from every past one;
// 'monthYear': that month in that year, from the years before it, with what
// happened once it has started; 'date': the week around that day, likewise.
export const PERIOD_MODES = [
  { key: 'month', label: 'Month' },
  { key: 'monthYear', label: 'Month and year' },
  { key: 'date', label: 'Exact date' },
];

// The years the period picker offers, oldest first
export const FIRST_YEAR = 2021;
export const LAST_YEAR = 2033;
export const YEARS = Array.from({ length: LAST_YEAR - FIRST_YEAR + 1 }, (_, i) => FIRST_YEAR + i);

const pad = (n) => String(n).padStart(2, '0');

// [year, month, day] from 'YYYY-MM-DD', read as written: no time zone shift
const dateParts = (iso) => iso.split('-').map(Number);

/** "2025", "2021–2025", or '' for no years */
export function yearSpan(years) {
  if (!years?.length) return '';
  const first = years[0];
  const last = years[years.length - 1];
  return first === last ? String(first) : `${first}–${last}`;
}

/** Next month, as the view has always opened; the other modes start on it this year, and today. */
export function defaultPeriod(now = new Date()) {
  const month = nextMonth(now);
  const year = now.getFullYear() + (month === 1 ? 1 : 0);
  return {
    mode: 'month',
    month,
    // Kept to a year the picker offers
    year: Math.min(Math.max(year, FIRST_YEAR), LAST_YEAR),
    date: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
  };
}

/** GET /api/history/forecast/'s params for a period */
export function periodParams(p) {
  if (p.mode === 'date') return { date: p.date };
  if (p.mode === 'monthYear') return { month: p.month, year: p.year };
  return { month: p.month };
}

/** 1-12, the month the period falls in */
export const periodMonth = (p) => (p.mode === 'date' ? dateParts(p.date)[1] : p.month);

/** The same period moved to another month (a date keeps its day, or the month's last) */
export function withMonth(p, month) {
  if (p.mode !== 'date') return { ...p, month };
  const [y, , d] = dateParts(p.date);
  const last = new Date(y, month, 0).getDate();
  return { ...p, date: `${y}-${pad(month)}-${pad(Math.min(d, last))}` };
}

/** "November", "November 2027", "November 15, 2027" */
export function periodLabel(p) {
  if (p.mode === 'date') {
    const [y, m, d] = dateParts(p.date);
    return `${MONTHS[m - 1]} ${d}, ${y}`;
  }
  return p.mode === 'monthYear' ? `${MONTHS[p.month - 1]} ${p.year}` : MONTHS[p.month - 1];
}

/** Where in past years the counts come from: "November", "the week of Nov 15" */
export function periodIn(p) {
  if (p.mode !== 'date') return MONTHS[p.month - 1];
  const [, m, d] = dateParts(p.date);
  return `the week of ${MONTHS[m - 1].slice(0, 3)} ${d}`;
}

/** The table's column: "Past Novembers", "Past years, week of Nov 15" */
export function periodPastHeader(p) {
  return p.mode === 'date' ? `Past years, ${periodIn(p).replace('the ', '')}` : `Past ${MONTHS[p.month - 1]}s`;
}

/** "3 of 4 past Novembers", "3 of 4 past years" for the week around a date */
export function periodYearsText(row, p) {
  if (p.mode !== 'date') return yearsText(row, MONTHS[p.month - 1]);
  const n = row.years_considered;
  return `${row.years_hit} of ${n} past year${n === 1 ? '' : 's'}`;
}

export const SEVERITY_WORD = { Red: 'Extreme', Orange: 'Moderate', Green: 'Low' };

export const FORECAST_DISCLAIMER =
  'Based on how often this happened at the same time of year in past years. '
  + 'It is a heads-up for preparing, not a warning that a hazard is coming. '
  + 'Live alerts come only from the DRRMO.';
