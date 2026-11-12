import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { historyApi } from '../../api/historyApi';
import ForecastPeriodPicker from './ForecastPeriodPicker';
import {
  FORECAST_DISCLAIMER, IN_TRAINING_NOTE, MODEL_LABELS, RAIN_ATTRIBUTION, SEVERITY_WORD, chanceText, combinedText,
  combinedUnavailable, defaultPeriod, levelLabel, likelihoodInfo, periodLabel, periodMonth, periodParams, periodPastHeader,
  periodYearsText, rangeText, smallChanceText, unavailableNote, withMonth,
} from './forecastLevels';
import './forecast.css';

const RAIN_HAZARDS = ['Flood', 'Landslide'];

// The attribution line, with its two links
function RainAttribution() {
  let rest = RAIN_ATTRIBUTION.text;
  const parts = [];
  RAIN_ATTRIBUTION.links.forEach((l) => {
    const [before, after] = rest.split(l.label);
    parts.push(
      <React.Fragment key={`t-${l.label}`}>{before}</React.Fragment>,
      <a key={l.label} href={l.href} target="_blank" rel="noopener noreferrer">{l.label}</a>,
    );
    rest = after;
  });
  parts.push(<React.Fragment key="t-end">{rest}</React.Fragment>);
  return <p className="fc-note fc-attribution">{parts}</p>;
}

/**
 * Which barangays a month, a month in a given year, or the week around a
 * date is likely to hit, and with what. Pick the period; pick a barangay
 * row to see its whole year. A period that has started also shows what
 * actually happened in it.
 *
 * Fire comes from a model trained on past fires (backend
 * apps/history/model_forecast.py); flood and landslide from models of rain and
 * terrain (apps/history/hazard_forecast.py). With no hazard picked, the table is
 * the chance of any of them (the response's `combined`). Not a weather forecast.
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

  const isAll = hazard === '';
  const results = data?.results || [];
  // All hazards: one row per barangay from `combined`; one hazard: its own rows
  const rows = isAll ? (data?.combined || []) : results;
  const shown = compact ? rows.slice(0, limit) : rows;
  // What actually happened, once a period with a year has started
  const outcome = data?.outcome;
  const modelled = data?.model_hazards || [];
  const showChance = !compact && !isAll && rows.some((r) => r.method === 'model' || r.method === 'unavailable');
  const inTraining = !isAll && shown.some((r) => r.in_training);
  const showsRain = isAll
    ? shown.some((r) => (r.hazards || []).some((h) => RAIN_HAZARDS.includes(h.hazard_type)))
    : shown.some((r) => r.method === 'model' && RAIN_HAZARDS.includes(r.hazard_type));
  const rainRow = results.find((r) => r.method === 'model' && RAIN_HAZARDS.includes(r.hazard_type) && r.model);
  const rainModel = rainRow ? (MODEL_LABELS[rainRow.model] || rainRow.model) : null;
  // What happened per barangay, from the per-hazard rows, for the combined table
  const happened = (id) => results.filter((r) => r.barangay_id === id).reduce((n, r) => n + (r.actual || 0), 0);
  const eventsText = (n) => (n ? `${n} event${n === 1 ? '' : 's'}` : 'None');
  // A shown hazard the models could not give is named under the All hazards table, never dropped silently
  const allNote = isAll && data ? unavailableNote(data, data.hazards_included || []) : '';
  const unavailable = data?.unavailable_hazards || [];
  // The chart comes from the models only; without them it has no bars, never counted ones
  const barNote = data?.profile_method === 'model'
    ? `Bar height is ${barangay ? 'the model\'s' : 'the average barangay\'s'} chance of at least one event in that month.`
    : 'The model gives no chart for this period.';

  return (
    <div className="fc">
      <div className="fc-controls">
        <ForecastPeriodPicker value={period} onChange={setPeriod} />
      </div>

      {error && <p className="db-error" role="alert">{error}</p>}

      {/* What happened in a period that has started; the figures themselves come from the models */}
      {data?.year != null && outcome && (
        <p className="fc-note">
          {period.mode === 'date' ? `The week of ${periodLabel(period)}` : periodLabel(period)}
          {outcome.complete
            ? ` is over: ${outcome.events} event${outcome.events === 1 ? '' : 's'} happened.`
            : ` has started: ${outcome.events} event${outcome.events === 1 ? '' : 's'} so far.`}
        </p>
      )}

      {data && !rows.length && (
        <p className="db-empty">
          {isAll
            ? 'No barangay has a forecast for this period.'
            : `No ${hazard.toLowerCase()} forecast is available for this period.`}
        </p>
      )}

      {inTraining && <p className="fc-note">{IN_TRAINING_NOTE}</p>}

      {shown.length > 0 && (
        // On a narrow phone the table scrolls inside the card, never the page
        <div className="fc-table-wrap">
        <table className="fc-table">
          <thead>
            {isAll ? (
              <tr>
                <th scope="col">Barangay</th>
                <th scope="col">All hazards</th>
                <th scope="col">Chance</th>
                <th scope="col">Biggest share</th>
                <th scope="col">Each hazard</th>
                {outcome && <th scope="col">{outcome.complete ? 'What happened' : 'So far'}</th>}
              </tr>
            ) : (
              <tr>
                <th scope="col">Barangay</th>
                <th scope="col">Hazard</th>
                <th scope="col">Likelihood</th>
                <th scope="col">{periodPastHeader(period)}</th>
                {showChance && <th scope="col">Chance</th>}
                {outcome && <th scope="col">{outcome.complete ? 'What happened' : 'So far'}</th>}
                {!compact && <th scope="col">Usual severity</th>}
              </tr>
            )}
          </thead>
          <tbody>
            {shown.map((r) => {
              const info = likelihoodInfo(r.method === 'unavailable' ? 'None' : r.level);
              const picked = barangay && barangay.id === r.barangay_id;
              const nameCell = (
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
              );
              // No All hazards chance because a hazard the response calls unavailable is missing: not
              // "None on record". A hazard missing with nothing on record stays "None on record".
              const allUnavailable = isAll && combinedUnavailable(r, unavailable);
              const badge = (
                <span className="fc-badge" style={{ background: info.tint, color: info.text }}>
                  <span className="fc-dot" style={{ background: info.color }} />
                  {allUnavailable ? 'Unavailable right now' : levelLabel(r)}
                </span>
              );
              if (isAll) {
                return (
                  <tr key={r.barangay_id} className={picked ? 'is-picked' : undefined}>
                    {nameCell}
                    <td>{badge}</td>
                    <td>{r.probability == null ? '-' : smallChanceText(r.probability)}</td>
                    <td>{r.top_hazard || '-'}</td>
                    <td>{combinedText(r, unavailable) || '-'}</td>
                    {outcome && <td>{eventsText(happened(r.barangay_id))}</td>}
                  </tr>
                );
              }
              return (
                <tr
                  key={`${r.barangay_id}-${r.hazard_type}`}
                  className={picked ? 'is-picked' : undefined}
                >
                  {nameCell}
                  <td>{r.hazard_type}</td>
                  <td>{badge}</td>
                  <td>{periodYearsText(r, period)}</td>
                  {showChance && (
                    <td>
                      {r.method === 'unavailable' ? (
                        <div className="fc-sub">{r.reason || 'Unavailable right now'}</div>
                      ) : (
                        <>
                          {(r.method === 'model' && r.hazard_type !== 'Fire' ? smallChanceText(r.probability) : chanceText(r)) || '-'}
                          {r.method === 'model' && r.range && <div className="fc-sub">{rangeText(r)}</div>}
                          {r.recorded_rain_probability != null && (
                            <div className="fc-sub">With rain so far: {smallChanceText(r.recorded_rain_probability)}</div>
                          )}
                        </>
                      )}
                    </td>
                  )}
                  {outcome && <td>{eventsText(r.actual)}</td>}
                  {!compact && <td>{SEVERITY_WORD[r.typical_severity] || '-'}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}

      {allNote && <p className="fc-note">{allNote}</p>}

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
                  title={m.probability == null
                    ? `${m.month_name}: no figure`
                    : `${m.month_name}: ${info.label} (${smallChanceText(m.probability)})`}
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
          <p className="fc-sub">{barNote}</p>
        </div>
      )}

      <p className="fc-note">{FORECAST_DISCLAIMER}</p>
      {showsRain && <RainAttribution />}
      {data?.basis?.sample_records > 0 && (
        <p className="fc-note">
          {data.basis.sample_records} of the {data.basis.records} records behind this are sample data
          made for testing.
        </p>
      )}

      {!compact && (
        <details className="db-method">
          <summary>How this is calculated</summary>
          {modelled.includes('Fire') && (
            <p>
              The likelihood for Fire comes from a trained model, a Poisson
              regression. From every real record it learns how many events to expect in each barangay
              in each month, using the barangay, the month, its land area and how many puroks it has
              for that area. That gives the chance of at least one event in the month. For an exact
              date the chance shown is for that week. With a year picked, it is trained only on what
              came before that period. When fewer than 100 fires came before it, the model trained on
              every record is used, and the table says it learned from that period.
            </p>
          )}
          {(rainModel || modelled.some((h) => RAIN_HAZARDS.includes(h))) && (
            <p>
              Flood and landslide come from rain and terrain.
              {rainModel ? ` A ${rainModel} model` : ' A trained model'} learns, from past
              years of daily rain over the city and each barangay&rsquo;s terrain (height above water, slope, nearness
              to streams, roads and the coast), how likely a report is on a day with that much rain.
              For a coming period it replays every past year&rsquo;s rain over the same dates, so each
              chance comes with the range it took across those years. Where this period&rsquo;s rain
              so far is known, it is shown as &ldquo;With rain so far&rdquo;. A hazard whose model
              cannot run is shown as unavailable, never guessed.
            </p>
          )}
          <p>
            All hazards is the chance that at least one of the hazards shown is reported in the
            period. Flood and landslide are combined within each past year&rsquo;s rain, and fire is
            treated as independent of them. Biggest share is the hazard contributing most of it.
          </p>
          <p>
            Levels follow the chance in the month: 25% or more is High, 15% or more is Moderate, and
            anything less is Low. For an exact date the chance shown is for that week and the level
            stays the month&rsquo;s. The accuracy check on this page shows how the models did on years
            they never saw, and the past events on record can be checked against the archived records
            on the History page.
          </p>
        </details>
      )}
    </div>
  );
}
