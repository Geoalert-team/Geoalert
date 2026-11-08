import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import { MONTHS, likelihoodInfo } from './forecastLevels';
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
};

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
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    historyApi.forecastAccuracy()
      .then((d) => { if (!cancelled) setHazards(d.hazards); })
      .catch(() => { if (!cancelled) setError('The accuracy check could not be loaded right now.'); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="fc">
      <h2>Model accuracy</h2>
      <p className="db-card-sub">
        A hazard type uses the trained model only if it beats counting on months it never saw. Real records only.
      </p>
      {error && <p className="db-error" role="alert">{error}</p>}
      {!error && !hazards && <p className="db-empty">Loading the accuracy check…</p>}
      {hazards && !hazards.length && <p className="db-empty">No real records to test a model on yet.</p>}
      {hazards?.map((report) => <HazardAccuracy key={report.hazard} report={report} />)}
      {hazards?.length > 0 && (
        <p className="fc-note">
          The model estimates how likely a month is in each barangay. It cannot say where or when a particular event
          will start.
        </p>
      )}
    </div>
  );
}
