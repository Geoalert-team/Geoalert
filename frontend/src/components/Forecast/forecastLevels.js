// Likelihood levels from GET /api/history/forecast/: a trained model for each hazard
// (fire from past fires; flood and landslide from rain and terrain), and a combined
// chance of any of them. Shown as a heads-up, never as an alert.

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

/** "23%" on a model's row; counting has no chance to give, only a share of years */
export const chanceText = (row) => (row.method === 'model' ? `${Math.round(row.probability * 100)}%` : '');

const HAZARD_ORDER = ['Fire', 'Flood', 'Landslide'];

/** The forecast's `hazards` parameter: "Fire,Landslide", in a fixed order */
export const hazardsParam = (types) => {
  const picked = new Set(types);
  return HAZARD_ORDER.filter((t) => picked.has(t)).join(',');
};

/** The forecast's combined rows by barangay id (as a string), for colouring the map */
export const combinedByBarangay = (likely) => new Map(
  (likely?.combined || []).map((r) => [String(r.barangay_id), r]),
);

/**
 * Identity of a forecast response for the map's layer key: changes whenever what the
 * tooltips would say changes (not just the row counts), so a response that lands after a
 * layer or period switch rebuilds them.
 */
export const likelyKey = (likely) => {
  if (!likely) return 'none';
  const c = (likely.combined || []).map((r) => `${r.barangay_id}:${r.probability}:${r.level}`).join(',');
  const r = (likely.results || [])
    .map((x) => `${x.barangay_id}:${x.hazard_type}:${x.method}:${x.level}:${x.probability}:${x.rain_years ?? ''}:${x.actual ?? ''}`)
    .join(',');
  return `${likely.error ? 'err' : 'ok'}|${c}|${r}`;
};

const percent = (p) => `${Math.round(p * 100)}%`;

/** A model's chance as text; a positive chance under 0.5% reads "under 1%", never "0%"; '' for no probability */
export const smallChanceText = (p) => {
  if (p == null) return '';
  if (p > 0 && p < 0.005) return 'under 1%';
  return chanceText({ method: 'model', probability: p });
};

/** The same with "about" before the figure: "about 3%", "under 1%" */
export const aboutChanceText = (p) => {
  if (p == null) return '';
  if (p > 0 && p < 0.005) return 'under 1%';
  return `about ${smallChanceText(p)}`;
};

/** The scenario years a model used: "8 past rain years (2018–2025)", "3 past rain years (2018, 2020 and 2023)" */
export const rainYearsText = (years) => {
  if (!Array.isArray(years) || !years.length) return '';
  const ys = [...new Set(years)].sort((a, b) => a - b);
  const n = ys.length;
  const noun = `${n} past rain year${n === 1 ? '' : 's'}`;
  if (n === 1) return `${noun} (${ys[0]})`;
  if (ys[n - 1] - ys[0] === n - 1) return `${noun} (${ys[0]}–${ys[n - 1]})`;
  return `${noun} (${ys.slice(0, -1).join(', ')} and ${ys[n - 1]})`;
};

// The hazards in a row's `missing` that the response names in `unavailable_hazards`. A hazard
// can be missing only because nothing is on record (fire on counting in a past period); that
// is not "unavailable".
const unavailableMissing = (row, unavailable) => {
  const named = new Set(unavailable || []);
  return new Set((row.missing || []).filter((h) => named.has(h)));
};

/**
 * A combined row's breakdown in its own order: "Fire 8% · Flood 3% · Landslide 30%".
 * `unavailable` is the response's `unavailable_hazards` (an array or Set). A hazard in the row's
 * `missing` that it names reads "Flood unavailable"; any other entry with no chance is left out.
 */
export const combinedText = (row, unavailable = []) => {
  const down = unavailableMissing(row, unavailable);
  return (row.hazards || [])
    .map((h) => {
      if (h.probability != null) return `${h.hazard_type} ${smallChanceText(h.probability)}`;
      return down.has(h.hazard_type) ? `${h.hazard_type} unavailable` : '';
    })
    .filter(Boolean)
    .join(' · ');
};

/**
 * True when a combined row has no chance because a hazard the response names in
 * `unavailable_hazards` is missing from it: it reads "Unavailable right now", not "None on record".
 */
export const combinedUnavailable = (row, unavailable = []) => row.probability == null
  && unavailableMissing(row, unavailable).size > 0;

// "Flood", "Flood and Landslide", "Fire, Flood and Landslide"
const namesText = (names) => (names.length > 1
  ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
  : names.join(''));

/**
 * The note beside an All hazards chance when the response names a shown hazard in
 * `unavailable_hazards`; `included` is an array or Set of hazard names. '' when there is none.
 */
export const unavailableNote = (likely, included) => {
  const shown = new Set(included || []);
  const unavailable = new Set(likely?.unavailable_hazards || []);
  const names = HAZARD_ORDER.filter((h) => unavailable.has(h) && shown.has(h));
  return names.length
    ? `Unavailable right now in some or all barangays, and left out of their All hazards chance: ${namesText(names)}.`
    : '';
};

const underOnePercent = (p) => p > 0 && p < 0.005;

/**
 * What a model row's chance was across the past rain years: "3–41% across past rain years";
 * a positive end under 0.5% reads "under 1%", never 0%. An exact 0 stays "0–4%".
 */
export const rangeText = (row) => {
  const [low, high] = row.range;
  if (underOnePercent(low) && underOnePercent(high)) return 'under 1% across past rain years';
  if (underOnePercent(low)) return `under 1% to ${percent(high)} across past rain years`;
  return `${Math.round(low * 100)}–${percent(high)} across past rain years`;
};

/** The level's word; a model that could not run is not "None on record" */
export const levelLabel = (row) => (row.method === 'unavailable' ? 'Unavailable right now' : likelihoodInfo(row.level).label);

export const MODEL_LABELS = { logistic_regression: 'logistic regression', random_forest: 'random forest', xgboost: 'XGBoost' };

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

/** The table's column: "On record in past Novembers", "On record in past years, week of Nov 15" */
export function periodPastHeader(p) {
  return p.mode === 'date'
    ? `On record in past years, ${periodIn(p).replace('the ', '')}`
    : `On record in past ${MONTHS[p.month - 1]}s`;
}

/** "3 of 4 past Novembers", "3 of 4 past years" for the week around a date */
export function periodYearsText(row, p) {
  if (p.mode !== 'date') return yearsText(row, MONTHS[p.month - 1]);
  const n = row.years_considered;
  return `${row.years_hit} of ${n} past year${n === 1 ? '' : 's'}`;
}

export const SEVERITY_WORD = { Red: 'Extreme', Orange: 'Moderate', Green: 'Low' };

export const FORECAST_DISCLAIMER =
  'Fire is estimated from past fires; flood and landslide from rain and terrain in past years. '
  + 'It is a heads-up for preparing, not a warning that a hazard is coming. '
  + 'Live alerts come only from the DRRMO.';

// Required beside any place Open-Meteo data are shown (CC BY 4.0)
export const RAIN_ATTRIBUTION = {
  text: 'Rain data by Open-Meteo.com (CC BY 4.0), processed into hazard chances by GeoAlert',
  links: [
    { label: 'Open-Meteo.com', href: 'https://open-meteo.com/' },
    { label: 'CC BY 4.0', href: 'https://creativecommons.org/licenses/by/4.0/' },
  ],
};

export const IN_TRAINING_NOTE =
  'The model learned from this period; see the accuracy check for results on years it never saw.';
