import React, { useEffect, useRef, useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { reportsApi } from '../api/reportApi';
import { barangaysApi } from '../api/barangaysApi';
import { hazardsApi } from '../api/hazardsApi';
import './css/Dashboard.css';

const TYPES = [
  {
    key: 'hazard-summary',
    label: 'Hazard Summary',
    blurb: 'Total occurrences, breakdown by hazard type, severity distribution and affected barangays.',
    usesHazardType: true,
  },
  {
    key: 'response-status',
    label: 'Response Status',
    blurb: 'Active, resolved and archived hazards, with alerts issued and their severities.',
    usesHazardType: false,
  },
];

const SEVERITY_LABEL = { Red: 'Extreme', Orange: 'Moderate', Green: 'Low' };
const SEVERITY_VAR = { Red: 'var(--db-high)', Orange: 'var(--db-medium)', Green: 'var(--db-low)' };

// Anything slower than this and we tell the user rather than leaving them
// watching a spinner, as the spec asks.
const SLOW_MS = 8000;

function BarList({ rows, labelKey, colorFor }) {
  if (!rows?.length) return <p className="db-empty">Nothing to show.</p>;
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="db-bars">
      {rows.map((r) => (
        <div key={r[labelKey] ?? 'unspecified'} className="db-bar-row">
          <span>{r.display || r[labelKey] || 'Unspecified'}</span>
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

function Stat({ value, label }) {
  return (
    <div className="db-stat">
      <div className="db-stat-value">{value ?? '—'}</div>
      <div className="db-stat-label">{label}</div>
    </div>
  );
}

export default function Reports() {
  const [type, setType] = useState('hazard-summary');
  const [barangays, setBarangays] = useState([]);
  const [hazardTypes, setHazardTypes] = useState([]);

  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [barangay, setBarangay] = useState('');
  const [hazardType, setHazardType] = useState('');

  const [report, setReport] = useState(null);
  const [notEnough, setNotEnough] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const slowTimer = useRef(null);

  const current = TYPES.find((t) => t.key === type);

  useEffect(() => {
    barangaysApi.list()
      .then((geo) => setBarangays(
        (geo.features || []).map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name })),
      ))
      .catch(() => setBarangays([]));

    hazardsApi.types()
      .then((list) => setHazardTypes(Array.isArray(list) ? list : list?.results || []))
      .catch(() => setHazardTypes([]));

    return () => clearTimeout(slowTimer.current);
  }, []);

  function clearFilters() {
    setDateFrom(''); setDateTo(''); setBarangay(''); setHazardType('');
  }

  async function generate(e) {
    e?.preventDefault();
    setBusy(true);
    setSlow(false);
    setError('');
    setNotEnough('');
    setReport(null);

    clearTimeout(slowTimer.current);
    slowTimer.current = setTimeout(() => setSlow(true), SLOW_MS);

    const params = {};
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = `${dateTo}T23:59:59`;
    if (barangay) params.barangay = barangay;
    if (hazardType && current.usesHazardType) params.hazard_type = hazardType;

    try {
      const data = type === 'hazard-summary'
        ? await reportsApi.hazardSummary(params)
        : await reportsApi.responseStatus(params);

      // Both endpoints answer 200 with an { error } body when the filters
      // match nothing, so an empty result isn't a failed request.
      if (data?.error) setNotEnough(data.error);
      else setReport(data);
    } catch (err) {
      setError(
        err?.status === 403
          ? 'You do not have permission to access this report. Please contact your System Administrator.'
          : 'Unable to generate report at this time. Please try again later.',
      );
    } finally {
      clearTimeout(slowTimer.current);
      setSlow(false);
      setBusy(false);
    }
  }

  const filtersOn = dateFrom || dateTo || barangay || hazardType;

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Reports</h1>
          <p>Summaries of hazard activity and response for planning and decision-making.</p>
        </div>

        {/* ---------- Choose a report ---------- */}
        <div className="db-card db-no-print">
          <h2>Report type</h2>
          <p className="db-card-sub">Pick what you need, then set the range.</p>

          <div className="db-report-types">
            {TYPES.map((t) => (
              <button
                key={t.key}
                type="button"
                className={`db-report-type ${type === t.key ? 'is-active' : ''}`}
                aria-pressed={type === t.key}
                onClick={() => { setType(t.key); setReport(null); setNotEnough(''); setError(''); }}
              >
                <strong>{t.label}</strong>
                <small>{t.blurb}</small>
              </button>
            ))}
          </div>

          <form onSubmit={generate}>
            <div className="db-filters" style={{ marginTop: 18 }}>
              <label className="db-field">From
                <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              </label>
              <label className="db-field">To
                <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
              </label>
              <label className="db-field">Barangay
                <select value={barangay} onChange={(e) => setBarangay(e.target.value)}>
                  <option value="">All barangays</option>
                  {barangays.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              </label>
              {current.usesHazardType && (
                <label className="db-field">Hazard type
                  <select value={hazardType} onChange={(e) => setHazardType(e.target.value)}>
                    <option value="">All hazard types</option>
                    {hazardTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </label>
              )}
            </div>

            {dateFrom && dateTo && dateFrom > dateTo && (
              <p className="db-error" role="alert">The start date is after the end date.</p>
            )}

            <div className="db-btn-row">
              <button
                className="db-btn db-btn-primary"
                disabled={busy || (dateFrom && dateTo && dateFrom > dateTo)}
              >
                {busy ? 'Generating…' : 'Generate report'}
              </button>
              {filtersOn && (
                <button type="button" className="db-btn db-btn-outline" onClick={clearFilters} disabled={busy}>
                  Clear filters
                </button>
              )}
            </div>
          </form>

          {slow && (
            <p className="db-callout" style={{ marginTop: 14 }}>
              Report generation is taking longer than expected. Please wait or simplify the criteria.
            </p>
          )}
        </div>

        {/* ---------- Results ---------- */}
        {error && <div className="db-card"><p className="db-error" role="alert">{error}</p></div>}

        {notEnough && (
          <div className="db-card">
            <p className="db-empty">{notEnough}</p>
          </div>
        )}

        {report && (
          <div className="db-card db-report">
            <div className="db-item-head">
              <div>
                <h2>{report.report_type}</h2>
                <p className="db-card-sub" style={{ marginBottom: 0 }}>
                  Generated by {report.generated_by}
                  {report.generated_at && ` · ${new Date(report.generated_at).toLocaleString()}`}
                  {' · '}
                  {dateFrom || dateTo
                    ? `${dateFrom || 'earliest'} to ${dateTo || 'today'}`
                    : 'all dates'}
                </p>
              </div>
              <button type="button" className="db-btn db-btn-outline db-btn-sm db-no-print" onClick={() => window.print()}>
                Print
              </button>
            </div>

            {type === 'hazard-summary' ? (
              <>
                <div className="db-stats" style={{ marginTop: 18 }}>
                  <Stat value={report.total_occurrences} label="Total occurrences" />
                  <Stat value={report.total_casualties} label="Total casualties" />
                  <Stat value={report.total_displaced} label="Total displaced" />
                </div>

                <div className="db-grid-2">
                  <section>
                    <h3>By hazard type</h3>
                    <BarList rows={report.breakdown_by_type} labelKey="hazard_type__name" />
                  </section>
                  <section>
                    <h3>By severity</h3>
                    <BarList
                      rows={(report.severity_distribution || []).map((r) => ({
                        ...r, display: SEVERITY_LABEL[r.severity_level] || r.severity_level,
                      }))}
                      labelKey="severity_level"
                      colorFor={(r) => SEVERITY_VAR[r.severity_level]}
                    />
                  </section>
                </div>

                <section style={{ marginTop: 20 }}>
                  <h3>Affected barangays</h3>
                  <BarList rows={report.affected_barangays} labelKey="barangay__name" />
                </section>
              </>
            ) : (
              <>
                <div className="db-stats" style={{ marginTop: 18 }}>
                  <Stat value={report.active_hazards} label="Active hazards" />
                  <Stat value={report.resolved_hazards} label="Resolved hazards" />
                  <Stat value={report.archived_hazards} label="Archived hazards" />
                  <Stat value={report.total_hazard_events} label="Total hazard events" />
                  <Stat value={report.total_alerts_issued} label="Alerts issued" />
                </div>

                <section style={{ marginTop: 8 }}>
                  <h3>Alerts by severity</h3>
                  <BarList
                    rows={(report.alerts_by_severity || []).map((r) => ({
                      ...r, display: SEVERITY_LABEL[r.severity] || r.severity,
                    }))}
                    labelKey="severity"
                    colorFor={(r) => SEVERITY_VAR[r.severity]}
                  />
                </section>
              </>
            )}

            <p className="db-note">
              Figures come from archived historical records and published hazard zones. Each
              generation is written to the audit log.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}