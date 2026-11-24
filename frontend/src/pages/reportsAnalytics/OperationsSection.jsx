import React from 'react';
import { reportsApi } from '../../api/reportApi';
import BarangayActivity from '../../components/Analytics/BarangayActivity';
import ResponseBand from '../../components/Analytics/ResponseBand';
import StatTile from '../../components/Analytics/StatTile';
import CategoryBars from '../../components/Charts/CategoryBars';
import { hazardSeriesColor, severitySeriesColor } from '../../components/Charts/chartTheme';
import { SEVERITY_LABEL, inSeverityOrder } from '../../utils/severity';
import SectionFrame from './SectionFrame';
import useSection from './useSection';
import { num, operationsCsv } from './reportFormat';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December'];

/** 2026-11-09 -> 9 November 2026, as a calendar day (no time zone shift) */
export function dayWords(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/**
 * Operations (the Response Status report): what the office did in GeoAlert
 * in the period: zones, alerts and how fast barangays opened them, incident
 * reports and how fast they were reviewed. GeoAlert's own records, so it
 * starts when the system went live.
 */
export default function OperationsSection({ params, active }) {
  const state = useSection(reportsApi.analytics, params, active);
  const a = state.data;
  return (
    <SectionFrame report="response-status" title="Response Status" file="response-status" answer={a} state={state}
      csv={operationsCsv}>
      {a && <OperationsBody a={a} />}
    </SectionFrame>
  );
}

function OperationsBody({ a }) {
  const k = a.kpis;
  const z = a.zones_by_status || {};
  const quiet = !k.zones_published && !k.zones_retracted && !k.alerts_issued && !k.incidents_submitted;
  const zonesByType = (a.zones_by_type || []).map((r) => ({
    label: r.hazard_type__name || 'Unspecified', value: r.count, color: hazardSeriesColor(r.hazard_type__name),
  }));
  const zonesBySeverity = k.zones_published
    ? inSeverityOrder(a.zones_by_severity || []).map((r) => ({
      label: SEVERITY_LABEL[r.severity] || r.severity, value: r.count, color: severitySeriesColor(r.severity),
    }))
    : [];
  return (
    <>
      {a.first_record && (
        <p className="ra-thin">
          GeoAlert&apos;s own records begin on {dayWords(a.first_record)}, so periods before then have none.
        </p>
      )}
      {quiet && <p className="db-empty ra-empty">No zones, alerts or incident reports in GeoAlert for these filters.</p>}

      <section className="ra-block" aria-labelledby="ra-zones-h">
        <h3 id="ra-zones-h">Hazard zones</h3>
        <div className="ra-tiles">
          <StatTile value={num(k.zones_published)} label="Published" hint={`${num(z.Retracted)} withdrawn as errors`} />
          <StatTile value={num(z.Active)} label="Still active" hint={`${num(k.active_zones_now)} active now, any period`} />
          <StatTile value={num(z.Resolved)} label="Resolved" />
          <StatTile value={num(z.Archived)} label="Archived" />
        </div>
        <div className="ra-two">
          {!a.hazard_type && (
            <div><h4>Zones by hazard type</h4>
              <CategoryBars rows={zonesByType} valueHead="Zones" empty="No zones in this period." thin /></div>
          )}
          <div><h4>Zones by severity</h4>
            <CategoryBars rows={zonesBySeverity} valueHead="Zones" empty="No zones in this period." thin /></div>
        </div>
      </section>

      <section className="ra-block" aria-labelledby="ra-alerts-h">
        <h3 id="ra-alerts-h">Alerts and incident reports</h3>
        <div className="ra-tiles">
          <StatTile value={num(k.alerts_issued)} label="Alerts issued" hint={`${num(k.extreme_alerts)} Extreme`} />
          <StatTile value={num(k.notices_sent)} label="Alert notices sent" hint={`${num(k.notices_read)} opened`} />
          <StatTile value={num(k.incidents_submitted)} label="Incident reports"
            hint={k.incidents_pending ? `${num(k.incidents_pending)} pending` : 'none pending'} />
          <StatTile value={num((k.incidents_validated || 0) + (k.incidents_rejected || 0))} label="Reports decided"
            hint={`${num(k.incidents_validated)} validated, ${num(k.incidents_rejected)} rejected`} />
        </div>
        <ResponseBand kpis={k} heading="Speed of response" as="h4" />
      </section>

      <section className="ra-block" aria-labelledby="ra-activity-h">
        <h3 id="ra-activity-h">Barangay activity</h3>
        <p className="ra-block-sub">Zones published and incident reports per barangay in the period.</p>
        <BarangayActivity rows={a.barangays} />
      </section>

      <footer className="ra-doc-foot">
        Counted from the hazard zones, alerts, alert notices and incident reports in GeoAlert. Each generation and
        export of this report is written to the audit log.
      </footer>
    </>
  );
}
