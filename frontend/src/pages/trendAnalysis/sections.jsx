import React, { useState } from 'react';
import StackedBars from '../../components/Charts/StackedBars';
import { hazardSeriesColor } from '../../components/Charts/chartTheme';
import { stackedData } from '../../components/Charts/stackedData';
import { num } from '../reportsAnalytics/reportFormat';
import PlacesMap from './PlacesMap';
import { hazardsIn } from './trendShapes';
import {
  MON, STATUS, changeLine, howOften, lastYear, mostCommon, peakLines, plainSentence, stoodOut,
} from './trendWords';

const SHORT_LIST = 10;

/** A titled band of the page that loads and fails on its own. */
export function Band({ id, title, sub, state, invalid, children }) {
  return (
    <section className="ra-band" id={id} aria-labelledby={`${id}-h`} aria-busy={state?.status === 'loading' || undefined}>
      <div className="ra-band-head">
        <div>
          <h2 id={`${id}-h`}>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
      </div>
      {invalid && <p className="ra-state">Fix the dates above to see this section.</p>}
      {!invalid && state?.status === 'loading' && !state.data && <p className="ra-state" role="status">Loading…</p>}
      {!invalid && state?.status === 'error' && <p className="db-error" role="alert">{state.error}</p>}
      {!invalid && state?.data && <div className={state.status === 'loading' ? 'ra-refreshing' : ''}>{children}</div>}
    </section>
  );
}

/* ---------- At a glance ---------- */

export function AtAGlance({ data }) {
  if (!data.hazards.length) return <p className="db-empty ra-empty">No hazard records for these filters.</p>;
  return (
    <>
      <div className="ta-hazards">
        {data.hazards.map((h) => {
          const last = lastYear(h);
          const change = changeLine(h.change);
          const top = Math.max(1, ...h.years.map((y) => y.count));
          return (
            <article key={h.hazard} className="ta-hazard">
              <header>
                <h3>{h.hazard}</h3>
                <span className={`ta-verdict is-${h.verdict}`}>{STATUS[h.verdict]}</span>
              </header>
              {last && <p className="ta-big">{num(last.count)} events in {last.year}</p>}
              {change && last && <p className="ta-change">{change}</p>}
              {h.so_far && <p className="ta-change">{h.so_far.year} so far: {num(h.so_far.count)}</p>}
              <p>{plainSentence(h)}</p>
              {h.years.length > 0 && (
                <ol className="ta-years" aria-label={`${h.hazard} events in each full year`}>
                  {h.years.map((y) => (
                    <li key={y.year}>
                      <span className="ta-year-bar" style={{ height: `${Math.max(4, (y.count / top) * 56)}px`,
                        background: hazardSeriesColor(h.hazard) }} />
                      <b>{num(y.count)}</b>
                      <small>{y.year}</small>
                    </li>
                  ))}
                </ol>
              )}
            </article>
          );
        })}
      </div>

      <h3 className="ta-sub">Months that stood out</h3>
      {data.unusual_months.length ? (
        <ul className="ta-stood-out">
          {data.unusual_months.map((m) => <li key={`${m.hazard}-${m.year}-${m.month}`}>{stoodOut(m)}</li>)}
        </ul>
      ) : (
        <p className="db-empty">No month stood out from the same month in other years.</p>
      )}

      <details className="ta-method">
        <summary>How we worked this out</summary>
        <p>
          We count events in each full calendar year. A hazard is called &ldquo;Going up&rdquo; or &ldquo;Going
          down&rdquo; only when the Mann–Kendall test finds a steady change at the 5% level over at least five full
          years with no empty year (its size is Sen&apos;s slope); with fewer years we show the counts only. Years
          after a hazard&apos;s last record, and empty years, may be missing data. A month &ldquo;stood out&rdquo; when
          it had at least three events and more than the same month&apos;s average in at least three other years by
          two standard deviations.
        </p>
      </details>
    </>
  );
}

/* ---------- Year by year ---------- */

export function YearByYear({ data, step, onStep }) {
  const hazards = hazardsIn(data);
  const rows = data.series.map((s) => ({ ...s, label: s.partial ? `${s.label} (part)` : s.label }));
  const series = stackedData(rows, hazards, hazardSeriesColor);
  return (
    <article className="ra-chart">
      <div className="ra-chart-head">
        <p>How many events happened in each {step === 'year' ? 'year' : 'month'}, by type of hazard.</p>
        <div className="ra-seg" role="group" aria-label="Show by">
          {[['year', 'By year'], ['month', 'By month']].map(([key, label]) => (
            <button key={key} type="button" aria-pressed={step === key} className={step === key ? 'is-active' : ''}
              onClick={() => onStep(key)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <StackedBars labels={series.labels} datasets={series.datasets} maxTicks={14}
        empty="No hazard records for these filters." />
      {data.series.some((s) => s.partial) && (
        <p className="ra-chart-note">A bar marked (part) covers only part of that {step}.</p>
      )}
    </article>
  );
}

/* ---------- Busiest months ---------- */

export function BusiestMonths({ data }) {
  const averages = data.month_average || [];
  const byMonth = MON.map((label, i) => ({
    label, counts: Object.fromEntries(averages.map((a) => [a.hazard, a.months[i] || 0])),
  }));
  const months = stackedData(byMonth, averages.map((a) => a.hazard), hazardSeriesColor);
  const peaks = peakLines(averages);
  if (!averages.length) return <p className="db-empty ra-empty">No hazard records for these filters.</p>;
  return (
    <>
      {peaks.length > 0 && <ul className="ta-peaks">{peaks.map((p) => <li key={p}>{p}</li>)}</ul>}
      <article className="ra-chart">
        <StackedBars labels={months.labels} datasets={months.datasets} height={260} valueHead="Events a year"
          empty="No hazard records for these filters." />
      </article>
      <p className="ra-coverage">
        Averages count only the years each month is on record, so a hazard with a longer record does not look bigger.
        We cannot compare this with rain: GeoAlert has no rainfall records.
      </p>
    </>
  );
}

/* ---------- Where it happens ---------- */

export function WhereItHappens({ places, trends, features }) {
  const [all, setAll] = useState(false);
  const fullYears = places.years.filter((y) => y.complete).length;
  const mix = new Map((trends?.barangays || []).map((b) => [b.id, b.counts]));
  const withEvents = places.barangays.filter((b) => b.total > 0);
  const shown = all ? places.barangays : withEvents.slice(0, SHORT_LIST);
  return (
    <>
      <div className="ta-places">
        <PlacesMap rows={places.barangays} features={features} selected={places.selected} />
        <div>
          {withEvents.length ? (
            <div className="ra-table-scroll">
              <table className="db-table">
                <thead>
                  <tr><th>Barangay</th><th className="ra-num">Events</th><th>Most common</th><th>How often</th></tr>
                </thead>
                <tbody>
                  {shown.map((b) => (
                    <tr key={b.id} className={places.selected === b.id ? 'is-picked' : ''}>
                      <td>{b.name}</td>
                      <td className="ra-num">{num(b.total)}</td>
                      <td>{b.total ? mostCommon(mix.get(b.id)) : '—'}</td>
                      <td>{howOften(b, fullYears)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="db-empty">No barangay had events in this range.</p>}
          {places.barangays.length > SHORT_LIST && (
            <button type="button" className="db-btn db-btn-outline db-btn-sm ta-more" onClick={() => setAll((v) => !v)}>
              {all ? 'Show the busiest only' : `Show all ${places.barangays.length} barangays`}
            </button>
          )}
        </div>
      </div>
      <p className="ra-coverage">
        Darker on the map means more events for the barangay&apos;s size. &ldquo;How often&rdquo; counts the full
        years with at least one event.
        {places.unspecified.total > 0 && ` ${num(places.unspecified.total)} records have no barangay and are not on the map.`}
      </p>
    </>
  );
}
