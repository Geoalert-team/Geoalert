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

const VERDICT = {
  in_use: 'the model is in use',
  not_better: 'stays on counting',
  too_few_records: 'stays on counting',
  in_use_not_better: 'in use',
  unavailable: 'unavailable',
};

const DASH = '–';
const sig3 = (v) => (v == null ? DASH : Number(v).toPrecision(3));
const two = (v) => (v == null ? DASH : Number(v).toFixed(2));
const pct1 = (v) => (v == null ? DASH : `${(v * 100).toFixed(1)}%`);
const joinYears = (years) => (years.length > 1 ? `${years.slice(0, -1).join(', ')} and ${years[years.length - 1]}` : years.join(''));

function aucLine(label, auc) {
  if (auc == null) return `${label}: not defined (it needs both outcomes).`;
  const suffix = auc < 0.5 ? ' — below chance' : auc < 0.6 ? ' — about chance' : '';
  return `${label}: AUC ${two(auc)} (0.5 is chance, 1 is perfect)${suffix}.`;
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
  const { winner, candidates, benchmark, no_skill: noSkill, calibration, monthly_levels: levels = [] } = report;
  const label = MODEL_LABELS[winner] || winner;
  const years = (report.folds || []).map((f) => f.test_year);
  const winnerYears = candidates[winner].per_year;
  const reported = winnerYears.reduce((sum, y) => sum + y.positives, 0);
  const days = report.timing_auc?.event_days;
  const expected = (year) => calibration?.per_year?.find((y) => y.year === year)?.expected;
  const counting = (year) => benchmark.per_year.find((y) => y.year === year)?.log_loss;
  const table1 = [
    ...Object.entries(candidates).map(([name, c]) => [`${MODEL_LABELS[name] || name}${name === winner ? ' (in use)' : ''}`, c.pooled]),
    ['Counting benchmark', benchmark.pooled],
    ['No skill', noSkill.pooled],
  ];
  // Two kinds of dash, each with its own footnote: a metric not defined (Tables 1 and 2), a level never given (Table 3)
  const anyUndefined = table1.some(([, p]) => [p.log_loss, p.brier, p.roc_auc, p.pr_auc].some((v) => v == null))
    || winnerYears.some((y) => [expected(y.year), y.log_loss, counting(y.year)].some((v) => v == null));
  const anyLevelNotGiven = levels.some((l) => l.rows === 0);
  const limits = report.limits || [];
  return (
    <div className="fc-accuracy">
      <h3>
        {hazard}: rain and terrain model ({label}), in use
        {status === 'in_use_not_better' && ' — did not beat counting on the years it never saw'}
      </h3>
      {report.stale && (
        <p className="db-error" role="alert">
          Records have changed since this test was run; run manage.py test_hazard_models again.
        </p>
      )}
      <p className="fc-note">
        Tested on {joinYears(years)}, each year trained only on the years before it: {reported} reported rows
        {days != null && ` on ${days} days`} in those years.
      </p>
      <div className="fc-table-wrap">
        <table className="fc-table fc-table-whole">
          <thead>
            <tr>
              <th scope="col">Model</th>
              <th scope="col">Log loss</th>
              <th scope="col">Brier</th>
              <th scope="col">ROC-AUC</th>
              <th scope="col">PR-AUC</th>
            </tr>
          </thead>
          <tbody>
            {table1.map(([name, p]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{sig3(p.log_loss)}</td>
                <td>{sig3(p.brier)}</td>
                <td>{two(p.roc_auc)}</td>
                <td>{two(p.pr_auc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="fc-note">
        Pooled over the three test years. Each year&apos;s model has its own base rate, so even the no-skill row&apos;s
        pooled ROC-AUC is not 0.5.
      </p>
      <div className="fc-table-wrap">
        <table className="fc-table fc-table-whole">
          <thead>
            <tr>
              <th scope="col">Year</th>
              <th scope="col">Reported events</th>
              <th scope="col">Expected events</th>
              <th scope="col">Model log loss</th>
              <th scope="col">Counting log loss</th>
            </tr>
          </thead>
          <tbody>
            {winnerYears.map((y) => (
              <tr key={y.year}>
                <td>{y.year}</td>
                <td>{y.positives}</td>
                <td>{two(expected(y.year))}</td>
                <td>{sig3(y.log_loss)}</td>
                <td>{sig3(counting(y.year))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="fc-note">Did the model&rsquo;s levels hold up on those years?</p>
      <div className="fc-table-wrap">
        <table className="fc-table fc-table-whole">
          <thead>
            <tr>
              <th scope="col">Level</th>
              <th scope="col">Barangay-months</th>
              <th scope="col">Average chance</th>
              <th scope="col">Share with an event</th>
            </tr>
          </thead>
          <tbody>
            {levels.map((row) => (
              <tr key={row.level}>
                <td>{likelihoodInfo(row.level).label}</td>
                <td>{row.rows}</td>
                <td>{row.rows === 0 ? DASH : pct1(row.chance)}</td>
                <td>{row.rows === 0 ? DASH : pct1(row.happened)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {anyUndefined && <p className="fc-note">{DASH} not defined: no reported event in that set.</p>}
      {anyLevelNotGiven && <p className="fc-note">{DASH} no barangay-month was given this level.</p>}
      <ul className="fc-robustness">
        <li>{aucLine('Barangays it never saw (each left out of training in turn), ranked by average chance', report.lobo_auc?.auc)}</li>
        <li>{aucLine(`When: reported ${noun} days ranked above other days`, report.timing_auc?.auc)}</li>
        <li>{aucLine(`Where: hit barangays ranked above the rest on each reported ${noun} day`, report.place_auc?.mean)}</li>
        {Array.isArray(report.camp_iv) && (report.camp_iv.length === 0
          ? <li>No landslide in the last test year fell in a barangay unseen in training.</li>
          : report.camp_iv.map((c) => (
            <li key={`${c.barangay_id}-${c.day}`}>
              A landslide in a barangay never seen with one in training ({c.day}) ranked above {Number(c.percentile).toFixed(1)}% of that year&apos;s barangay-days.
            </li>
          )))}
        {report.sensitivity && (
          <li>
            With no records left out ({report.sensitivity.study_positives} reported barangay-days): log loss {sig3(report.sensitivity.log_loss)}, ROC-AUC {two(report.sensitivity.roc_auc)}.
          </li>
        )}
      </ul>
      {limits.length > 0 && (
        <ul className="fc-limits">
          {limits.map((text) => <li key={text}>{text}</li>)}
        </ul>
      )}
    </div>
  );
}

function HazardAccuracy({ report }) {
  const { hazard, status, train, test, model, counting, levels } = report;
  return (
    <div className="fc-accuracy">
      <h3>{hazard}: {VERDICT[status]}</h3>
      {status === 'too_few_records' ? (
        <p className="fc-note">
          It has too few records to train and test a model yet
          {train ? ` (${train.events} to train on, ${test.events} to test on)` : ''}.
        </p>
      ) : (
        <>
          <p className="fc-note">
            Trained on {span(train)} ({train.events} events), tested on {span(test)} ({test.events} events it never saw).
            {status === 'not_better' && ' The model did not beat counting on those months, so counting stays.'}
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
    </div>
  );
}

/**
 * How each hazard type's trained model did against counting on months it
 * never saw (backend apps/history/model_forecast.py), and whether it is in
 * use. The same test decides which method the likelihood above shows. It
 * always reads real records, so it takes no filters from the page.
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
        Fire uses its model only if it beats counting. Flood and landslide always use their rain and terrain model,
        and this card says when it does not beat counting.
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
          Rain data by <a href={RAIN_ATTRIBUTION.links[0].href} target="_blank" rel="noopener noreferrer">{RAIN_ATTRIBUTION.links[0].label}</a>{' '}
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
