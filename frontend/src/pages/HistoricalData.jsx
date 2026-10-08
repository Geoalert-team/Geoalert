import React, { useEffect, useMemo, useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { historyApi } from '../api/historyApi';
import { barangaysApi } from '../api/barangaysApi';
import { hazardsApi } from '../api/hazardsApi';
import { buildRiskOutlook } from '../utils/riskOutlook';
import './css/Dashboard.css';

const SEVERITY = {
  Red:    { label: 'Extreme',  color: 'var(--db-high)' },
  Orange: { label: 'Moderate', color: 'var(--db-medium)' },
  Green:  { label: 'Low',      color: 'var(--db-low)' },
};

// A blank count in the archive means "nobody counted", which is not zero.
// Printing it as 0 would quietly turn an uncounted incident into a
// casualty-free one.
function countText(label, value) {
  if (value === null || value === undefined) return `${label}: not counted`;
  return `${label}: ${Number(value).toLocaleString()}`;
}

function BarList({ rows, labelKey, colorFor }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="db-bars">
      {rows.map((r) => (
        <div key={r[labelKey]} className="db-bar-row">
          <span>{r.display || r[labelKey]}</span>
          <div className="db-bar-track">
            <div
              className="db-bar-fill"
              style={{ width: `${(r.count / max) * 100}%`, background: colorFor ? colorFor(r) : undefined }}
            />
          </div>
          <span className="db-bar-count">{r.count}</span>
        </div>
      ))}
    </div>
  );
}

export default function HistoricalData() {
  const [records, setRecords] = useState([]);
  const [trends, setTrends] = useState(null);
  const [barangays, setBarangays] = useState([]);
  const [hazardTypes, setHazardTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [hazardId, setHazardId] = useState('');
  const [barangayId, setBarangayId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    barangaysApi.list()
      .then((geo) => setBarangays(
        (geo.features || []).map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name }))
      ))
      .catch(() => {});

    // Read hazard types from the API instead of hardcoding 1/2/3 — the
    // seeded IDs won't survive a reseed, and new types are expected.
    hazardsApi.types()
      .then((types) => setHazardTypes(types || []))
      .catch(() => setHazardTypes([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const params = {};
    if (hazardId)   params.hazard_type = hazardId;
    if (barangayId) params.barangay = barangayId;
    if (dateFrom)   params.date_from = dateFrom;
    if (dateTo)     params.date_to = `${dateTo}T23:59:59`;

    setLoading(true);
    setError('');
    Promise.all([historyApi.list(params), historyApi.trends(params)])
      .then(([list, t]) => {
        if (cancelled) return;
        setRecords(Array.isArray(list) ? list : (list?.results || []));
        setTrends(t);
      })
      .catch(() => { if (!cancelled) setError('Could not load historical records. Please try again.'); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [hazardId, barangayId, dateFrom, dateTo]);

  const outlook = useMemo(() => buildRiskOutlook(records), [records]);

  const hazardTabs = [{ id: '', name: 'All types' }, ...hazardTypes.map((t) => ({ id: t.id, name: t.name }))];

  const monthRows = (trends?.by_month || []).map((m) => ({
    month: m.month,
    display: new Date(m.month).toLocaleDateString(undefined, { month: 'short', year: 'numeric' }),
    count: m.count,
  }));
  const severityRows = (trends?.by_severity || []).map((s) => ({
    ...s, display: `${SEVERITY[s.severity_level]?.label || s.severity_level}`,
  }));

  const scopeLabel = hazardId
    ? (hazardTypes.find((t) => String(t.id) === String(hazardId))?.name || 'this hazard type')
    : 'all hazard types';

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Historical data and trends</h1>
          <p>Archived hazard events in Talisay City, with a rule-based seasonal outlook.</p>
        </div>

        <div className="db-tabs" role="tablist">
          {hazardTabs.map((h) => (
            <button
              key={h.name} type="button" role="tab" aria-selected={String(hazardId) === String(h.id)}
              className={`db-tab ${String(hazardId) === String(h.id) ? 'is-active' : ''}`}
              onClick={() => setHazardId(h.id)}
            >
              {h.name}
            </button>
          ))}
        </div>

        <div className="db-filters">
          <label className="db-field">Barangay
            <select value={barangayId} onChange={(e) => setBarangayId(e.target.value)}>
              <option value="">All barangays</option>
              {barangays.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          <label className="db-field">From
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="db-field">To
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
        </div>

        {error && <p className="db-empty">{error}</p>}

        {!error && (
          <>
            <div className="db-stats">
              <div className="db-stat">
                <div className="db-stat-value">{trends?.total_records ?? 0}</div>
                <div className="db-stat-label">Events on record</div>
              </div>
              <div className="db-stat">
                <div className="db-stat-value">{outlook ? `${outlook.redShare}%` : '-'}</div>
                <div className="db-stat-label">Extreme severity share</div>
              </div>
              <div className="db-stat">
                <div className="db-stat-value">{outlook ? outlook.focus.level : '-'}</div>
                <div className="db-stat-label">Outlook, {outlook ? outlook.focus.name : 'this month'}</div>
              </div>
            </div>

            {/* ---------- Forward-looking outlook ---------- */}
            <div className="db-card">
              <h2>Seasonal risk outlook</h2>
              <p className="db-card-sub">
                What the next three months have historically brought, for {scopeLabel}
              </p>

              {outlook ? (
                <>
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
              ) : (
                <p className="db-empty">
                  No archived events match these filters yet, so there is nothing to project from.
                  Records appear here once DRRMO resolves a hazard zone.
                </p>
              )}
            </div>

            <div className="db-grid-2">
              <div className="db-card">
                <h2>Events by month</h2>
                <p className="db-card-sub">How often hazards were recorded over time</p>
                {monthRows.length ? <BarList rows={monthRows} labelKey="month" /> : <p className="db-empty">No data for this filter.</p>}
              </div>
              <div className="db-card">
                <h2>Most affected barangays</h2>
                <p className="db-card-sub">Top barangays by recorded events</p>
                {trends?.by_barangay?.length
                  ? <BarList rows={trends.by_barangay} labelKey="barangay__name" />
                  : <p className="db-empty">No data for this filter.</p>}
              </div>
            </div>

            <div className="db-card">
              <h2>Severity distribution</h2>
              <p className="db-card-sub">Share of events by severity level</p>
              {severityRows.length
                ? <BarList rows={severityRows} labelKey="severity_level" colorFor={(r) => SEVERITY[r.severity_level]?.color} />
                : <p className="db-empty">No data for this filter.</p>}
            </div>

            <div className="db-card">
              <h2>Records</h2>
              <p className="db-card-sub">
                {records.length} historical record{records.length === 1 ? '' : 's'}
              </p>
              {loading ? (
                <p style={{ color: 'var(--db-soft)' }}>Loading...</p>
              ) : records.length === 0 ? (
                <p className="db-empty">No records match these filters.</p>
              ) : (
                <div className="db-list">
                  {records.map((r) => (
                    <div key={r.id} className="db-item">
                      <div className="db-item-head">
                        <span className="db-item-title">
                          {r.hazard_type_detail?.name} - {r.barangay_detail?.name}
                        </span>
                        <span
                          className="db-item-meta"
                          style={{ color: SEVERITY[r.severity_level]?.color, fontWeight: 600 }}
                        >
                          {SEVERITY[r.severity_level]?.label || r.severity_level}
                        </span>
                      </div>
                      <div className="db-item-meta">{r.description}</div>
                      <div className="db-item-meta">
                        {new Date(r.occurred_at).toLocaleDateString()}
                        {' · '}{countText('Casualties', r.total_casualties)}
                        {' · '}{countText('Displaced', r.total_displaced)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}