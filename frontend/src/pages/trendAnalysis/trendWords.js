// Plain words for Trend Analysis, shared by the screen and its CSV. Every
// sentence is built from the numbers the server counted; a direction is only
// named when the server's test found one (5 or more full years, no gaps).

export const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const MONTH = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December'];

export const STATUS = {
  increasing: 'Going up',
  decreasing: 'Going down',
  no_clear_trend: 'No steady change',
  too_few_years: 'Not enough years yet',
  gaps: 'Gaps in the records',
};

export const RECURRENCE = {
  every_year: 'Every year',
  most_years: 'Most years',
  some_years: 'Some years',
  latest_only: 'Only last year',
  none: 'None',
  too_few_years: 'Not enough years yet',
};

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** The one-line explanation under a hazard's status. */
export function plainSentence(h) {
  const n = h.complete_years;
  const name = h.hazard.toLowerCase();
  let text;
  if (h.verdict === 'too_few_years') {
    text = `We need at least 5 full years of records to tell whether the number of ${name} events is changing; `
      + `there ${n === 1 ? 'is' : 'are'} ${n} so far.`;
  } else if (h.verdict === 'gaps') {
    text = 'Some years have no records, which may be missing data, so we cannot tell whether the number is changing.';
  } else if (h.verdict === 'no_clear_trend') {
    text = `Over ${plural(n, 'full year')} the number goes up and down without a steady change.`;
  } else {
    const way = h.verdict === 'increasing' ? 'up' : 'down';
    text = `Over ${plural(n, 'full year')} the number has gone ${way} steadily, by about `
      + `${Math.abs(h.slope).toLocaleString(undefined, { maximumFractionDigits: 1 })} a year.`;
  }
  if (h.quiet_since) text += ` No records since ${h.quiet_since}; this may be missing data.`;
  return text;
}

/** "7% fewer than the years before (59 a year)", or null when there is nothing to compare */
export function changeLine(change) {
  if (!change || change.pct === null || change.pct === undefined) return null;
  const before = `the years before (${change.earlier_mean.toLocaleString(undefined, { maximumFractionDigits: 1 })} a year)`;
  if (Math.abs(change.pct) < 5) return `About the same as ${before}`;
  return `${Math.abs(change.pct)}% ${change.pct > 0 ? 'more' : 'fewer'} than ${before}`;
}

/** The last full year shown for a hazard, or null. */
export function lastYear(h) {
  const years = h.years || [];
  return years.length ? years[years.length - 1] : null;
}

/** "April 2025: 14 fire events. April usually has 3 to 8." */
export function stoodOut(m) {
  const month = MONTH[m.month - 1];
  const usual = m.baseline_min === m.baseline_max ? `${m.baseline_min}` : `${m.baseline_min} to ${m.baseline_max}`;
  return `${month} ${m.year}: ${plural(m.count, `${m.hazard.toLowerCase()} event`)}. ${month} usually has ${usual}.`;
}

/** "Fire: most often in January (13.5 a year on average)" for each hazard with a covered month. */
export function peakLines(monthAverage = []) {
  return monthAverage.flatMap((a) => {
    let best = null;
    a.months.forEach((v, i) => { if (v !== null && v > 0 && (best === null || v > a.months[best])) best = i; });
    if (best === null) return [];
    const value = a.months[best].toLocaleString(undefined, { maximumFractionDigits: 1 });
    return [`${a.hazard}: most often in ${MONTH[best]} (${value} a year on average)`];
  });
}

/** "Every year (5 of 5 years)" */
export function howOften(row, fullYears) {
  const word = RECURRENCE[row.recurrence] || '—';
  if (row.recurrence === 'none' || row.recurrence === 'too_few_years') return word;
  return `${word} (${row.years_with_events} of ${fullYears} years)`;
}

/** The hazard with the most events in a hazard-mix row, or '—'. */
export function mostCommon(counts = {}) {
  let best = null;
  Object.entries(counts).forEach(([name, n]) => { if (n > 0 && (best === null || n > counts[best])) best = name; });
  return best || '—';
}
