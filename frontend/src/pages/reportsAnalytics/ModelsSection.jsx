import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import FloodReadiness from '../../components/Forecast/FloodReadiness';
import ModelUpdates from '../../components/Forecast/ModelUpdates';
import ForecastAccuracy from '../../components/Forecast/ForecastAccuracy';
import SectionFrame from './SectionFrame';

/**
 * Prediction models: which model each hazard uses now, why flood and
 * landslide start from outside data, how a model is trained, when GeoAlert
 * switches to its own, and where retraining runs and goes live
 * (docs/design/specs/2026-11-24-automatic-retraining-design.md). The text is
 * fixed; only the "Model in use" lines and the flood spot count are read
 * live, so they stay true after an automatic switch. Below the text come the
 * data cards (docs/design/specs/2026-11-24-reports-and-trends-separation-design.md,
 * section 3): flood data readiness, model updates and model accuracy. Each
 * card loads on its own, so one failing never hides another. The period
 * filters do not apply here.
 */

// backend fire_training's candidate families
const FIRE_FAMILY = {
  logistic_regression: 'Logistic regression',
  random_forest: 'Random forest',
  adaboost: 'AdaBoost',
  xgboost: 'XGBoost',
  neural_network: 'Neural network',
};

// backend flood_purok.SOURCES: what the flood map in use learned from
const FLOOD_SOURCE = {
  noah: "UP NOAH's 25-year flood map, with its Red, Orange and Green cut-offs learned from where floods reached in "
    + 'the 2017 UP Mananga flood survey.',
  model: 'A machine-learning model trained on the 2017 UP Mananga flood survey.',
  geoalert: "A machine-learning model trained on GeoAlert's own located flood records.",
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** '2023-01' -> 'Jan 2023' */
export const monthWords = (ym) => {
  const [y, m] = String(ym || '').split('-').map(Number);
  return y && m >= 1 && m <= 12 ? `${MONTHS[m - 1]} ${y}` : '';
};

/** Fire's "Model in use" line from its accuracy entry */
export function fireInUse(entry) {
  if (!entry) return 'Not available right now.';
  if (entry.status !== 'in_use') return entry.reason || 'Not available right now.';
  const family = FIRE_FAMILY[entry.model?.family] || entry.model?.family || 'A trained model';
  const t = entry.trained || {};
  const span = t.start && t.end ? ` from ${monthWords(t.start)} to ${monthWords(t.end)}` : '';
  return t.fires != null ? `${family}, trained on ${t.fires} fires${span}.` : `${family}.`;
}

/** Flood's "Model in use" line from the readiness answer's flood_map */
export function floodInUse(map) {
  if (!map) return 'Not available right now.';
  if (!map.available) return map.reason || 'Not available right now.';
  return FLOOD_SOURCE[map.source] || 'A trained flood susceptibility map.';
}

/** Landslide's "Model in use" line from its accuracy entry */
export function landslideInUse(entry) {
  if (!entry) return 'Not available right now.';
  if (entry.status !== 'in_use') return entry.reason || 'Not available right now.';
  // The entry's own basis line (backend landslide_purok.basis) says what the map in use learned from
  return entry.basis || 'A trained landslide susceptibility map.';
}

/** Where GeoAlert's own located landslide spots stand against the floor to try an own-data model */
export function landslideSpotsLine(own, source) {
  if (source === 'geoalert') return "In use now: the landslide map learns from GeoAlert's own located landslide records.";
  if (!own) return '';
  const counted = `${own.n} of ${own.needed} located landslide spots, in ${own.barangays} of ${own.barangays_needed} barangays`;
  return own.enough
    ? `Today: ${counted}. That is enough, so the next January run trains on GeoAlert's own records.`
    : `Today: ${counted}. Until both are reached, the landslide map keeps learning from outside data.`;
}

/** Where GeoAlert's own located flood spots stand against the floor to try an own-data model */
export function spotsLine(own, source) {
  if (source === 'geoalert') return "In use now: the flood map learns from GeoAlert's own located flood records.";
  if (!own) return '';
  const counted = `${own.n} of ${own.needed} located flood spots, in ${own.barangays} of ${own.barangays_needed} barangays`;
  return own.enough
    ? `Today: ${counted}. That is enough, so the next January run trains on GeoAlert's own records.`
    : `Today: ${counted}. Until both are reached, the flood map keeps learning from outside data.`;
}

/** One API answer: undefined while loading, null when it failed */
function useAnswer(load) {
  const [answer, setAnswer] = useState(undefined);
  useEffect(() => {
    let cancelled = false;
    load().then((d) => { if (!cancelled) setAnswer(d || null); }).catch(() => { if (!cancelled) setAnswer(null); });
    return () => { cancelled = true; };
  }, [load]);
  return answer;
}

const live = (answer, line) => (answer === undefined ? 'Checking…' : line);

export default function ModelsSection() {
  const accuracy = useAnswer(historyApi.forecastAccuracy);
  const readiness = useAnswer(historyApi.forecastReadiness);
  const fire = accuracy?.hazards?.find((h) => h.hazard === 'Fire');
  const landslide = accuracy?.hazards?.find((h) => h.hazard === 'Landslide');
  const landslideOwn = landslide?.status === 'in_use' && landslide.source === 'geoalert';
  const floodMap = readiness?.flood_map;
  const floodOwn = floodMap?.available && floodMap.source === 'geoalert';
  const spots = readiness === undefined ? 'Counting GeoAlert’s located flood spots…' : spotsLine(readiness?.own_spots, floodMap?.source);
  const landslideSpots = readiness === undefined
    ? 'Counting GeoAlert’s located landslide spots…'
    : landslideSpotsLine(readiness?.landslide_spots, landslide?.source);

  return (
    <SectionFrame report="models" title="Prediction models" file="models" csv={null}
      note="How GeoAlert predicts hazards, how its models are trained, and how a better model takes over. The filters above do not apply here.">

      <section className="ra-block" aria-labelledby="ra-pm-use-h">
        <h3 id="ra-pm-use-h">The models in use</h3>
        <p className="ra-block-sub">
          Each model gives every purok a Red, Orange or Green level. No person sets or changes a predicted level;
          only a trained model does.
        </p>
        <div className="ra-pm-models">
          <article className="ra-pm-card">
            <h4>Fire</h4>
            <span className="ra-pm-tag is-own">Learns from GeoAlert&rsquo;s own records</span>
            <dl>
              <dt>Predicts</dt>
              <dd>The chance of a fire in each purok, month by month.</dd>
              <dt>Model in use</dt>
              <dd className="ra-pm-live">{live(accuracy, fireInUse(fire))}</dd>
              <dt>Learns from</dt>
              <dd>
                BFP&rsquo;s fire log in GeoAlert. Each purok is described from open map data: buildings, roads, distance
                to a fire station, land cover and population. Adapted from the City of Pittsburgh Bureau of Fire /
                Carnegie Mellon Metro21 fire risk model (MIT License).
              </dd>
              <dt>Retrained</dt>
              <dd>Every month, on the 2nd.</dd>
            </dl>
          </article>
          <article className="ra-pm-card">
            <h4>Flood</h4>
            <span className={`ra-pm-tag ${floodOwn ? 'is-own' : 'is-outside'}`}>
              {floodOwn ? 'Learns from GeoAlert’s own records' : 'Learns from outside data for now'}
            </span>
            <dl>
              <dt>Predicts</dt>
              <dd>How flood-prone each purok is. It is the same in every month and never says a flood is coming.</dd>
              <dt>Model in use</dt>
              <dd className="ra-pm-live">{live(readiness, floodInUse(floodMap))}</dd>
              <dt>Learns from</dt>
              <dd>
                {floodOwn
                  ? "GeoAlert's own located flood records, with ground height, distance to a river and UP NOAH's map as clues."
                  : "Outside flood data (below) until GeoAlert has enough located flood records of its own."}
              </dd>
              <dt>Retrained</dt>
              <dd>Every year, on 5 January, after the wet season.</dd>
            </dl>
          </article>
          <article className="ra-pm-card">
            <h4>Landslide</h4>
            <span className={`ra-pm-tag ${landslideOwn ? 'is-own' : 'is-outside'}`}>
              {landslideOwn ? 'Learns from GeoAlert’s own records' : 'Learns from outside data for now'}
            </span>
            <dl>
              <dt>Predicts</dt>
              <dd>How prone each purok is to sliding. It is the same in every month and never says a landslide is coming.</dd>
              <dt>Model in use</dt>
              <dd className="ra-pm-live">{live(accuracy, landslideInUse(landslide))}</dd>
              <dt>Learns from</dt>
              <dd>
                {landslideOwn
                  ? "Typhoon landslides across the Philippines and GeoAlert's own located landslide records, with terrain, land cover and roads as clues."
                  : "Philippine typhoon landslide inventories (below), until GeoAlert has enough located landslide records of its own. UP NOAH's landslide map is the benchmark the model must beat, and the map in use if it does not."}
              </dd>
              <dt>Retrained</dt>
              <dd>Every year, on 6 January, to try GeoAlert&rsquo;s own records once there are enough.</dd>
            </dl>
          </article>
        </div>
      </section>

      <section className="ra-block ra-pm-text" aria-labelledby="ra-pm-why-h">
        <h3 id="ra-pm-why-h">Why flood and landslide start from outside data</h3>
        <p>
          A model learns where a hazard strikes from many recorded events, each with an exact location, spread across
          the city. It also needs some events held back, never seen in training, to test it honestly. A model trained
          on too few events memorises those few places and is wrong everywhere else.
        </p>
        <ul>
          <li>
            <strong>Fire has enough.</strong> BFP&rsquo;s fire log gives GeoAlert enough located fires to train and
            test on its own records, so fire uses GeoAlert&rsquo;s data from the start.
          </li>
          <li>
            <strong>Flood does not yet.</strong> GeoAlert&rsquo;s own located flood records are still far fewer than a
            model needs (today&rsquo;s count is under &ldquo;When a new model takes over&rdquo;).
          </li>
          <li>
            <strong>Landslide does not yet either.</strong> Only a handful of landslides are on record, nearly all in
            Manipis. A model trained on them would learn &ldquo;Manipis&rdquo;, not what makes a slope fail.
          </li>
        </ul>
        <p>So flood learns from outside sources that already map where floods reach in Talisay:</p>
        <ul>
          <li>
            <strong>UP NOAH&rsquo;s 25-year flood hazard map</strong>, a physics-based flood model of the Philippines.
          </li>
          <li>
            <strong>The 2017 UP Mananga flood survey</strong> (Phil-LiDAR 1, UP and the University of San Carlos): over a
            hundred located flood depths from six typhoons between 1990 and 2014. Its points stay private; only the
            fitted results reach GeoAlert.
          </li>
          <li>
            <strong>Public land data</strong>: ground height (Copernicus elevation model), distance to rivers
            (OpenStreetMap) and buildings (Microsoft building footprints).
          </li>
        </ul>
        <p>Landslide starts from outside data too, from where landslides began in other typhoons:</p>
        <ul>
          <li>
            <strong>Philippine typhoon landslide inventories</strong>: NASA&rsquo;s landslide inventories mapped from
            satellite images after recent typhoons (Vershel et al. 2025) and the landslides mapped from satellite images
            after Typhoon Mangkhut in Itogon. Only the fitted results reach GeoAlert.
          </li>
          <li>
            <strong>UP NOAH&rsquo;s landslide hazard maps</strong>, the benchmark: the model must beat them, and they
            are used instead if it does not.
          </li>
          <li>
            <strong>Public land data</strong>: terrain (Copernicus elevation model), land cover (Esri / Impact
            Observatory), roads (OpenStreetMap) and buildings (Microsoft building footprints).
          </li>
        </ul>
      </section>

      <section className="ra-block ra-pm-text" aria-labelledby="ra-pm-train-h">
        <h3 id="ra-pm-train-h">How a model is trained</h3>
        <ol className="ra-pm-steps">
          <li>
            <strong>Gather the records.</strong> The job collects every recorded event of the hazard from GeoAlert. No
            location is ever written to a log or a report.
          </li>
          <li>
            <strong>Try several models.</strong> Fire tries logistic regression, random forest, AdaBoost, XGBoost and a
            small neural network. Flood tries logistic regression, a MaxEnt-type model, XGBoost and a neural network.
            For fire and flood, a rule fixed in advance picks the simplest one, unless a more complex one is clearly
            better. Landslide tries logistic regression, XGBoost and a neural network, and keeps the neural network
            unless a simpler one is clearly better.
          </li>
          <li>
            <strong>Test it on data it never saw.</strong> Fire is tested on the newest 12 full months, which it is not
            trained on. Flood is tested on the newest wet season, June to December. Landslide is tested on one Philippine typhoon at a
            time, held out, and then on the Talisay puroks with a located landslide.
          </li>
          <li>
            <strong>Set the levels.</strong> A fixed rule sets the Red, Orange and Green cut-offs from the results.
          </li>
        </ol>
        <p>
          <strong>When:</strong> fire retrains on the 2nd of every month, on all fires recorded so far. Flood retrains
          once a year, on 5 January, after the wet season. Landslide retrains every January, on the 6th, only to try
          GeoAlert&rsquo;s own landslide records. All start at 3:17 a.m. Manila time.
        </p>
      </section>

      <section className="ra-block ra-pm-text" aria-labelledby="ra-pm-switch-h">
        <h3 id="ra-pm-switch-h">When a new model takes over</h3>
        <p>
          A new model never goes live just because it is newer. It must do at least as well as the one in use, on data
          neither has seen. If it does not, or if a run fails, the model in use stays and the site keeps working.
        </p>
        <h4>Fire, every month</h4>
        <p>
          The new fit and the model in use are scored on the same held-back 12 months. The new fit goes live if it
          scores at least as well, and better than giving every purok the same chance.
        </p>
        <h4>Flood, every January: switching to GeoAlert&rsquo;s own model</h4>
        <ol className="ra-pm-steps">
          <li>
            <strong>Count our own flood spots:</strong> flood records with a map point, and &ldquo;Affected here&rdquo;
            marks on flood zones.
          </li>
          <li>
            <strong>Not enough yet?</strong> Below 100 spots in at least 5 barangays, nothing is trained and the
            outside-data map stays as it is. Retraining on the same survey would give the same answer.
          </li>
          <li>
            <strong>Enough?</strong> A model is trained on GeoAlert&rsquo;s own spots. The land clues stay (ground
            height, distance to a river and UP NOAH&rsquo;s map), but the floods it learns from are now ours.
          </li>
          <li>
            <strong>It must pass four checks:</strong> better than UP NOAH&rsquo;s map on its own; at least three quarters
            of the newest wet season&rsquo;s spots in Red or Orange; Red and Orange covering at most half the
            buildings; and the test spots kept hidden until the model and its cut-offs are fixed.
          </li>
          <li>
            <strong>It passes:</strong> it replaces the outside-data map, and the site names GeoAlert&rsquo;s records as
            the source. Each January after that, a new fit must also catch at least as many of the newest
            season&rsquo;s spots as the one in use.
          </li>
        </ol>
        {spots && <p className="ra-pm-progress" role="status">{spots}</p>}
        <h4>Landslide, every January: switching to GeoAlert&rsquo;s own records</h4>
        <ol className="ra-pm-steps">
          <li>
            <strong>Count our own landslide spots:</strong> landslide records with a map point, and &ldquo;Affected
            here&rdquo; marks on landslide zones.
          </li>
          <li>
            <strong>Not enough yet?</strong> Below 30 spots in at least 3 barangays, nothing is trained and the
            outside-data map stays as it is.
          </li>
          <li>
            <strong>Enough?</strong> A model is trained on the outside typhoon landslides together with GeoAlert&rsquo;s
            own spots, which count ten times as much. At least 5 spots from the newest wet season (1 June to 31
            December) are held back to test it.
          </li>
          <li>
            <strong>It must pass four checks:</strong> better than UP NOAH&rsquo;s map on its own; at least three quarters
            (rounded up) of the held-back spots in Red or Orange; Red and Orange covering at most half of
            Talisay&rsquo;s assessed scoring points; and the test spots kept hidden until the model and its cut-offs are
            fixed.
          </li>
          <li>
            <strong>It passes:</strong> it replaces the outside-data map only if it also catches at least as many of the
            held-back spots as the map in use.
          </li>
        </ol>
        {landslideSpots && <p className="ra-pm-progress" role="status">{landslideSpots}</p>}
        <p>Flood and landslide maps change only between January and May, never in the middle of a wet season.</p>
      </section>

      <section className="ra-block ra-pm-text" aria-labelledby="ra-pm-where-h">
        <h3 id="ra-pm-where-h">Where retraining runs and how it goes live</h3>
        <ol className="ra-pm-flow">
          <li><strong>Starts on schedule</strong> GitHub Actions runs the &ldquo;Model retraining&rdquo; job.</li>
          <li><strong>Fetches records</strong> It asks GeoAlert for the training records with a secret token.</li>
          <li><strong>Trains and tests</strong> On its own temporary machine and database.</li>
          <li><strong>Sends the result</strong> The new model and its test results go back to GeoAlert.</li>
          <li><strong>Goes live on a pass</strong> GeoAlert checks it, saves the attempt and switches only if it passed.</li>
        </ol>
        <p>
          <strong>Where:</strong> retraining runs on GitHub Actions, free, on a throw-away machine with its own
          temporary database. It never runs on the live server, which is too small to train on, and it never touches
          GeoAlert&rsquo;s database: GitHub holds only a token that can fetch training records and send a result back,
          never the database password.
        </p>
        <p>
          <strong>Deployment is automatic.</strong> GeoAlert saves every attempt with its result (Switched, Kept current,
          Not tried, Skipped or Failed) and the reason. A model that passes is used across the site within about a
          minute, with no code change and no redeploy. A system administrator can switch back to an earlier model in
          Django&rsquo;s admin site, which is turned on only when needed, and the job can also be started by hand from
          GitHub.
        </p>
      </section>

      <div className="db-card">
        <FloodReadiness />
      </div>
      <div className="db-card">
        <ModelUpdates />
      </div>
      <div className="db-card">
        <ForecastAccuracy />
      </div>
    </SectionFrame>
  );
}
