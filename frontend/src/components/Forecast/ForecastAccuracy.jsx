import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import { FIRE_CREDIT, FIRE_MODEL_LABEL, SEVERITY_WORD } from './forecastLevels';
import './forecast.css';

/**
 * How the fire model did on fires it never saw (backend
 * views.ForecastAccuracyView, which serves train_fire_model's report). Fire
 * is the only hazard with a prediction model since 2026-11-22; flood and
 * landslide are being rebuilt. An entry the backend cannot give is shown as
 * unavailable with its reason. It always reads real records, so it takes no
 * filters from the page.
 */

const FAMILY = {
  logistic_regression: 'Logistic regression',
  random_forest: 'Random forest',
  adaboost: 'AdaBoost',
  xgboost: 'XGBoost',
  neural_network: 'Neural network',
};

// What the model is measured against; counting past fires is one of them, never the prediction
const COMPARISON = {
  comparison_same_everywhere: 'Same chance everywhere',
  comparison_buildings: 'In proportion to buildings',
  comparison_historical_frequency: "The area's own past fires (counting, as a yardstick only)",
};

// [key, label, digits, as a percentage]
const SCORES = [
  ['log_loss', 'Log loss (lower is better)', 4, false],
  ['brier', 'Brier score (lower is better)', 4, false],
  ['roc_auc', 'ROC-AUC (0.5 is chance)', 2, false],
  ['pr_auc', 'PR-AUC', 3, false],
  ['calibration_slope', 'Calibration slope (1 is ideal)', 2, false],
  ['top20_share', 'Fires in the top 20% of purok-months', 0, true],
];

const fmt = (v, digits, pct) => {
  if (v == null) return '—';
  return pct ? `${Math.round(v * 100)}%` : Number(v).toFixed(digits);
};

/** "0.68 (0.57–0.75)": a score with its 95% interval from resampling barangays */
function scoreText(s, digits, pct) {
  if (!s || s.value == null) return '—';
  const range = s.low != null && s.high != null ? ` (${fmt(s.low, digits, pct)}–${fmt(s.high, digits, pct)})` : '';
  return `${fmt(s.value, digits, pct)}${range}`;
}

function ScoreTable({ columns, caption }) {
  return (
    <div className="fc-table-wrap">
      <table className="fc-table fc-table-whole">
        {caption && <caption className="fc-sub">{caption}</caption>}
        <thead>
          <tr>
            <th scope="col">Score</th>
            {columns.map(([label]) => <th key={label} scope="col">{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {SCORES.map(([key, label, digits, pct]) => (
            <tr key={key}>
              <td>{label}</td>
              {columns.map(([name, scores]) => <td key={name}>{scoreText(scores?.[key], digits, pct)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function withComparisons(label, scores, comparison) {
  return [[label, scores], ...Object.entries(comparison || {}).map(([k, v]) => [COMPARISON[k] || k, v])];
}

function Prospective({ logged }) {
  if (!logged) {
    return (
      <p className="fc-note">
        No month has been logged and scored yet. Each month&apos;s purok figures are kept as issued and scored on
        fires that come after them; the first verdict is due after about 12 months.
      </p>
    );
  }
  const s = logged.scores || {};
  return (
    <p className="fc-note">
      From {logged.first} to {logged.last}: {logged.rows} purok-months logged, {logged.fires_after}{' '}
      {logged.fires_after === 1 ? 'fire' : 'fires'} after the figures were issued against {logged.expected} expected.
      Log loss {fmt(s.log_loss, 4)}, Brier {fmt(s.brier, 4)}, ROC-AUC {fmt(s.roc_auc, 2)}.
    </p>
  );
}

export function FireModelReport({ report }) {
  if (report.status === 'unavailable') {
    return (
      <section className="fc-accuracy">
        <h3>{report.hazard}: unavailable</h3>
        {report.reason && <p className="fc-sub">{report.reason}</p>}
      </section>
    );
  }
  const test = report.test || {};
  const sens = report.sensitivity || {};
  const green = (test.levels || []).find((r) => r.level === 'Green');
  return (
    <section className="fc-accuracy">
      <h3>Fire: {FIRE_MODEL_LABEL}</h3>
      {report.model && (
        <p className="fc-sub">
          In use: {FAMILY[report.model.family] || report.model.family} ({report.model.settings?.label}),
          version {report.version}. Trained on fires from {report.trained?.start} to {report.trained?.end}.
        </p>
      )}

      <h4>The candidates and the rule</h4>
      <p className="fc-note">
        Each model was scored leaving one year out. Another model replaces logistic regression only if it is
        better with 95% confidence.
      </p>
      {(report.verdict?.reasons || []).map((r) => <p key={r} className="fc-note">{r}</p>)}
      <div className="fc-table-wrap">
        <table className="fc-table fc-table-whole fc-candidates">
          <thead>
            <tr><th scope="col">Model</th><th scope="col">Settings</th><th scope="col">Log loss</th><th scope="col">Brier</th></tr>
          </thead>
          <tbody>
            {(report.candidates || []).map((c) => (
              <tr key={`${c.family}-${c.label}`}>
                <td>{FAMILY[c.family] || c.family}</td>
                <td>{c.label}</td>
                <td>{fmt(c.log_loss, 4)}</td>
                <td>{fmt(c.brier, 4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h4>The test: {test.window?.start} to {test.window?.end}, fires it never saw</h4>
      <ScoreTable columns={withComparisons('Fire model', test.scores, test.comparison)} />
      {test.levels && (
        <div className="fc-table-wrap">
          <table className="fc-table fc-table-whole">
            <thead>
              <tr>
                <th scope="col">Level</th><th scope="col">Share of purok-months</th><th scope="col">Fires</th>
                <th scope="col">Caught at this level or higher</th>
              </tr>
            </thead>
            <tbody>
              {test.levels.map((r) => (
                <tr key={r.level}>
                  <td>{SEVERITY_WORD[r.level] || r.level}</td>
                  <td>{fmt(r.share, 0, true)}</td>
                  <td>{r.fires}</td>
                  <td>{fmt(r.recall, 0, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {green && test.fires != null && (
        <p className="fc-note">Fires in Low (missed by the levels): {green.fires} of {test.fires}.</p>
      )}

      {report.barangay_check && (
        <>
          <h4>The barangay check (BFP&apos;s own barangay field)</h4>
          <ScoreTable
            columns={withComparisons('Fire model', report.barangay_check.scores, report.barangay_check.comparison)}
          />
        </>
      )}

      <h4>Puroks drawn from fire addresses</h4>
      <ScoreTable
        columns={[
          [`Drawn from a fire address (${sens.named_areas ?? '—'} areas)`, sens.fire_log_named],
          [`Other areas (${sens.other_areas ?? '—'})`, sens.others],
          ['Each barangay left out in turn', report.leave_one_barangay_out],
        ]}
      />
      {report.caveat && <p className="fc-note"><strong>{report.caveat}</strong></p>}

      <h4>Scored as it goes</h4>
      <Prospective logged={report.logged} />

      {report.unplaced?.length > 0 && (
        <p className="fc-note">
          Left out of training because the BFP address names no purok:{' '}
          {report.unplaced.map((u) => `${u.date} (${u.barangay})`).join(', ')}.
        </p>
      )}
      <p className="fc-note">{report.credit || FIRE_CREDIT}</p>
    </section>
  );
}

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
        How the fire model did on fires it never saw. Counting past fires is only a comparison here, never the
        prediction.
      </p>
      {error && <p className="db-error" role="alert">{error}</p>}
      {!error && !hazards && <p className="db-empty">Loading the accuracy check…</p>}
      {hazards && !hazards.length && <p className="db-empty">No real records to test a model on yet.</p>}
      {hazards?.map((report) => <FireModelReport key={report.hazard} report={report} />)}
      {hazards && <p className="fc-note">Flood and landslide predictions are being rebuilt.</p>}
    </div>
  );
}
