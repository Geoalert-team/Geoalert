import React, { useEffect, useRef, useState } from 'react';
import CategoryBars from '../components/Charts/CategoryBars';
import BarangayLikelihood from '../components/Forecast/BarangayLikelihood';
import SeasonalOutlook from '../components/Forecast/SeasonalOutlook';
import ActivityBand from '../components/Analytics/ActivityBand';
import ResponseBand from '../components/Analytics/ResponseBand';
import MonthlyMultiples from '../components/Analytics/MonthlyMultiples';
import BarangayActivity from '../components/Analytics/BarangayActivity';
import ExportMenu from '../components/Analytics/ExportMenu';
import usePrintOpensDetails from '../components/Analytics/usePrintOpensDetails';
import { hazardSeriesColor, severitySeriesColor } from '../components/Charts/chartTheme';
import { SEVERITY_LABEL, inSeverityOrder } from '../utils/severity';
import { reportsApi } from '../api/reportApi';
import { hazardsApi } from '../api/hazardsApi';
import { downloadCsv, csvFilename } from '../utils/csv';
import { analyticsCsv, analyticsCriteria } from '../utils/analyticsCsv';
import './css/Dashboard.css';
import './css/Analytics.css';

const WINDOWS = [3, 6, 12, 24];

const toRows = (rows, key, label = (r) => r[key] || 'Unspecified', color) =>
  (rows || []).map((r) => ({ label: label(r), value: r.count, color: color ? color(r) : undefined }));

/**
 * F7 Analytics: patterns in how hazards have been handled, and what past
 * seasons say is coming. One filter row (period and hazard type) scopes the
 * whole tab; below it, in reading order:
 *
 *   Activity       how much happened, with each count's monthly shape
 *   Response       how fast alerts were read and reports reviewed
 *   Month by month the four measures as small multiples
 *   Outlook        the next three months, from the whole archive
 *   Likelihood     which barangays a month tends to hit
 *   Breakdowns     zones by type and severity, and every barangay's activity
 *
 * The outlook and likelihood used to live on the History page, which is now
 * the record archive. Download, PDF and print are each written to the audit
 * log before they happen.
 */
export default function AnalyticsPanel() {
  const [months, setMonths] = useState(12);
  const [hazardTypeId, setHazardTypeId] = useState('');
  const [includeSamples, setIncludeSamples] = useState(false);
  const [hazardTypes, setHazardTypes] = useState([]);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef(null);
  usePrintOpensDetails(bodyRef);

  useEffect(() => {
    hazardsApi.types()
      .then((types) => setHazardTypes(Array.isArray(types) ? types : (types?.results || [])))
      .catch(() => setHazardTypes([]));
  }, []);

  useEffect(() => {
    let live = true;
    setBusy(true);
    setError('');
    reportsApi.analytics({
      months,
      ...(hazardTypeId ? { hazard_type: hazardTypeId } : {}),
      ...(includeSamples ? { include_samples: 'true' } : {}),
    })
      .then((d) => { if (live) setData(d); })
      .catch((err) => {
        if (!live) return;
        setError(err?.status === 403
          ? 'You do not have permission to view analytics.'
          : 'Analytics could not be loaded right now. Please try again later.');
      })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [months, hazardTypeId, includeSamples]);

  // The outlook and likelihood follow the picker straight away; they need
  // not wait for the analytics figures
  const pickedName = hazardTypes.find((t) => String(t.id) === hazardTypeId)?.name || null;

  async function exportAs(via) {
    try { await reportsApi.printed('analytics', analyticsCriteria(data), via); } catch { /* export anyway */ }
    if (via === 'csv') downloadCsv(csvFilename('analytics'), analyticsCsv(data));
    else window.print();
  }

  const k = data?.kpis;
  const noZones = !k || k.zones_published === 0;

  return (
    <>
      <div className="db-card an-toolbar db-no-print">
        <div className="an-seg" role="group" aria-label="Period">
          {WINDOWS.map((w) => (
            <button
              key={w}
              type="button"
              className={months === w ? 'is-active' : ''}
              aria-pressed={months === w}
              onClick={() => setMonths(w)}
              disabled={busy}
            >
              {w} months
            </button>
          ))}
        </div>
        <label className="db-field an-hazard">
          Hazard
          <select value={hazardTypeId} onChange={(e) => setHazardTypeId(e.target.value)}>
            <option value="">All types</option>
            {hazardTypes.map((t) => <option key={t.id} value={String(t.id)}>{t.name}</option>)}
          </select>
        </label>
        <div className="an-toolbar-end">
          <label className="db-report-check an-secondary">
            <input type="checkbox" checked={includeSamples} onChange={(e) => setIncludeSamples(e.target.checked)} />
            Include sample data
          </label>
          <ExportMenu onExport={exportAs} disabled={!data || busy} />
        </div>
      </div>

      {error && <div className="db-card"><p className="db-error" role="alert">{error}</p></div>}
      {!data && !error && <div className="db-card"><p className="db-empty">Loading analytics…</p></div>}

      <div ref={bodyRef} className="an-body">
      {data && (
        <div className={`an-figures ${busy ? 'is-busy' : ''}`}>
          <p className="an-period">
            Last {data.months} months, from {new Date(data.since).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
            {data.hazard_type && <> · {data.hazard_type.name}</>}
            {' · '}Generated by {data.generated_by}, {new Date(data.generated_at).toLocaleString()}.
          </p>
          {data.includes_samples && (
            <p className="an-notice" role="status">
              <strong>Includes sample data.</strong> These figures count seeded test rows, so they are not an official record.
            </p>
          )}

          <ActivityBand kpis={k} monthly={data.monthly} />
          <ResponseBand kpis={k} />
          <MonthlyMultiples monthly={data.monthly} />
        </div>
      )}

      {/* Drawn from the whole archive through their own endpoints: they load
          alongside the figures and fail on their own, never waiting on them */}
      <div className="db-card">
        <SeasonalOutlook hazardTypeId={hazardTypeId} hazardName={pickedName} includeSamples={includeSamples} />
      </div>

      <div className="db-card">
        <h2>Likelihood by barangay</h2>
        <p className="db-card-sub">
          Which barangays a month has tended to hit, from the same month in past years
        </p>
        <BarangayLikelihood hazard={pickedName || ''} excludeSamples={!includeSamples} />
      </div>

      {data && (
        <div className={`an-figures ${busy ? 'is-busy' : ''}`}>
          <div className={`an-grid ${data.hazard_type ? 'is-single' : ''}`}>
            {!data.hazard_type && (
              <div className="db-card">
                <h2>Zones by hazard type</h2>
                <CategoryBars
                  rows={noZones ? [] : toRows(data.zones_by_type, 'hazard_type__name', undefined, (r) => hazardSeriesColor(r.hazard_type__name))}
                  valueHead="Zones"
                  empty="No zones in this period."
                  thin
                />
              </div>
            )}
            <div className="db-card">
              <h2>Zones by severity</h2>
              <CategoryBars
                rows={noZones ? [] : toRows(
                  inSeverityOrder(data.zones_by_severity), 'severity',
                  (r) => SEVERITY_LABEL[r.severity] || r.severity, (r) => severitySeriesColor(r.severity),
                )}
                valueHead="Zones"
                empty="No zones in this period."
                thin
              />
            </div>
          </div>

          <div className="db-card">
            <h2>Barangay activity</h2>
            <p className="db-card-sub">Zones published and incident reports per barangay in this period.</p>
            <BarangayActivity rows={data.barangays} />
          </div>
        </div>
      )}
      </div>
    </>
  );
}
