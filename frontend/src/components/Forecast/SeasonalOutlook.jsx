import React, { useEffect, useMemo, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import { buildRiskOutlook } from '../../utils/riskOutlook';

/**
 * What the next three months have historically brought, from the whole
 * archive of resolved hazards (utils/riskOutlook.js). Moved here from the
 * History page, which is now the archive only.
 *
 * It follows the Analytics hazard filter but not its period: a seasonal
 * pattern needs every past year, so the sub line says so. Sample records
 * are left out unless the officer asked for them, like every other figure
 * on the tab.
 *
 * Props:
 *   hazardTypeId    hazard type id as a string, '' for all types
 *   hazardName      that type's name for the sub line, or null
 *   includeSamples  keep seeded sample records
 */
export default function SeasonalOutlook({ hazardTypeId = '', hazardName = null, includeSamples = false }) {
  const [records, setRecords] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setError('');
    historyApi.list(hazardTypeId ? { hazard_type: hazardTypeId } : {})
      .then((list) => { if (!cancelled) setRecords(Array.isArray(list) ? list : (list?.results || [])); })
      .catch(() => { if (!cancelled) setError('The seasonal outlook could not be loaded right now.'); });
    return () => { cancelled = true; };
  }, [hazardTypeId]);

  const outlook = useMemo(() => {
    if (!records) return null;
    return buildRiskOutlook(includeSamples ? records : records.filter((r) => !r.is_sample));
  }, [records, includeSamples]);

  return (
    <>
      <h2>Seasonal outlook</h2>
      <p className="db-card-sub">
        From the whole archive for {hazardName || 'all hazard types'}. The period above does not apply.
      </p>

      {error && <p className="db-error" role="alert">{error}</p>}
      {!error && !records && <p className="db-empty">Loading the outlook…</p>}

      {!error && records && !outlook && (
        <p className="db-empty">
          No archived events match these filters yet, so there is nothing to project from.
          Records appear here once DRRMO resolves a hazard zone.
        </p>
      )}

      {!error && outlook && (
        <>
          <p className="an-outlook-summary">
            Extreme severity share: <strong>{outlook.redShare}%</strong>
            {' · '}Outlook for {outlook.focus.name}: <strong>{outlook.focus.level}</strong>
          </p>

          <span className="db-badge" data-level={outlook.confidence.level}>
            <span className="db-badge-dot" />
            {outlook.confidence.level}
          </span>

          <div className="db-outlook-grid">
            {outlook.lookahead.map((m) => (
              <div key={m.key} className="db-outlook-card" data-level={m.level}>
                <div className="db-outlook-month">{m.label}{m.isCurrent ? ' · now' : ''}</div>
                <div className="db-outlook-level">{m.level}</div>
                <div className="db-outlook-detail">
                  {m.yearsObserved > 0 ? (
                    <>
                      {m.expected} event{m.expected === 1 ? '' : 's'} expected
                      <br />
                      {m.pastEvents} recorded over {m.yearsObserved} {m.name}
                      {m.yearsObserved === 1 ? '' : 's'} observed
                    </>
                  ) : (
                    <>No {m.name} on record yet</>
                  )}
                </div>
              </div>
            ))}
          </div>

          <ul className="db-outlook">
            <li>
              <strong>Watch in {outlook.focus.name}:</strong>{' '}
              {outlook.watchlist.length
                ? outlook.watchlist.map((b) => `${b.name} (${b.count})`).join(', ')
                : `no ${outlook.focus.name} events on record yet`}
            </li>
            <li>
              <strong>Most likely type:</strong>{' '}
              {outlook.likelyHazards.length
                ? outlook.likelyHazards.map((h) => `${h.name} (${h.count})`).join(', ')
                : 'nothing recorded for this month'}
            </li>
            <li>
              <strong>Peak season:</strong>{' '}
              {outlook.peakMonths.length ? outlook.peakMonths.join(', ') : 'not yet identifiable'}
            </li>
            <li>
              <strong>Direction:</strong> {outlook.trend.direction}
              {outlook.trend.recent !== null && (
                <> ({outlook.trend.recent} in the last 12 months vs {outlook.trend.previous} in the 12 before)</>
              )}
            </li>
            <li>
              <strong>Overall rate:</strong> {outlook.baselineRate} events per month across{' '}
              {outlook.spanMonths} month{outlook.spanMonths === 1 ? '' : 's'} of records
            </li>
          </ul>

          <p className="db-note">
            {outlook.confidence.note} This is a statistical pattern drawn from archived
            records — not a weather forecast and not an AI prediction. It says what this
            month has tended to bring, not what will happen.
          </p>

          <details className="db-method">
            <summary>How this is calculated</summary>
            <p>
              For each calendar month, the system counts the archived events that occurred
              in that month and divides by the number of times that month has been observed
              since the first record, giving the events expected per occurrence of that
              month. That figure is compared against the overall average of{' '}
              {outlook.baselineRate} events per month. A month at 1.5&times; the average or
              above is marked Elevated, 0.75&times; to 1.5&times; is Typical, and below
              0.75&times; is Lower. The observation window runs from the earliest record up
              to today, so quiet stretches count as evidence of quiet.
            </p>
          </details>
        </>
      )}
    </>
  );
}
