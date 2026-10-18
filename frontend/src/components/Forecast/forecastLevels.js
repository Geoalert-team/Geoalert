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

export const SEVERITY_WORD = { Red: 'Extreme', Orange: 'Moderate', Green: 'Low' };

export const FORECAST_DISCLAIMER =
  'Based on how often this happened in the same month in past years. '
  + 'It is a heads-up for preparing, not a warning that a hazard is coming. '
  + 'Live alerts come only from the DRRMO.';
