import React, { useEffect, useRef, useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { reportsApi } from '../api/reportApi';
import { barangaysApi } from '../api/barangaysApi';
import { hazardsApi } from '../api/hazardsApi';
import CategoryBars from '../components/Charts/CategoryBars';
import { hazardSeriesColor, severitySeriesColor } from '../components/Charts/chartTheme';
import { Icon } from './Dashboard/admin/adminShared';
import './css/Dashboard.css';

const TYPES = [
  {
    key: 'hazard-summary',
    label: 'Hazard Summary',
    blurb: 'Total occurrences, breakdown by hazard type, severity distribution and affected barangays.',
    usesHazardType: true,
    icon: 'alert',
  },
  {
    key: 'response-status',
    label: 'Response Status',
    blurb: 'Active, resolved and archived hazards, with alerts issued and their severities.',
    usesHazardType: false,
    icon: 'clock',
  },
];

const SEVERITY_LABEL = { Red: 'Extreme', Orange: 'Moderate', Green: 'Low' };

// Anything slower than this and we tell the user rather than leaving them
// watching a spinner, as the spec asks.
const SLOW_MS = 8000;

// The report endpoints key their rows by whatever the GROUP BY produced;
// the charts want a plain { label, value, color }.
function toRows(rows = [], labelKey, colorFor) {
  return (rows || []).map((r) => ({
    label: r.display || r[labelKey] || 'Unspecified',
    value: r.count,
    color: colorFor ? colorFor(r) : undefined,
  }));
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
  // Seeded events are left out by default. A report gets printed and handed
  // over as an official figure, and Faker incidents are not one.
  const [includeSamples, setIncludeSamples] = useState(false);

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
    setIncludeSamples(false);
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
    if (includeSamples) params.include_samples = 'true';

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

  const filtersOn = dateFrom || dateTo || barangay || hazardType || includeSamples;

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
                <span className="db-report-type-icon"><Icon name={t.icon} size={20} /></span>
                <span>
                  <strong>{t.label}</strong>
                  <small>{t.blurb}</small>
                </span>
                <span className="db-report-type-check"><Icon name="check" size={14} strokeWidth={3} /></span>
              </button>
            ))}
          </div>

          <form onSubmit={generate}>
            <h3 className="db-report-label">Filters</h3>
            <div className="db-report-filters">
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

            <div className="db-report-actions">
              <label className="db-report-check">
                <input type="checkbox" checked={includeSamples} onChange={(e) => setIncludeSamples(e.target.checked)} />
                Include sample data
              </label>
              <div className="db-btn-row">
                {filtersOn && (
                  <button type="button" className="db-btn db-btn-outline" onClick={clearFilters} disabled={busy}>
                    Clear filters
                  </button>
                )}
                <button
                  className="db-btn db-btn-primary"
                  disabled={busy || (dateFrom && dateTo && dateFrom > dateTo)}
                >
                  {busy ? 'Generating…' : 'Generate report'}
                </button>
              </div>
            </div>
          </form>

          {slow && (
            <p className="db-callout" style={{ marginTop: 14 }}>
              Report generation is taking longer than expected. Please wait or simplify the criteria.
            </p>
          )}
        </div>

        {/* ---------- Results ---------- */}
        {!report && !error && !notEnough && (
          <div className="db-card db-report-placeholder db-no-print">
            <span className="db-report-type-icon"><Icon name={current.icon} size={22} /></span>
            <strong>{busy ? 'Generating your report…' : 'No report yet'}</strong>
            <p>{busy ? 'This usually takes a few seconds.' : `Set your filters and press Generate report to see the ${current.label}.`}</p>
          </div>
        )}

        {error &&<div className="db-card"><p className="db-error" role="alert">{error}</p></div>}

        {notEnough && (
          <div className="db-card">
            <p className="db-empty">{notEnough}</p>
            {!includeSamples && (
              <p className="db-note">
                Sample data is excluded from reports. If the archive is mostly
                seeded test events, tick <strong>Include sample data</strong> to
                see them — the report will be labelled as not official.
              </p>
            )}
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

            {report.includes_samples && (
              <p className="db-error" role="status" style={{ marginTop: 14 }}>
                <strong>This report includes sample data.</strong> Figures below count
                events generated for testing alongside real ones, so it is not
                suitable as an official record.
              </p>
            )}

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
                    <CategoryBars
                      rows={toRows(
                        report.breakdown_by_type, 'hazard_type__name',
                        (r) => hazardSeriesColor(r.hazard_type__name),
                      )}
                      empty="Nothing to show."
                    />
                  </section>
                  <section>
                    <h3>By severity</h3>
                    <CategoryBars
                      rows={toRows(
                        (report.severity_distribution || []).map((r) => ({
                          ...r, display: SEVERITY_LABEL[r.severity_level] || r.severity_level,
                        })),
                        'severity_level',
                        (r) => severitySeriesColor(r.severity_level),
                      )}
                      empty="Nothing to show."
                    />
                  </section>
                </div>

                <section style={{ marginTop: 20 }}>
                  <h3>Affected barangays</h3>
                  <CategoryBars
                    rows={toRows(report.affected_barangays, 'barangay__name')}
                    empty="Nothing to show."
                  />
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

                {report.retracted_hazards > 0 && (
                  <p className="db-note">
                    <strong>
                      {report.retracted_hazards} zone{report.retracted_hazards === 1 ? '' : 's'} withdrawn
                      as published in error.
                    </strong>{' '}
                    Withdrawn zones are not counted in total hazard events — they
                    never happened — but the alerts they issued are still counted
                    above, because those alerts did go out to recipients.
                  </p>
                )}

                <section style={{ marginTop: 8 }}>
                  <h3>Alerts by severity</h3>
                  <CategoryBars
                    rows={toRows(
                      (report.alerts_by_severity || []).map((r) => ({
                        ...r, display: SEVERITY_LABEL[r.severity] || r.severity,
                      })),
                      'severity',
                      (r) => severitySeriesColor(r.severity),
                    )}
                    valueHead="Alerts"
                    empty="Nothing to show."
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