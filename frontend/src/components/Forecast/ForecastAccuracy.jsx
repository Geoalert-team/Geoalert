import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import { MONTHS, MODEL_LABELS, RAIN_ATTRIBUTION, likelihoodInfo } from './forecastLevels';
import './forecast.css';

const monthLabel = (ym) => {
  const [year, month] = ym.split('-');
  return `${MONTHS[Number(month) - 1].slice(0, 3)} ${year}`;
};
const span = ({ start, end }) => `${monthLabel(start)} to ${monthLabel(end)}`;
const percent = (share) => (share == null ? '-' : `${Math.round(share * 100)}%`);
const fixed = (value, places) => (value == null ? '-' : value.toFixed(places));

// No hazard is forecast by counting: a model that lost to it stays in use; too few records is unavailable
const VERDICT = {
  in_use: 'the model is in use',
  too_few_records: 'unavailable',
  in_use_not_better: 'in use',
  unavailable: 'unavailable',
};

const DASH = '–';
// n significant figures as a plain decimal: toPrecision, but never e-notation (0.00045, -0.0015, 150)
const sigFigs = (v, n) => {
  const text = Number(v).toPrecision(n);
  if (!text.includes('e')) return text;
  const exponent = Number(text.split('e')[1]);
  return exponent < 0 ? Number(text).toFixed(n - 1 - exponent) : String(Number(text));
};
const sig3 = (v) => (v == null ? DASH : sigFigs(v, 3));
// The real report's PR-AUCs and Brier skills are a few thousandths: two significant figures, the same for a value
// and its no-skill value, so 0.0015 (0.00045) never reads "0.00 (0.00045)"
const sig2 = (v) => (v == null ? DASH : sigFigs(v, 2));
const two = (v) => (v == null ? DASH : Number(v).toFixed(2));
// A chance as a percent: one decimal from 1%, two significant figures under it, so a real chance never reads "0.0%"
const chancePercent = (v) => {
  if (v == null) return DASH;
  return v > 0 && v < 0.01 ? `${sigFigs(v * 100, 2)}%` : `${(v * 100).toFixed(1)}%`;
};
const trimmed = (v, places) => Number(Number(v).toFixed(places)); // 3, 5.7, 9.5: no trailing zeros
const mm = (v) => (v == null ? DASH : `${trimmed(v, 2)} mm`);
const plural = (n, noun) => `${n} ${noun}${n === 1 ? '' : 's'}`;

// The two models a flood or landslide report compares, and the baselines it scores them against
const CONTENDERS = ['two_part', 'logistic_regression'];
const SHORT_NAMES = { two_part: 'two-part model', logistic_regression: 'pooled logistic regression' };
const BASELINE_LABELS = {
  climatology: 'overall rate',
  rate: 'barangay rate',
  persistence: 'day after an event day',
  pagasa_bands: 'PAGASA rain bands',
  rain_only: 'rain only',
  return_level: '2-year return-level rain',
  p95_7day: '7-day rain above its 95th percentile',
};
const modelLabel = (name) => MODEL_LABELS[name] || BASELINE_LABELS[name] || name;
const EVENT_COLUMNS = ["Hit barangays' chance", 'Day before', 'City chance', 'At High that month'];

/** "0.85 for the two-part model, 0.60 for the pooled logistic regression" over the contenders that were scored */
function perModel(models, pick, show) {
  return CONTENDERS.filter((n) => models[n] && !models[n].unavailable).map((n) => {
    const v = pick(models[n]);
    return v == null ? `not defined for the ${SHORT_NAMES[n]}` : `${show(v)} for the ${SHORT_NAMES[n]}`;
  }).join(', ');
}

function EventTable({ events }) {
  return (
    <div className="fc-table-wrap">
      <table className="fc-table fc-table-whole">
        <caption>Event by event</caption>
        <thead>
          <tr>
            <th scope="col" rowSpan={2}>Date</th>
            <th scope="col" rowSpan={2}>Record type</th>
            <th scope="col" rowSpan={2}>Storm</th>
            <th scope="col" rowSpan={2}>1-day rain</th>
            <th scope="col" rowSpan={2}>3-day rain</th>
            <th scope="col" rowSpan={2}>PAGASA band</th>
            {CONTENDERS.map((n) => <th key={n} scope="colgroup" colSpan={EVENT_COLUMNS.length}>{SHORT_NAMES[n]}</th>)}
          </tr>
          <tr>
            {CONTENDERS.flatMap((n) => EVENT_COLUMNS.map((h) => <th key={`${n}-${h}`} scope="col">{h}</th>))}
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.day}>
              <td>{e.day}</td>
              <td>{e.subtypes?.length ? e.subtypes.join(', ') : DASH}</td>
              <td>{e.storm || DASH}</td>
              <td>{mm(e.rain_1day)}</td>
              <td>{mm(e.rain_3day)}</td>
              <td>{e.band}</td>
              {CONTENDERS.flatMap((n) => {
                const m = e.models?.[n] || {};
                return [
                  <td key={`${n}-hit`}>{chancePercent(m.hit_chance)}</td>,
                  <td key={`${n}-before`}>{chancePercent(m.hit_chance_before)}</td>,
                  <td key={`${n}-city`}>{chancePercent(m.city_chance)}</td>,
                  <td key={`${n}-high`}>{m.high_barangays ?? DASH}</td>,
                ];
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BaselineTable({ models }) {
  return (
    <div className="fc-table-wrap">
      <table className="fc-table fc-table-whole">
        <caption>Against the baselines</caption>
        <thead>
          <tr>
            <th scope="col">Model</th>
            <th scope="col">Log score</th>
            <th scope="col">Brier skill vs overall rate</th>
            <th scope="col">Brier skill vs barangay rate</th>
            <th scope="col">PR-AUC (no skill)</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(models).map(([name, m]) => (m.unavailable ? (
            <tr key={name}>
              <td>{modelLabel(name)}</td>
              <td colSpan={4}>not available: {m.unavailable}</td>
            </tr>
          ) : (
            <tr key={name}>
              <td>{modelLabel(name)}</td>
              <td>{sig3(m.scores.log_loss)}</td>
              <td>{sig2(m.scores.brier_skill_climatology)}</td>
              <td>{sig2(m.scores.brier_skill_rate)}</td>
              <td>{m.scores.pr_auc == null ? DASH : `${sig2(m.scores.pr_auc)} (${sig2(m.scores.no_skill_pr_auc)})`}</td>
            </tr>
          )))}
        </tbody>
      </table>
    </div>
  );
}

// At break-even, warning at a chance of c costs (1 - c) / c false alarms per real event; the backend lists one per cut-off
function breakevenText(breakeven) {
  const counts = [...new Set((breakeven || []).map((b) => trimmed(b.false_alarms_per_event, 1)))].sort((a, b) => a - b);
  if (!counts.length) return null;
  return `At these cut-offs a warning pays off only if acting on about ${counts.join(' to ')} false alarms per real event is acceptable.`;
}

function OutsideTest({ outside }) {
  if (!outside) return null;
  if (outside.unavailable) return <p className="fc-note">{outside.unavailable}</p>;
  const { current, catalogue_to_geoalert: toCity, geoalert_to_catalogue: toCatalogue } = outside;
  const auc = (v) => (v == null ? 'not defined' : `AUC ${two(v)}`);
  return (
    <>
      <p className="fc-note">
        Outside the study years (NASA catalogue days): the pooled logistic regression ranked catalogue landslide days
        with {auc(current.auc)}, and expected {trimmed(current.expected, 1)} landslide days against {current.observed} observed.
      </p>
      <p className="fc-note">
        The two-part &quot;when&quot; model trained on the catalogue era and tested on GeoAlert days: {auc(toCity.auc)}.
        Trained on GeoAlert days and tested on the catalogue era: {auc(toCatalogue.auc)}.
      </p>
    </>
  );
}

/** The model's chances as first logged against what was reported since; shown only once rows are logged */
function LoggedBlock({ hazard, logged }) {
  const fire = hazard === 'Fire';
  const [low, high] = logged.events_interval;
  const events = logged.new_events || [];
  const given = (v) => (v == null ? 'not logged' : chancePercent(v));
  return (
    <div className="fc-logged">
      <h4>Since logging began</h4>
      <p className="fc-note">
        From {logged.first} to {logged.last}, {plural(logged.rows, fire ? 'barangay-month' : 'barangay-day')}{' '}
        {logged.rows === 1 ? 'was' : 'were'} logged: {plural(logged.events, 'reported event')} against{' '}
        {trimmed(logged.expected, 2)} expected (95% range {trimmed(low, 2)} to {trimmed(high, 2)}).
      </p>
      {events.length > 0 && (
        <div className="fc-table-wrap">
          <table className="fc-table fc-table-whole">
            <caption>Events since logging began</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Barangay</th>
                <th scope="col">Chance given</th>
                {!fire && <th scope="col">Day before</th>}
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={`${e.day}-${e.barangay_id}`}>
                  <td>{e.day}</td>
                  <td>{e.barangay || DASH}</td>
                  <td>{given(e.chance)}</td>
                  {!fire && <td>{given(e.chance_before)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RainTerrainAccuracy({ report }) {
  const { hazard, status } = report;
  if (status === 'unavailable') {
    return (
      <div className="fc-accuracy">
        <h3>{hazard}: rain and terrain model unavailable</h3>
        <p className="fc-note">{report.reason}</p>
      </div>
    );
  }
  const noun = hazard.toLowerCase();
  const { verdict, tests, limits = [], credits = [] } = report;
  const { loso } = tests;
  const label = MODEL_LABELS[report.in_use] || report.in_use;
  // a short heading; the reasons (with the real report, hundreds of characters) go in a list below it
  const opening = verdict.adopted
    ? `${hazard}: ${label}, in use — adopted under rule (${verdict.rule}).`
    : `${hazard}: ${label}, in use. The two-part model was tested and not adopted.`;
  const breakeven = breakevenText(loso.breakeven);
  return (
    <div className="fc-accuracy">
      <h3>{opening}</h3>
      {!verdict.adopted && verdict.reasons.length > 0 && (
        <ul className="fc-reasons">
          {verdict.reasons.map((text) => <li key={text}>{text}</li>)}
        </ul>
      )}
      {report.stale && (
        <p className="db-error" role="alert">
          Records have changed since this test was run; run manage.py test_hazard_models again.
        </p>
      )}
      <p className="fc-note">
        Tested by leaving out one storm or one month at a time and training on the rest:{' '}
        {plural(loso.hit_rows, `reported ${noun} barangay-day`)} on {plural(loso.event_days, 'day')}.
      </p>
      <EventTable events={tests.events || []} />
      <BaselineTable models={loso.models} />
      <ul className="fc-robustness">
        <li>When (reported {noun} days ranked above other days): AUC {perModel(loso.models, (m) => m.when?.auc, two)}.</li>
        <li>Where (hit barangays ranked above the rest on each reported {noun} day): AUC {perModel(loso.models, (m) => m.where?.auc, two)}.</li>
        <li>Lift (hit barangays among the top 5 of the day, against an even spread): {perModel(loso.models, (m) => m.where?.lift, (v) => trimmed(v, 1))}.</li>
      </ul>
      {breakeven && <p className="fc-note">{breakeven}</p>}
      <OutsideTest outside={tests.outside} />
      {report.logged && <LoggedBlock hazard={hazard} logged={report.logged} />}
      {limits.length > 0 && (
        <ul className="fc-limits">
          {limits.map((text) => <li key={text}>{text}</li>)}
        </ul>
      )}
      {credits.length > 0 && (
        <ul className="fc-credits">
          {credits.map((text) => <li key={text}>{text}</li>)}
        </ul>
      )}
    </div>
  );
}

/** Fire's two models side by side: the verdict, 80% range coverage, the paired test and the two checks on the model in use */
function FireCandidate({ candidate }) {
  const { verdict, window, models, difference, dispersion, dispersion_flag: wide, morans_i: moran } = candidate;
  const exposure = MODEL_LABELS.pooled_exposure;
  const inUse = MODEL_LABELS[candidate.in_use] || candidate.in_use;
  return (
    <div className="fc-candidate">
      {window && (
        <p className="fc-note">
          {verdict.adopted
            ? `${inUse}, in use. It replaced the ${MODEL_LABELS.current} after being tested on ${span(window)}.`
            : `${inUse}, in use. The ${exposure} was tested on ${span(window)}.`}
        </p>
      )}
      <p className="fc-note">{verdict.reasons.join(' ')}</p>
      {models.current && models.pooled_exposure && (
        <div className="fc-table-wrap">
          <table className="fc-table fc-table-whole">
            <caption>Fire models side by side</caption>
            <thead>
              <tr>
                <th scope="col">Model</th>
                <th scope="col">Log score</th>
                <th scope="col">80% range coverage</th>
              </tr>
            </thead>
            <tbody>
              {['current', 'pooled_exposure'].map((name) => (
                <tr key={name}>
                  <td>{MODEL_LABELS[name]}{candidate.in_use === name ? ' (in use)' : ''}</td>
                  <td>{fixed(models[name].log_score, 3)}</td>
                  <td>{percent(models[name].coverage80)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ul className="fc-robustness">
        {difference?.dm?.p != null && <li>Diebold-Mariano test of the difference: p = {two(difference.dm.p)}.</li>}
        {dispersion != null && (
          <li>
            {wide ? 'Counts spread wider than a Poisson' : 'Counts spread like a Poisson'} (dispersion {two(dispersion)}; 1 is a Poisson spread).
          </li>
        )}
        {moran?.i != null && (
          <li>
            {moran.flag ? 'Errors cluster in neighbouring barangays' : 'Errors do not cluster in neighbouring barangays'}{' '}
            (Moran&apos;s I {two(moran.i)}, p = {two(moran.p)}).
          </li>
        )}
      </ul>
    </div>
  );
}

function HazardAccuracy({ report }) {
  const { hazard, status, train, test, model, counting, levels, candidate, logged } = report;
  return (
    <div className="fc-accuracy">
      <h3>{hazard}: {VERDICT[status]}</h3>
      {status === 'too_few_records' ? (
        <p className="fc-note">
          It has too few records to train and test a model yet
          {train ? ` (${train.events} to train on, ${test.events} to test on)` : ''}, so the likelihood shows it as
          unavailable.
        </p>
      ) : (
        <>
          <p className="fc-note">
            Trained on {span(train)} ({train.events} events), tested on {span(test)} ({test.events} events it never saw).
            {status === 'in_use_not_better'
              && ' The model did not beat counting on those months. It stays in use: no hazard is forecast by counting.'}
          </p>
          <div className="fc-table-wrap">
            <table className="fc-table fc-table-whole">
              <thead>
                <tr><th scope="col">Measure</th><th scope="col">Model</th><th scope="col">Counting</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td>Error in the chance (Brier, lower is better)</td>
                  <td>{fixed(model.brier, 3)}</td>
                  <td>{fixed(counting.brier, 3)}</td>
                </tr>
                <tr>
                  <td>Events in its top 5 barangays each month</td>
                  <td>{percent(model.top_share)}</td>
                  <td>{percent(counting.top_share)}</td>
                </tr>
                <tr>
                  <td>Ranking skill (AUC, 0.5 is guessing)</td>
                  <td>{fixed(model.auc, 2)}</td>
                  <td>{fixed(counting.auc, 2)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="fc-note">Did the model&rsquo;s levels hold up on those months?</p>
          <div className="fc-table-wrap">
            <table className="fc-table fc-table-whole">
              <thead>
                <tr>
                  <th scope="col">Level</th>
                  <th scope="col">Barangay-months</th>
                  <th scope="col">Chance it gave</th>
                  <th scope="col">Actually had an event</th>
                  <th scope="col">Events</th>
                </tr>
              </thead>
              <tbody>
                {levels.map((row) => (
                  <tr key={row.level}>
                    <td>{likelihoodInfo(row.level).label}</td>
                    <td>{row.rows}</td>
                    <td>{percent(row.chance)}</td>
                    <td>{percent(row.happened)}</td>
                    <td>{row.events}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {candidate && <FireCandidate candidate={candidate} />}
      {logged && <LoggedBlock hazard={hazard} logged={logged} />}
    </div>
  );
}

/**
 * How each hazard type's trained model did against counting on months it
 * never saw (backend apps/history/model_forecast.py and hazard_models.py).
 * Every hazard's likelihood comes from its model; counting is only the
 * benchmark. It always reads real records, so it takes no filters from the page.
 */
export default function ForecastAccuracy() {
  const [hazards, setHazards] = useState(null);
  const [combinedNote, setCombinedNote] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    historyApi.forecastAccuracy()
      .then((d) => { if (!cancelled) { setHazards(d.hazards); setCombinedNote(d.combined_note || ''); } })
      .catch(() => { if (!cancelled) setError('The accuracy check could not be loaded right now.'); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="fc">
      <h2>Model accuracy</h2>
      <p className="db-card-sub">
        Every hazard always uses its model; counting is only the benchmark it is tested against, and this card says
        when a model does not beat it.
      </p>
      {error && <p className="db-error" role="alert">{error}</p>}
      {!error && !hazards && <p className="db-empty">Loading the accuracy check…</p>}
      {hazards && !hazards.length && <p className="db-empty">No real records to test a model on yet.</p>}
      {hazards?.map((report) => (report.kind === 'rain_terrain'
        ? <RainTerrainAccuracy key={report.hazard} report={report} />
        : <HazardAccuracy key={report.hazard} report={report} />))}
      {combinedNote && <p className="fc-note">{combinedNote}</p>}
      {hazards?.some((r) => r.kind === 'rain_terrain' && r.status !== 'unavailable') && (
        <p className="fc-note">
          Rain data from <a href={RAIN_ATTRIBUTION.links[0].href} target="_blank" rel="noopener noreferrer">{RAIN_ATTRIBUTION.links[0].label}</a>{' '}
          (<a href={RAIN_ATTRIBUTION.links[1].href} target="_blank" rel="noopener noreferrer">{RAIN_ATTRIBUTION.links[1].label}</a>), processed into hazard chances by GeoAlert
        </p>
      )}
      {hazards?.length > 0 && (
        <p className="fc-note">
          The model estimates how likely a month is in each barangay. It cannot say where or when a particular event
          will start.
        </p>
      )}
    </div>
  );
}
