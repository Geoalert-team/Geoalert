/**
 * Seasonal risk outlook for Talisay City, computed from archived hazard
 * records. Rule-based statistics only — no model, no training, nothing
 * learned. Every number here can be recomputed by hand from the records
 * table, which is the point: it has to be explainable at defense.
 *
 * The method, in one line: for each calendar month, how often has a hazard
 * been recorded in that month per year observed, compared with the overall
 * monthly average?
 */

export const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const SHORT_MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

// How far above or below the overall monthly average a month has to sit
// before it's worth calling out. Deliberately coarse — with a handful of
// records, finer bands would be reading noise.
const ELEVATED_AT = 1.5;
const TYPICAL_AT = 0.75;

function barangayOf(record) {
  return (
    record.barangay_detail?.name ||
    record.barangay_details?.name ||
    record.barangay_name ||
    'Unspecified barangay'
  );
}

function hazardOf(record) {
  return (
    record.hazard_type_detail?.name ||
    record.hazard_type_details?.name ||
    record.hazard_type_name ||
    'Hazard'
  );
}

function levelFor(index) {
  if (index >= ELEVATED_AT) return 'Elevated';
  if (index >= TYPICAL_AT) return 'Typical';
  return 'Lower';
}

/**
 * @param records  array of HistoricalRecord objects straight from the API
 * @param options  { now?: Date, horizon?: number }  horizon = months ahead
 * @returns null when there is nothing on record, otherwise the outlook
 */
export function buildRiskOutlook(records, options = {}) {
  const now = options.now ? new Date(options.now) : new Date();
  const horizon = options.horizon ?? 3;

  const rows = (records || [])
    .map((r) => ({
      date: new Date(r.occurred_at),
      barangay: barangayOf(r),
      hazard: hazardOf(r),
      severity: r.severity_level,
    }))
    .filter((r) => !Number.isNaN(r.date.getTime()))
    .sort((a, b) => a.date - b.date);

  if (rows.length === 0) return null;

  const earliest = rows[0].date;
  const latest = rows[rows.length - 1].date;

  // The observation window runs from the first record up to today, not up to
  // the last record. A quiet stretch since the last event is real evidence of
  // quiet, and leaving it out would inflate every rate.
  const windowEnd = latest > now ? latest : now;

  // Walk the window month by month and tally how many times each calendar
  // month has been observed. February observed twice means a February event
  // count of 2 is one per year, not two.
  const observations = new Array(12).fill(0);
  let spanMonths = 0;
  const cursor = new Date(earliest.getFullYear(), earliest.getMonth(), 1);
  const end = new Date(windowEnd.getFullYear(), windowEnd.getMonth(), 1);
  while (cursor <= end && spanMonths < 1200) {
    observations[cursor.getMonth()] += 1;
    spanMonths += 1;
    cursor.setMonth(cursor.getMonth() + 1);
  }

  const eventsByMonth = new Array(12).fill(0);
  rows.forEach((r) => { eventsByMonth[r.date.getMonth()] += 1; });

  const baselineRate = spanMonths > 0 ? rows.length / spanMonths : 0;

  // ---- Months ahead -------------------------------------------------------
  const lookahead = [];
  for (let step = 0; step < horizon; step += 1) {
    const target = new Date(now.getFullYear(), now.getMonth() + step, 1);
    const m = target.getMonth();
    const years = observations[m] || 0;
    const past = eventsByMonth[m];
    const expected = years > 0 ? past / years : 0;
    const index = baselineRate > 0 ? expected / baselineRate : 0;

    lookahead.push({
      key: `${target.getFullYear()}-${m}`,
      month: m,
      label: `${SHORT_MONTHS[m]} ${target.getFullYear()}`,
      name: MONTH_NAMES[m],
      isCurrent: step === 0,
      pastEvents: past,
      yearsObserved: years,
      expected: Math.round(expected * 10) / 10,
      index: Math.round(index * 100) / 100,
      level: years > 0 ? levelFor(index) : 'No history',
    });
  }

  // ---- Who to watch in the nearest elevated month -------------------------
  const focus = lookahead.find((l) => l.level === 'Elevated') || lookahead[0];
  const inFocusMonth = rows.filter((r) => r.date.getMonth() === focus.month);

  const tally = (list, key) => {
    const counts = new Map();
    list.forEach((r) => counts.set(r[key], (counts.get(r[key]) || 0) + 1));
    return [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  };

  const watchlist = tally(inFocusMonth, 'barangay').slice(0, 4);
  const likelyHazards = tally(inFocusMonth, 'hazard').slice(0, 3);

  // ---- Direction of travel, last 12 months vs the 12 before ---------------
  const cut1 = new Date(now); cut1.setFullYear(cut1.getFullYear() - 1);
  const cut2 = new Date(cut1); cut2.setFullYear(cut2.getFullYear() - 1);

  let trend = { direction: 'Not enough history yet', recent: null, previous: null };
  if (spanMonths >= 24) {
    const recent = rows.filter((r) => r.date > cut1).length;
    const previous = rows.filter((r) => r.date > cut2 && r.date <= cut1).length;
    trend = {
      direction: recent > previous ? 'Rising' : recent < previous ? 'Falling' : 'Stable',
      recent,
      previous,
    };
  }

  // ---- Seasonality, as a peak-month list ----------------------------------
  const perYear = eventsByMonth.map((count, m) => (observations[m] ? count / observations[m] : 0));
  const peak = Math.max(...perYear);
  const peakMonths = peak > 0
    ? perYear.map((rate, m) => ({ rate, m })).filter((x) => x.rate === peak).map((x) => MONTH_NAMES[x.m])
    : [];

  // ---- How much to trust any of the above ---------------------------------
  let confidence;
  if (spanMonths >= 24 && rows.length >= 24) {
    confidence = {
      level: 'Reasonable',
      note: `Based on ${rows.length} records across ${Math.floor(spanMonths / 12)} years.`,
    };
  } else if (spanMonths >= 12 && rows.length >= 8) {
    confidence = {
      level: 'Indicative',
      note: `Only ${rows.length} records over ${spanMonths} months — treat month-to-month differences loosely.`,
    };
  } else {
    confidence = {
      level: 'Baseline still building',
      note: `${rows.length} record${rows.length === 1 ? '' : 's'} over ${spanMonths} month${spanMonths === 1 ? '' : 's'} is too little to call a season. The outlook firms up as hazards are resolved and archived.`,
    };
  }

  const redCount = rows.filter((r) => r.severity === 'Red').length;

  return {
    totalRecords: rows.length,
    spanMonths,
    from: earliest,
    to: windowEnd,
    baselineRate: Math.round(baselineRate * 100) / 100,
    lookahead,
    focus,
    watchlist,
    likelyHazards,
    trend,
    peakMonths,
    confidence,
    redShare: rows.length ? Math.round((redCount / rows.length) * 100) : 0,
  };
}