import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import { FIRE_CREDIT, FIRE_MODEL_LABEL, FLOOD_WORD, LANDSLIDE_WORD, NOT_ASSESSED, SEVERITY_WORD } from './forecastLevels';
import './forecast.css';

/**
 * How the fire model did on fires it never saw, and how the flood
 * susceptibility model did on floods it never saw (backend
 * views.ForecastAccuracyView, which serves train_fire_model's and
 * train_flood_model's reports) and how the landslide susceptibility model did
 * on landslides it never saw (train_landslide_model's report). An entry the
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
  const own = report.source === 'geoalert';
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
        {own
          ? `Trained on ${count(report.own_spots)} flooded spots from GeoAlert's located flood records, against `
            + `${count(report.domain_buildings)} buildings in the area they cover (${count(report.valid_buildings)} `
            + 'on ground like theirs).'
          : `Trained on ${count(report.survey_spots)} flooded survey spots and ${count(report.dry_spots)} that stayed `
            + `dry, against ${count(report.domain_buildings)} buildings in the surveyed floodplain `
            + `(${count(report.valid_buildings)} on ground like the survey's).`}
        {' '}Each candidate was scored on barangays it never saw. The Boyce index
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
      {own && test.held_back?.length > 0 && (
        <div className="fc-table-wrap">
          <table className="fc-table fc-table-whole">
            <caption className="fc-sub">{`The ${test.season} wet season's flood spots, held back`}</caption>
            <thead>
              <tr><th scope="col">Day</th><th scope="col">Barangay</th><th scope="col">Level of its area</th></tr>
            </thead>
            <tbody>
              {test.held_back.map((p, i) => (
                // eslint-disable-next-line react/no-array-index-key -- two spots can share a day and a purok
                <tr key={i}>
                  <td>{p.day}</td>
                  <td>{p.barangay}</td>
                  <td>{floodLevelWord(p.level)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
      {!own && test.dry_spots?.length > 0 && (
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
              <th scope="col">{own ? 'Flood spots' : 'Survey flood spots'}</th>
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

// ---- Landslide (backend landslide_run.run's report, served by views.landslide_accuracy_entry) ----

/** Shown when new located landslides keep falling outside Red and Orange (backend landslide_purok.UNDER_REVIEW) */
export const LANDSLIDE_UNDER_REVIEW = 'Under review: recent landslides fall outside the flagged areas';

const landslideLevelWord = (level) => LANDSLIDE_WORD[level] || NOT_ASSESSED;

// backend landslide_training's candidates, simplest first, and the benchmark they must beat
const LANDSLIDE_FAMILY = {
  logistic_regression: 'Logistic regression',
  xgboost: 'XGBoost',
  neural_network: 'Neural network',
  noah_only: "UP NOAH's map on its own (the benchmark)",
};

// The clues whose values are held to the training range, in words (backend landslide_features.CLIP_COLUMNS)
const CLIPPED_CLUE = {
  dist_road_m: 'distance to a road',
  lc_trees: 'tree cover',
  lc_rangeland: 'rangeland',
  lc_crops: 'cropland',
  lc_built: 'built-up land',
  lc_bare: 'bare ground',
};

const EVENT_REGION = { ph: 'Philippines', world: 'Elsewhere in the world' };
const capitalise = (word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`;
const SHORT_MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const SMALL_WORDS = new Set(['of', 'the', 'and']);
/**
 * An event key in words: 'egay' -> 'Egay'; a world event's key, its country and date
 * (backend landslide_inventories: 'south_africa_20220411') -> 'South Africa, 11 Apr 2022'
 */
const eventName = (key) => {
  if (!key) return '—';
  const text = String(key);
  const world = text.match(/^(.+)_(\d{4})(\d{2})(\d{2})$/);
  const month = world ? Number(world[3]) : 0;
  if (!world || month < 1 || month > 12) return capitalise(text);
  const place = world[1].split('_').filter(Boolean)
    .map((w, i) => (i > 0 && SMALL_WORDS.has(w) ? w : capitalise(w))).join(' ');
  return `${place}, ${Number(world[4])} ${SHORT_MONTH[month - 1]} ${world[2]}`;
};
const foldName = (f) => (f === 'world' ? 'World' : eventName(f));

function LandslideSincePublishing({ since }) {
  if (!since) return null;
  return (
    <>
      <h4>Since publishing</h4>
      {since.under_review && <p className="fc-note"><strong>{LANDSLIDE_UNDER_REVIEW}</strong></p>}
      <p className="fc-note">
        {since.n
          ? `${since.in_red_orange} of ${since.n} located ${since.n === 1 ? 'landslide' : 'landslides'} since the `
            + 'levels were published fell in Red or Orange.'
          : 'No located landslide has been recorded since the levels were published.'}
      </p>
      {since.misses?.length > 0 && (
        <p className="fc-note">
          Outside Red and Orange: {since.misses.map((m) => `${m.day} (${m.purok}, ${m.level})`).join(', ')}.
        </p>
      )}
    </>
  );
}

function LandslideTrainingSet({ training, own }) {
  if (!training) return null;
  const world = training.world || {};
  // In own mode the counts include GeoAlert's own located landslides and their "no" points
  const from = own ? "from typhoons in the Philippines, GeoAlert's own landslides and" : 'from typhoons in the Philippines and';
  return (
    <>
      <h4>The training set</h4>
      <p className="fc-note">
        {`${count(training.slides)} landslides and the ground around them that did not slide (${count(training.rows)} `
          + `rows in all) that the chosen training set holds, ${from}, if they joined, events elsewhere in the world.`}
      </p>
      <div className="fc-table-wrap">
        <table className="fc-table fc-table-whole">
          <thead>
            <tr>
              <th scope="col">Event</th><th scope="col">Where</th><th scope="col">Landslides</th>
              <th scope="col">Ground that did not slide</th><th scope="col">Used to train</th>
            </tr>
          </thead>
          <tbody>
            {(training.events || []).map((e) => (
              <tr key={e.event}>
                <td>{eventName(e.event)}</td>
                <td>{EVENT_REGION[e.region] || "GeoAlert's own located landslides"}</td>
                <td>{count(e.slides)}</td>
                <td>{count(e.no_points)}</td>
                <td>{yesNo(e.used)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {world.verdict && <p className="fc-note">{world.verdict}</p>}
      {world.rule && <p className="fc-note">{world.rule}</p>}
    </>
  );
}

/**
 * How many training rows kept the road clue (spec 3.3), and the events whose mapped area had too few
 * roads to keep it (backend landslide_run's report['road_check']); a missing key shows nothing
 */
function LandslideRoadCheck({ check }) {
  const kept = check?.rows != null && check?.rows_with_road != null;
  const without = check?.events_without_road || [];
  if (!kept && !without.length) return null;
  return (
    <p className="fc-note">
      {kept && `${count(check.rows_with_road)} of ${count(check.rows)} training rows kept the road clue.`}
      {kept && without.length > 0 && ' '}
      {without.length > 0
        && "No road clue for the events whose mapped area has under a tenth of Talisay's road density on steep ground: "
          + `${without.map(eventName).join('; ')}.`}
    </p>
  );
}

/**
 * The share of the held-out landslides the cut-offs in use put in Red, and in Red and Orange together,
 * and whether the 90% target was reached (spec 5.2 step 5; flood_rules.Cutoffs); a missing key shows nothing
 */
function LandslideRecall({ cut, own }) {
  if (cut?.red_recall == null || cut?.orange_recall == null) return null;
  // A target not reached is rounded down, so 0.8996 reads 89%, never the 90% it missed (the small
  // epsilon keeps a whole percent whole: 0.57 * 100 is 56.99999999999999)
  const together = cut.target_reached === false
    ? `${Math.floor(cut.orange_recall * 100 + 1e-9)}%` : fmt(cut.orange_recall, 0, true);
  return (
    <p className="fc-note">
      {`At the cut-offs in use, Red holds ${fmt(cut.red_recall, 0, true)} of the held-out landslides, and Red and `
        + `Orange together ${together}.`}
      {cut.target_reached === false
        && ' The 90% target for Red and Orange was not reached: the scores tie at the bottom, so Orange stops at the '
          + 'last distinct score.'}
      {own && " GeoAlert's own landslides count ten times in these shares."}
    </p>
  );
}

function LandslideCandidates({ report }) {
  const candidates = report.candidates || [];
  const rows = candidates.flatMap((c) => (c.folds || []).map((f) => ({ ...f, name: c.name })));
  // In own mode GeoAlert's own landslides are a held-out fold too
  const heldOut = `a Philippine typhoon${report.source === 'geoalert' ? " or GeoAlert's own landslides" : ''}`;
  return (
    <>
      <h4>The candidates and the rule</h4>
      <p className="fc-note">
        {`Each candidate was scored on landslides it never saw, one held-out event at a time: ${heldOut}. AUC 0.5 is `
          + 'chance. The neural network is kept unless a simpler model is clearly better.'}
      </p>
      <div className="fc-table-wrap">
        <table className="fc-table fc-table-whole fc-candidates">
          <thead>
            <tr><th scope="col">Model</th><th scope="col">AUC (95% interval)</th></tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.name}>
                <td>{LANDSLIDE_FAMILY[c.name] || c.name}{c.name === report.choice?.chosen ? ' (chosen)' : ''}</td>
                <td>{scoreText({ value: c.auc, low: c.lo, high: c.hi }, 2, false)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 0 && (
        <div className="fc-table-wrap">
          <table className="fc-table fc-table-whole">
            <caption className="fc-sub">{`AUC on each held-out event (${heldOut})`}</caption>
            <thead>
              <tr>
                <th scope="col">Model</th><th scope="col">Event</th><th scope="col">Landslides</th>
                <th scope="col">AUC (95% interval)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f) => (
                <tr key={`${f.name}-${f.fold}`}>
                  <td>{LANDSLIDE_FAMILY[f.name] || f.name}</td>
                  <td>{foldName(f.fold)}</td>
                  <td>{count(f.slides)}</td>
                  <td>{scoreText({ value: f.auc, low: f.lo, high: f.hi }, 2, false)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {report.choice?.verdict && <p className="fc-note"><strong>{report.choice.verdict}</strong></p>}
      {report.choice?.rule && <p className="fc-note">{report.choice.rule}</p>}
    </>
  );
}

function LandslideAcceptance({ acceptance }) {
  const gates = acceptance?.gates || {};
  const labels = acceptance?.labels || {};
  const details = acceptance?.details || {};
  return (
    <>
      <h4>The four checks</h4>
      <ul className="fc-note">
        {Object.keys(gates).map((g) => (
          <li key={g}>{`${labels[g] || g}: ${gates[g] ? 'passed' : 'failed'}. ${details[g] || ''}`.trim()}</li>
        ))}
      </ul>
      {(acceptance?.reasons || []).map((r) => <p key={r} className="fc-note">{r}</p>)}
    </>
  );
}

function LandslideTest({ report, fallback, own }) {
  const test = report.talisay_test || {};
  const check = test.barangay_check || {};
  const catalogue = test.catalogue || [];
  const held = report.temporal_test?.held_back || [];
  const catalogueCounts = ['Red', 'Orange', 'Green', null].map((lv) => [
    lv, catalogue.filter((c) => ((fallback ? c.published_level : c.level) || null) === lv).length,
  ]).filter(([, n]) => n > 0);
  return (
    <>
      <h4>The Talisay test: landslides it never saw</h4>
      {fallback && (
        <p className="fc-note">
          These checks scored the machine-learning model, which is not in use; the last column gives each purok&apos;s
          level on the map in use.
        </p>
      )}
      {own && held.length > 0 && (
        <div className="fc-table-wrap">
          <table className="fc-table fc-table-whole">
            <caption className="fc-sub">{`The ${report.temporal_test.season} wet season's landslide spots, held back`}</caption>
            <thead><tr><th scope="col">Spot</th><th scope="col">Level of its area</th></tr></thead>
            <tbody>
              {held.map((p, i) => (
                // eslint-disable-next-line react/no-array-index-key -- two spots can share a purok
                <tr key={i}><td>{i + 1}</td><td>{landslideLevelWord(p.level)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!own && test.puroks?.length > 0 && (
        <div className="fc-table-wrap">
          <table className="fc-table fc-table-whole">
            <caption className="fc-sub">Talisay puroks with a located landslide</caption>
            <thead>
              <tr>
                <th scope="col">Barangay</th><th scope="col">Purok</th>
                <th scope="col">{fallback ? 'Machine-learning model (not in use)' : 'Level of its area'}</th>
                {fallback && <th scope="col">Map in use</th>}
              </tr>
            </thead>
            <tbody>
              {test.puroks.map((p, i) => (
                // eslint-disable-next-line react/no-array-index-key -- a purok id can be null
                <tr key={i}>
                  <td>{p.barangay}</td>
                  <td>{p.name}</td>
                  <td>{landslideLevelWord(p.level)}</td>
                  {fallback && <td>{landslideLevelWord(p.published_level)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {catalogueCounts.length > 0 && (
        <p className="fc-note">
          {`Landslides in NASA's Global Landslide Catalog inside Talisay, by the level of their area${fallback ? ' on the map in use' : ''}: ${catalogueCounts
            .map(([lv, n]) => `${landslideLevelWord(lv)} ${n}`).join('; ')}.`}
        </p>
      )}
      {check.barangays?.length > 0 && (
        <>
          <h4>The barangay check{fallback ? ' (the machine-learning model, not in use)' : ''}</h4>
          <div className="fc-table-wrap">
            <table className="fc-table fc-table-whole">
              <thead>
                <tr>
                  <th scope="col">Barangay</th><th scope="col">Located landslides</th>
                  <th scope="col">Scoring points</th><th scope="col">In Red or Orange</th>
                </tr>
              </thead>
              <tbody>
                {check.barangays.map((b) => (
                  <tr key={b.barangay_id}>
                    <td>{b.barangay}</td>
                    <td>{count(b.records)}</td>
                    <td>{count(b.points)}</td>
                    <td>{fmt(b.share_red_orange, 0, true)}</td>
                  </tr>
                ))}
                {check.rest && (
                  <tr>
                    <td>The rest of the city</td>
                    <td>—</td>
                    <td>{count(check.rest.points)}</td>
                    <td>{fmt(check.rest.share_red_orange, 0, true)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function LandslideRange({ range, fallback }) {
  if (!range) return null;
  const clipped = Object.entries(range.clipped || {}).filter(([, n]) => n > 0);
  return (
    <>
      <h4>Ground like the training areas{fallback ? ' (the machine-learning model, not in use)' : ''}</h4>
      <p className="fc-note">
        {`${count(range.in_range)} of ${count(range.points)} scoring points (${fmt(range.share, 0, true)}) sit on `
          + `ground like the training areas; ${count(range.unlike_puroks)} puroks are not assessed because their `
          + 'ground is unlike it.'}
        {clipped.length > 0
          && ` Held to the training range: ${clipped.map(([c, n]) => `${CLIPPED_CLUE[c] || c} (${count(n)})`)
            .join(', ')}.`}
      </p>
    </>
  );
}

/**
 * The landslide susceptibility model's report (train_landslide_model), in
 * order: where the levels come from, the training set and how many of its rows
 * kept the road clue, the candidates and rule 2's verdict, the four checks, the
 * Talisay test, how much of the city is on ground like the training areas, the
 * classes and the recall their cut-offs reach, how it has done since
 * publishing, its limits and the credits.
 */
export function LandslideModelReport({ report }) {
  const fallback = report.source === 'noah';
  const own = report.source === 'geoalert';
  const chosen = LANDSLIDE_FAMILY[report.choice?.chosen] || report.choice?.chosen;
  const levels = report.classes?.levels || {};
  const notAssessed = Object.entries(report.classes?.not_assessed || {});
  const model = chosen ? `the machine-learning model (${chosen})` : 'the machine-learning model';
  const version = report.version ? `, version ${report.version}` : '';
  let inUse = `In use: ${model}${version}.`;
  if (fallback) {
    inUse = `In use: the NOAH fallback${version}. ${model.charAt(0).toUpperCase()}${model.slice(1)} did not pass `
      + "every check, so the levels come from UP NOAH's landslide hazard map, classed by where landslides started "
      + 'after Philippine typhoons.';
  } else if (own) {
    inUse = `In use: ${model} trained on typhoon landslides and GeoAlert's own located landslide records${version}.`;
  }
  return (
    <section className="fc-accuracy">
      <h3>Landslide: susceptibility by purok</h3>
      {report.basis && <p className="fc-sub">{report.basis}</p>}
      <p className="fc-sub">
        {inUse}
        {report.built_at && ` Built ${report.built_at.slice(0, 10)}.`}
      </p>
      {fallback && report.fallback?.note && <p className="fc-note">{report.fallback.note}</p>}
      {own && report.own_spots != null && (
        <p className="fc-note">{`${count(report.own_spots)} of GeoAlert's own located landslide spots are in the training set.`}</p>
      )}

      <LandslideTrainingSet training={report.training_set} own={own} />
      <LandslideRoadCheck check={report.road_check} />
      <LandslideCandidates report={report} />
      <LandslideAcceptance acceptance={report.acceptance} />
      <LandslideTest report={report} fallback={fallback} own={own} />
      <LandslideRange range={report.in_range} fallback={fallback} />

      <h4>The levels</h4>
      <div className="fc-table-wrap">
        <table className="fc-table fc-table-whole">
          <thead>
            <tr><th scope="col">Level</th><th scope="col">Areas</th><th scope="col">Scoring points</th></tr>
          </thead>
          <tbody>
            {['Red', 'Orange', 'Green'].filter((k) => levels[k]).map((k) => (
              <tr key={k}>
                <td>{LANDSLIDE_WORD[k]}</td>
                <td>{count(levels[k].puroks)}</td>
                <td>{count(levels[k].points)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* The cut-offs that ship: the fallback's when UP NOAH's map is in use */}
      <LandslideRecall cut={fallback ? report.fallback?.cutoffs : report.cutoffs} own={own} />
      {notAssessed.length > 0 && (
        <p className="fc-note">
          {`${NOT_ASSESSED}: ${notAssessed.map(([reason, n]) => `${reason} (${n})`).join('; ')}.`}
        </p>
      )}

      <LandslideSincePublishing since={report.since_publishing} />

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

/** One hazard's entry on the card: its reason when unavailable, else the fire, flood or landslide report */
export function ForecastAccuracyEntry({ entry }) {
  if (entry.status === 'unavailable') {
    return (
      <section className="fc-accuracy">
        <h3>{entry.hazard}: unavailable</h3>
        {entry.reason && <p className="fc-sub">{entry.reason}</p>}
      </section>
    );
  }
  // Landslide is picked before the fire fallback, so its report never renders under a Fire heading
  if (entry.kind === 'landslide_purok') return <LandslideModelReport report={entry} />;
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
        How the fire model did on fires it never saw, the flood model on floods it never saw, and the landslide
        model on landslides it never saw. Counting past fires is only a comparison here, never the prediction.
      </p>
      {error && <p className="db-error" role="alert">{error}</p>}
      {!error && !hazards && <p className="db-empty">Loading the accuracy check…</p>}
      {hazards && !hazards.length && <p className="db-empty">No real records to test a model on yet.</p>}
      {hazards?.map((entry) => <ForecastAccuracyEntry key={entry.hazard} entry={entry} />)}
    </div>
  );
}
