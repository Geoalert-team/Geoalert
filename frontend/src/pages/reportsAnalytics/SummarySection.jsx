import React from 'react';
import { reportsApi } from '../../api/reportApi';
import CategoryBars from '../../components/Charts/CategoryBars';
import { hazardSeriesColor, severitySeriesColor } from '../../components/Charts/chartTheme';
import { SEVERITY_LABEL } from '../../utils/severity';
import SectionFrame from './SectionFrame';
import useSection from './useSection';
import { IMPACT, figure, formatShare, impactOf, num, recordedText, summaryCsv, withShares } from './reportFormat';

/**
 * Summary (the Hazard Summary report): what GeoAlert holds, then the
 * archive's events and their impact for the applied filters, the breakdowns
 * a situation report carries, and how complete the records are. Impact
 * figures say how many of the records carry them: a sum over the records
 * that have a figure is not a total for the period.
 */
export default function SummarySection({ params, active }) {
  const state = useSection(reportsApi.summary, params, active);
  const s = state.data;
  return (
    <SectionFrame report="hazard-summary" title="Hazard Summary" file="hazard-summary" answer={s} state={state}
      csv={summaryCsv}>
      {s && <SummaryBody s={s} />}
    </SectionFrame>
  );
}

function SummaryBody({ s }) {
  const h = s.holdings;
  return (
    <>
      <section className="ra-block" aria-labelledby="ra-holdings-h">
        <h3 id="ra-holdings-h">What GeoAlert holds</h3>
        <p className="ra-block-sub">Everything on file, whatever the filters.</p>
        <div className="ra-two">
          <Table head={['Archive', 'Records', 'From', 'To']}
            rows={h.archive.map((a) => [a.hazard, num(a.records), a.first, a.last])} numeric={[1]} />
          <Table head={['GeoAlert’s own records', 'Count', 'Since']} numeric={[1]} rows={[
            ['Hazard zones', num(h.zones.count), h.zones.first || '—'],
            ['Alerts', num(h.alerts.count), h.alerts.first || '—'],
            ['Alert notices', num(h.notices.count), ''],
            ['Incident reports', num(h.incident_reports.count), h.incident_reports.first || '—'],
            ['Barangays · puroks', `${num(h.barangays)} · ${num(h.puroks)}`, ''],
          ]} />
        </div>
      </section>

      <section className="ra-block" aria-labelledby="ra-impact-h">
        <h3 id="ra-impact-h">Events and impact</h3>
        {!s.events ? (
          <p className="db-empty ra-empty">No hazard records for these filters.</p>
        ) : (
          <dl className="ra-doc-figures">
            <div><dt>Events</dt><dd>{num(s.events)}</dd></div>
            {IMPACT.map((i) => {
              const m = impactOf(s, i.key);
              return (
                <div key={i.key} className={m.value === null ? 'is-missing' : ''}>
                  <dt>{i.label}</dt>
                  <dd>{m.value === null ? 'Not recorded' : figure(i, m.value)}</dd>
                  <dd className="ra-kpi-note">{recordedText(m)}</dd>
                </div>
              );
            })}
            <div className="is-missing"><dt>Displaced</dt><dd>Not recorded</dd>
              <dd className="ra-kpi-note">the archive has no displacement figures</dd></div>
          </dl>
        )}
      </section>

      {s.events > 0 && (
        <>
          <section className="ra-block" aria-labelledby="ra-by-hazard-h">
            <h3 id="ra-by-hazard-h">By hazard type</h3>
            <div className="ra-two">
              <div>
                <h4>Events by hazard type</h4>
                <CategoryBars rows={s.by_hazard.map((r) => ({ label: r.hazard, value: r.events, color: hazardSeriesColor(r.hazard) }))}
                  thin empty="No events." />
              </div>
              <div>
                <h4>Events by severity</h4>
                <CategoryBars rows={s.severity.map((r) => ({ label: SEVERITY_LABEL[r.severity], value: r.count,
                  color: severitySeriesColor(r.severity) }))} thin empty="No events." />
              </div>
            </div>
            <ImpactTable first="Hazard type" rows={s.by_hazard.map((r) => ({ ...r, label: r.hazard }))} />
          </section>

          <section className="ra-block" aria-labelledby="ra-by-brgy-h">
            <h3 id="ra-by-brgy-h">By barangay</h3>
            <p className="ra-block-sub">The barangay each record is filed under; records with none are listed last.</p>
            <ImpactTable first="Barangay" share={s.events} rows={s.by_barangay.map((r) => ({ ...r, label: r.name }))} />
            {s.by_purok.length > 0 && (
              <>
                <h4>By purok</h4>
                <Table head={['Purok', 'Events']} numeric={[1]} rows={s.by_purok.map((p) => [p.name, num(p.events)])} />
              </>
            )}
          </section>

          {(s.fire || s.flood_landslide) && (
            <section className="ra-block" aria-labelledby="ra-details-h">
              <h3 id="ra-details-h">Details by hazard</h3>
              <div className="ra-two">
                {s.fire && <Counted title="Fires by property category" rows={s.fire.property_category} />}
                {s.fire && <Counted title="Fires by alarm level" rows={s.fire.alarm_level} />}
                {s.flood_landslide && <Counted title="Floods and landslides by sub-category" rows={s.flood_landslide.subcategory} />}
                {s.flood_landslide && <Counted title="Floods and landslides by cause" rows={s.flood_landslide.cause} />}
              </div>
            </section>
          )}

          <section className="ra-block" aria-labelledby="ra-complete-h">
            <h3 id="ra-complete-h">How complete the records are</h3>
            <p className="ra-block-sub">The share of the selected records that carry each detail. Figures above count only these.</p>
            <ul className="ra-complete">
              {s.completeness.map((c) => {
                const share = c.of ? c.count / c.of : 0;
                return (
                  <li key={c.key}>
                    <span>{c.label}</span>
                    <span className="ra-bar" aria-hidden="true"><span style={{ width: `${Math.round(share * 100)}%` }} /></span>
                    <span className="ra-num">{num(c.count)} of {num(c.of)} ({formatShare(c.of ? share : null)})</span>
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      )}

      <footer className="ra-doc-foot">
        Fires come from the BFP fire log; floods and landslides from the DRRMO events record. Each generation and
        export of this report is written to the audit log.
      </footer>
    </>
  );
}

function Table({ head, rows, numeric = [] }) {
  return (
    <div className="ra-table-scroll">
      <table className="db-table">
        <thead><tr>{head.map((h, i) => <th key={h} className={numeric.includes(i) ? 'ra-num' : ''}>{h}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r[0]}>{r.map((v, i) => <td key={i} className={numeric.includes(i) ? 'ra-num' : ''}>{v}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ImpactTable({ first, rows, share }) {
  return (
    <div className="ra-table-scroll">
      <table className="db-table">
        <thead>
          <tr>
            <th>{first}</th><th className="ra-num">Events</th>
            {share !== undefined && <th className="ra-num">Share</th>}
            {IMPACT.map((i) => <th key={i.key} className="ra-num">{i.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td><td className="ra-num">{num(r.events)}</td>
              {share !== undefined && <td className="ra-num">{formatShare(share ? r.events / share : null)}</td>}
              {IMPACT.map((i) => <td key={i.key} className="ra-num">{figure(i, r[i.key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Counted({ title, rows }) {
  return (
    <div>
      <h4>{title}</h4>
      {rows.length ? (
        <Table head={['', 'Records', 'Share']} numeric={[1, 2]}
          rows={withShares(rows, (r) => r.label).map((r) => [r.label, num(r.count), formatShare(r.share)])} />
      ) : <p className="db-empty">Not recorded.</p>}
    </div>
  );
}
