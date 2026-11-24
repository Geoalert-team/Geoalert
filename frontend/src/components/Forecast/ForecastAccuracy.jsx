import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import { FIRE_CREDIT, FIRE_MODEL_LABEL, FLOOD_WORD, NOT_ASSESSED, SEVERITY_WORD } from './forecastLevels';
import './forecast.css';

/**
 * How the fire model did on fires it never saw, and how the flood
 * susceptibility model did on floods it never saw (backend
 * views.ForecastAccuracyView, which serves train_fire_model's and
 * train_flood_model's reports). Landslide is being rebuilt. An entry the
 * backend cannot give is shown as unavailable with its reason. It always
 * reads real records, so it takes no filters from the page.
 */

/** Shown when new located floods keep falling outside Red and Orange (backend flood_rules.monitoring) */
export const UNDER_REVIEW = 'Under review: recent floods fall outside the flagged areas';

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

// The flood candidates (backend flood_training), simplest first, and the benchmark they must beat
const FLOOD_FAMILY = {
  logistic_regression: 'Logistic regression',
  maxent_hinge: 'MaxEnt-type (hinge logistic)',
  xgboost: 'XGBoost',
  neural_network: 'Neural network',
  noah_only: "UP NOAH's map on its own (the benchmark)",
};

const count = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'));
const signed = (v) => (v == null ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(3)}`);
const yesNo = (v) => (v ? 'Yes' : 'No');
const floodLevelWord = (level) => FLOOD_WORD[level] || NOT_ASSESSED;

function FloodSincePublishing({ since }) {
  if (!since) return null;
  return (
    <>
      <h4>Since publishing</h4>
      {since.under_review && <p className="fc-note"><strong>{UNDER_REVIEW}</strong></p>}
      <p className="fc-note">
        {since.n
          ? `${since.in_red_orange} of ${since.n} located ${since.n === 1 ? 'flood' : 'floods'} since the levels were `
            + 'published fell in Red or Orange.'
          : 'No located flood has been recorded since the levels were published.'}
      </p>
      {since.misses?.length > 0 && (
        <p className="fc-note">
          Outside Red and Orange: {since.misses.map((m) => `${m.day} (${m.purok}, ${m.level})`).join(', ')}.
        </p>
      )}
    </>
  );
}

/**
 * The flood susceptibility model's report (train_flood_model), in order: where
 * the levels come from, the candidates, the choice and the four checks, the
 * test on floods it never saw, the barangay check, the classes, how it has
 * done since publishing, its limits and the credits.
 */
export function FloodModelReport({ report }) {
  const fallback = report.source === 'noah';
  const chosen = FLOOD_FAMILY[report.choice?.chosen] || report.choice?.chosen;
  const acceptance = report.acceptance || {};
  const test = report.temporal_test || {};
  const eosrs = test.eosrs;
  const levels = report.classes?.levels || {};
  const notAssessed = Object.entries(report.classes?.not_assessed || {});
  return (
    <section className="fc-accuracy">
      <h3>Flood: susceptibility by purok</h3>
      <p className="fc-sub">{report.basis}</p>
      <p className="fc-sub">
        {fallback
          ? `In use: the NOAH fallback, version ${report.version}. The machine-learning model (${chosen}) did not `
            + "pass every check, so the levels come from UP NOAH's 25-year flood model, classed by the survey's "
            + 'flood spots.'
          : `In use: the machine-learning model (${chosen}), version ${report.version}.`}
        {report.built_at && ` Built ${report.built_at.slice(0, 10)}.`}
      </p>
      {fallback && report.fallback?.note && <p className="fc-note">{report.fallback.note}</p>}

      <h4>The candidates and the rule</h4>
      <p className="fc-note">
        Trained on {count(report.survey_spots)} flooded survey spots and {count(report.dry_spots)} that stayed dry,
        against {count(report.domain_buildings)} buildings in the surveyed floodplain ({count(report.valid_buildings)}
        {' '}on ground like the survey&apos;s). Each candidate was scored on barangays it never saw. The Boyce index
        (−1 to 1) checks that more flood spots fall where the scores are higher; AUC 0.5 is chance. A more complex model
        replaces a simpler one only if it is better with 95% confidence.
      </p>
      <div className="fc-table-wrap">
        <table className="fc-table fc-table-whole fc-candidates">
          <thead>
            <tr><th scope="col">Model</th><th scope="col">Boyce index (95% interval)</th><th scope="col">AUC</th></tr>
          </thead>
          <tbody>
            {(report.candidates || []).map((c) => (
              <tr key={c.name}>
                <td>{FLOOD_FAMILY[c.name] || c.name}{c.name === report.choice?.chosen ? ' (chosen)' : ''}</td>
                <td>{scoreText({ value: c.boyce, low: c.boyce_low, high: c.boyce_high }, 2, false)}</td>
                <td>{fmt(c.auc, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(report.choice?.comparisons || []).map((c) => (
        <p key={`${c.candidate}-${c.against}`} className="fc-note">
          {`${FLOOD_FAMILY[c.candidate] || c.candidate} against ${FLOOD_FAMILY[c.against] || c.against}: Boyce gain `
            + `${signed(c.gain)} (${signed(c.low)} to ${signed(c.high)}), ${c.adopted ? 'adopted' : 'not adopted'}.`}
        </p>
      ))}

      <h4>The checks (all four must pass for the model to be used)</h4>
      <ul className="fc-note">
        {(acceptance.gates || []).map((g) => (
          <li key={g.gate}>{`${g.gate}: ${g.passed ? 'passed' : 'failed'}. ${g.detail}`}</li>
        ))}
      </ul>
      {(acceptance.reasons || []).map((r) => <p key={r} className="fc-note">{r}</p>)}

      <h4>The test: floods it never saw</h4>
      {fallback && (
        <p className="fc-note">
          These checks scored the machine-learning model, which is not in use; the last column gives each
          flood&apos;s level on the map in use.
        </p>
      )}
      {test.mananga_points?.length > 0 && (
        <div className="fc-table-wrap">
          <table className="fc-table fc-table-whole">
            <caption className="fc-sub">GeoAlert&apos;s own flood records on the lower Mananga</caption>
            <thead>
              <tr>
                <th scope="col">Day</th><th scope="col">Barangay</th>
                <th scope="col">{fallback ? 'Machine-learning model (not in use)' : 'Level of its area'}</th>
                {fallback && <th scope="col">Map in use</th>}
              </tr>
            </thead>
            <tbody>
              {test.mananga_points.map((p) => (
                <tr key={`${p.day}-${p.purok_id}`}>
                  <td>{p.day}</td>
                  <td>{p.barangay}</td>
                  <td>{floodLevelWord(p.level)}</td>
                  {fallback && <td>{floodLevelWord(p.published_level)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(test.elsewhere || []).map((p) => (
        <p key={`${p.day}-${p.barangay}`} className="fc-note">{`${p.day}, ${p.barangay}: ${p.note}`}</p>
      ))}
      {eosrs && (
        <p className="fc-note">
          {`Typhoon Tino's satellite flood map (EOS-RS, November 2025), over the ${count(eosrs.flagged_buildings)} `
            + `buildings it marks flooded: Boyce ${fmt(eosrs.boyce, 2)}, AUC ${fmt(eosrs.auc, 2)}. ${eosrs.note}`}
        </p>
      )}
      {test.dry_spots?.length > 0 && (
        <p className="fc-note">
          {`Survey spots that stayed dry: ${test.dry_spots.map((d) => fmt(d.share_of_flood_spots_scoring_lower, 0, true))
            .join(' and ')} of the flooded spots scored lower than them.`}
        </p>
      )}

      {report.barangay_check?.length > 0 && (
        <>
          <h4>The barangay check{fallback ? ' (the machine-learning model, not in use)' : ''}</h4>
          <div className="fc-table-wrap">
            <table className="fc-table fc-table-whole">
              <thead>
                <tr>
                  <th scope="col">Barangay</th><th scope="col">Buildings</th><th scope="col">In Red or Orange</th>
                  <th scope="col">Tino flood on record</th><th scope="col">Any flood on record</th>
                </tr>
              </thead>
              <tbody>
                {report.barangay_check.map((b) => (
                  <tr key={b.barangay}>
                    <td>{b.barangay}</td>
                    <td>{count(b.buildings)}</td>
                    <td>{fmt(b.share_red_orange, 0, true)}</td>
                    <td>{yesNo(b.tino_record)}</td>
                    <td>{yesNo(b.any_flood_record)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h4>The levels</h4>
      <div className="fc-table-wrap">
        <table className="fc-table fc-table-whole">
          <thead>
            <tr>
              <th scope="col">Level</th><th scope="col">Areas</th><th scope="col">Buildings</th>
              <th scope="col">Survey flood spots</th>
            </tr>
          </thead>
          <tbody>
            {['Red', 'Orange', 'Green'].filter((k) => levels[k]).map((k) => (
              <tr key={k}>
                <td>{FLOOD_WORD[k]}</td>
                <td>{count(levels[k].puroks)}</td>
                <td>{count(levels[k].buildings)}</td>
                <td>{count(levels[k].field_spots)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {notAssessed.length > 0 && (
        <p className="fc-note">
          {`${NOT_ASSESSED}: ${notAssessed.map(([reason, n]) => `${reason} (${n})`).join('; ')}.`}
        </p>
      )}

      <FloodSincePublishing since={report.since_publishing} />

      {report.limits?.length > 0 && (
        <>
          <h4>Limits</h4>
          <ul className="fc-note">{report.limits.map((l) => <li key={l}>{l}</li>)}</ul>
        </>
      )}
      {(report.credits || []).map((c) => <p key={c} className="fc-note">{c}</p>)}
    </section>
  );
}

/** One hazard's entry on the card: its reason when unavailable, else the fire or the flood report */
export function ForecastAccuracyEntry({ entry }) {
  if (entry.status === 'unavailable') {
    return (
      <section className="fc-accuracy">
        <h3>{entry.hazard}: unavailable</h3>
        {entry.reason && <p className="fc-sub">{entry.reason}</p>}
      </section>
    );
  }
  return entry.kind === 'flood_purok' ? <FloodModelReport report={entry} /> : <FireModelReport report={entry} />;
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
        How the fire model did on fires it never saw, and the flood model on floods it never saw. Counting past
        fires is only a comparison here, never the prediction.
      </p>
      {error && <p className="db-error" role="alert">{error}</p>}
      {!error && !hazards && <p className="db-empty">Loading the accuracy check…</p>}
      {hazards && !hazards.length && <p className="db-empty">No real records to test a model on yet.</p>}
      {hazards?.map((entry) => <ForecastAccuracyEntry key={entry.hazard} entry={entry} />)}
      {hazards && <p className="fc-note">Landslide predictions are being rebuilt.</p>}
    </div>
  );
}
