import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import ForecastPeriodPicker from './ForecastPeriodPicker';
import {
  FIRE_CREDIT, FIRE_MODEL_LABEL, FLOOD_ON_MAP_NOTE, FORECAST_DISCLAIMER, FORECAST_ONLY_NOTE, IN_TRAINING_NOTE, PUROK_CAVEAT, SEVERITY_WORD, chanceText, defaultPeriod, isFireOnly, levelLabel,
  likelihoodInfo, periodLabel, periodMonth, periodParams, periodPastHeader, periodYearsText, smallChanceText,
  unavailableNote, withMonth,
} from './forecastLevels';
import './forecast.css';

/**
 * Which barangays a month, a month in a given year, or the week around a
 * date is likely to have a fire, and how likely. Pick the period; pick a
 * barangay row to see its whole year. A period that has started also shows
 * what actually happened in it.
 *
 * The table is fire's chance by month. A page filter set to Flood points to
 * the map, where flood susceptibility is (FLOOD_ON_MAP_NOTE: the same in every
 * month, so not a monthly table); Landslide shows FORECAST_ONLY_NOTE. Until the fire
 * model is trained, every row says it is unavailable. Not a weather forecast.
 *
 * Props:
 *   compact  dashboard card: top rows only, no month profile
 *   limit    rows shown when compact (default 5)
 *   hazard   the page's hazard filter, '' for all
 */
export default function BarangayLikelihood({ compact = false, limit = 5, hazard = '' }) {
  const [period, setPeriod] = useState(defaultPeriod);
  const [barangay, setBarangay] = useState(null); // { id, name } for the profile
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const fireShown = isFireOnly(hazard);

  useEffect(() => {
    if (!fireShown) { setData(null); return undefined; }
    let cancelled = false;
    setError('');
    historyApi.forecast({
      ...periodParams(period),
      hazard_type_name: 'Fire',
      ...(barangay ? { barangay: barangay.id } : {}),
    })
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError('Could not load the seasonal likelihood.'); });
    return () => { cancelled = true; };
  }, [period, fireShown, barangay]);

  if (!fireShown) {
    return (
      <div className="fc">
        <p className="db-empty">{hazard === 'Flood' ? FLOOD_ON_MAP_NOTE : FORECAST_ONLY_NOTE}</p>
      </div>
    );
  }

  const rows = data?.results || [];
  const shown = compact ? rows.slice(0, limit) : rows;
  // What actually happened, once a period with a year has started
  const outcome = data?.outcome;
  const showChance = !compact && rows.some((r) => r.method === 'model' || r.method === 'unavailable');
  const inTraining = shown.some((r) => r.in_training);
  const eventsText = (n) => (n ? `${n} event${n === 1 ? '' : 's'}` : 'None');
  // Fire with no figures is named, with its reason, never dropped silently
  const note = data ? unavailableNote(data) : '';
  // The chart comes from the model only; without it it has no bars, never counted ones
  const barNote = data?.profile_method === 'model'
    ? `Bar height is ${barangay ? 'the model\'s' : 'the average barangay\'s'} chance of at least one fire in that month.`
    : 'The model gives no chart for this period.';

  return (
    <div className="fc">
      <div className="fc-controls">
        <ForecastPeriodPicker value={period} onChange={setPeriod} />
      </div>

      {error && <p className="db-error" role="alert">{error}</p>}

      {/* What happened in a period that has started; the figures themselves come from the model */}
      {data?.year != null && outcome && (
        <p className="fc-note">
          {period.mode === 'date' ? `The week of ${periodLabel(period)}` : periodLabel(period)}
          {outcome.complete
            ? ` is over: ${outcome.events} event${outcome.events === 1 ? '' : 's'} happened.`
            : ` has started: ${outcome.events} event${outcome.events === 1 ? '' : 's'} so far.`}
        </p>
      )}

      {data && !rows.length && <p className="db-empty">No fire forecast is available for this period.</p>}

      {note && <p className="fc-note">{note}</p>}
      {inTraining && <p className="fc-note">{IN_TRAINING_NOTE}</p>}

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
              {showChance && <th scope="col">Chance</th>}
              {outcome && <th scope="col">{outcome.complete ? 'What happened' : 'So far'}</th>}
              {!compact && <th scope="col">Usual severity</th>}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const info = likelihoodInfo(r.method === 'unavailable' ? 'None' : r.level);
              const picked = barangay && barangay.id === r.barangay_id;
              return (
                <tr key={`${r.barangay_id}-${r.hazard_type}`} className={picked ? 'is-picked' : undefined}>
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
                      {levelLabel(r)}
                    </span>
                  </td>
                  <td>{periodYearsText(r, period)}</td>
                  {showChance && (
                    <td>
                      {r.method === 'unavailable'
                        ? <div className="fc-sub">{r.reason || 'Unavailable right now'}</div>
                        : chanceText(r) || '-'}
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

      {compact && rows.length > shown.length && (
        <p className="fc-more">The top {shown.length} of {rows.length} barangays.</p>
      )}

      {!compact && data?.profile && (
        <div className="fc-profile">
          <h3>
            Through the year: {barangay ? barangay.name : 'all of Talisay City'}
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

      {!compact && (
        <details className="db-method">
          <summary>How this is calculated</summary>
          <p>{data?.basis?.method || "Fire's prediction model is being rebuilt."}</p>
          <p>
            The {FIRE_MODEL_LABEL.charAt(0).toLowerCase() + FIRE_MODEL_LABEL.slice(1)} gives each purok a chance
            of a fire from its buildings, roads, land cover and distance to a fire station, never from how many
            fires it had. A barangay&rsquo;s chance combines its puroks&rsquo;. Levels follow the chance in the
            month: 25% or more is High, 15% or more is Moderate, and anything less is Low. For an exact date the
            chance shown is for that week and the level stays the month&rsquo;s. A model that cannot run is shown
            as unavailable, never guessed or counted. The past events on record can be checked against the
            archived records on the History page.
          </p>
          <p>{PUROK_CAVEAT}</p>
          <p>{FIRE_CREDIT}</p>
        </details>
      )}
    </div>
  );
}
