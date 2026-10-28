import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { historyApi } from '../../api/historyApi';
import ForecastPeriodPicker from './ForecastPeriodPicker';
import {
  FORECAST_DISCLAIMER, SEVERITY_WORD, defaultPeriod, likelihoodInfo, periodIn, periodLabel, periodMonth,
  periodParams, periodPastHeader, periodYearsText, withMonth,
} from './forecastLevels';
import './forecast.css';

/**
 * Which barangays a month, a month in a given year, or the week around a
 * date has tended to hit, and with what. Pick the period; pick a barangay
 * row to see its whole year. A period that has started also shows what
 * actually happened in it.
 *
 * Rule-based seasonal statistics from the archive (backend
 * apps/history/forecast.py), not AI and not a weather forecast.
 *
 * Props:
 *   compact         dashboard card: top rows only, no month profile
 *   limit           rows shown when compact (default 5)
 *   hazard          hazard type name to narrow to, '' for all. Set by the
 *                   page's own filter (Reports › Analytics), so there is
 *                   no second hazard picker in here.
 *   excludeSamples  leave seeded sample records out (Analytics does unless
 *                   asked; the dashboard card labels them instead)
 */
export default function BarangayLikelihood({ compact = false, limit = 5, hazard = '', excludeSamples = false }) {
  const [period, setPeriod] = useState(defaultPeriod);
  const [barangay, setBarangay] = useState(null); // { id, name } for the profile
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setError('');
    historyApi.forecast({
      ...periodParams(period),
      ...(hazard ? { hazard_type_name: hazard } : {}),
      ...(barangay ? { barangay: barangay.id } : {}),
      ...(excludeSamples ? { exclude_samples: 'true' } : {}),
    })
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError('Could not load the seasonal likelihood.'); });
    return () => { cancelled = true; };
  }, [period, hazard, barangay, excludeSamples]);

  const rows = data?.results || [];
  const shown = compact ? rows.slice(0, limit) : rows;
  // What actually happened, once a period with a year has started
  const outcome = data?.outcome;

  return (
    <div className="fc">
      <div className="fc-controls">
        <ForecastPeriodPicker value={period} onChange={setPeriod} />
      </div>

      {error && <p className="db-error" role="alert">{error}</p>}

      {data?.year != null && (
        <p className="fc-note">
          {data.years.length
            ? `For ${periodLabel(period)}, from ${periodIn(period)} in ${data.years[0]}–${data.years[data.years.length - 1]}.`
            : `Nothing on record before ${periodLabel(period)} to estimate from.`}
          {outcome && (outcome.complete
            ? ` It is over: ${outcome.events} event${outcome.events === 1 ? '' : 's'} happened.`
            : ` It has started: ${outcome.events} event${outcome.events === 1 ? '' : 's'} so far.`)}
        </p>
      )}

      {data && data.limited && (
        <p className="fc-note">
          Only {data.years.length} past year{data.years.length === 1 ? '' : 's'} on record for {periodIn(period)}, so
          these levels are rough.
        </p>
      )}

      {data && !rows.length && (
        <p className="db-empty">
          No hazard has been recorded in {periodIn(period)} in the years on record.
        </p>
      )}

      {shown.length > 0 && (
        // On a narrow phone the table scrolls inside the card, never the page
        <div className="fc-table-wrap">
        <table className="fc-table">
          <thead>
            <tr>
              <th scope="col">Barangay</th>
              <th scope="col">Hazard</th>
              <th scope="col">Likelihood</th>
              <th scope="col">{periodPastHeader(period)}</th>
              {outcome && <th scope="col">{outcome.complete ? 'What happened' : 'So far'}</th>}
              {!compact && <th scope="col">Usual severity</th>}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const info = likelihoodInfo(r.level);
              const picked = barangay && barangay.id === r.barangay_id;
              return (
                <tr
                  key={`${r.barangay_id}-${r.hazard_type}`}
                  className={picked ? 'is-picked' : undefined}
                >
                  <td>
                    {compact ? r.barangay : (
                      <button
                        type="button"
                        className="fc-link"
                        onClick={() => setBarangay(picked ? null : { id: r.barangay_id, name: r.barangay })}
                        aria-pressed={picked}
                      >
                        {r.barangay}
                      </button>
                    )}
                  </td>
                  <td>{r.hazard_type}</td>
                  <td>
                    <span className="fc-badge" style={{ background: info.tint, color: info.text }}>
                      <span className="fc-dot" style={{ background: info.color }} />
                      {info.label}
                    </span>
                  </td>
                  <td>{periodYearsText(r, period)}</td>
                  {outcome && <td>{r.actual ? `${r.actual} event${r.actual === 1 ? '' : 's'}` : 'None'}</td>}
                  {!compact && <td>{SEVERITY_WORD[r.typical_severity] || '-'}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}

      {compact && rows.length > shown.length && (
        <p className="fc-more">
          <Link to="/app/reports?tab=analytics">{rows.length - shown.length} more in Reports › Analytics</Link>
        </p>
      )}

      {!compact && data?.profile && (
        <div className="fc-profile">
          <h3>
            Through the year: {barangay ? barangay.name : 'all of Talisay City'}
            {/* The type these figures were counted for, not the one just picked:
                until the new figures arrive, the old ones keep their own label */}
            {data.hazard_type ? `, ${data.hazard_type.toLowerCase()}` : ''}
          </h3>
          {!barangay && (
            <p className="fc-sub">Pick a barangay in the table to see its own year.</p>
          )}
          <ol className="fc-months">
            {data.profile.map((m) => {
              const info = likelihoodInfo(m.level);
              const height = Math.round(Math.max(m.probability, 0.03) * 100);
              return (
                <li
                  key={m.month}
                  className={m.month === periodMonth(period) ? 'is-current' : undefined}
                  title={`${m.month_name}: ${info.label} (${m.years_hit} of ${m.years_considered} years)`}
                >
                  <button type="button" onClick={() => setPeriod((p) => withMonth(p, m.month))} aria-label={`${m.month_name}, ${info.label}`}>
                    <span className="fc-bar-wrap">
                      <span className="fc-bar" style={{ height: `${height}%`, background: info.color }} />
                    </span>
                    <span className="fc-month">{m.month_name.slice(0, 3)}</span>
                  </button>
                </li>
              );
            })}
          </ol>
          <p className="fc-sub">Bar height is the share of past years with at least one event in that month.</p>
        </div>
      )}

      <p className="fc-note">{FORECAST_DISCLAIMER}</p>
      {data?.basis?.sample_records > 0 && (
        <p className="fc-note">
          {data.basis.sample_records} of the {data.basis.records} records behind this are sample data
          made for testing.
        </p>
      )}

      {!compact && (
        <details className="db-method">
          <summary>How this is calculated</summary>
          <p>
            For each barangay and hazard type, the system looks at the same month in each past year
            on the record (up to ten years), or for an exact date the week around it (three days
            either side), and counts the years that had at least one event. With a year picked, only
            the years before it count, so a past period can be checked against what happened. A year
            counts half as much for every three years back, so recent seasons matter more. At least
            60% of years, or two or more events expected in the month, is High; at least 30% is
            Moderate; anything less that still happened is Low. It is plain counting, with no AI or
            machine learning, and every figure can be checked against the archived records on the
            History page.
          </p>
        </details>
      )}
    </div>
  );
}
