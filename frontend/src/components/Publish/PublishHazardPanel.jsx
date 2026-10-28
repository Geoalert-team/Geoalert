import React, { useEffect, useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';
import { MIN_CORNERS, areaSqM, formatArea, pointsToPolygon } from '../../utils/drawnZone';
import { SEVERITY } from '../Map/hazardInfo';
import {
  DEPTH_PRESETS, FLOOD_DEPTH, HAND, PAST, REPORTS,
  defaultMethodFor, methodByKey, methodsFor, runMethod,
} from './shapeMethods';
import { reportsApi } from '../../api/reportApi';
import { loadElevation, loadTerrain, readSpot } from '../../utils/terrain';
import { describeSpot } from '../../utils/spotText';
import { checkZone } from '../../utils/zoneCheck';
import './css/PublishHazard.css';

const SEVERITY_ORDER = ['Green', 'Orange', 'Red'];

// What sizes are usual for each hazard, as a guide while outlining.
// A burned block is small (40 razed houses cover ~0.25 ha); floods spread wide.
const TYPICAL_SIZE = {
  Flood:     'street ponding 100-250 m across, river overflow 500 m to 1.5 km',
  Landslide: 'rockfall 20-50 m across, slope failure with houses below 100-300 m',
  Fire:      'house fire 30-80 m across, block of 50+ houses 80-200 m',
};

function timeOf(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  } catch {
    return '';
  }
}

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

/**
 * The last look before an alert goes out: who it reaches and what it
 * overlaps. Publishing notifies people straight away and can't be taken
 * back, only withdrawn, so a wrong hazard type or a double publish is
 * cheapest to catch here.
 */
function ConfirmStep({ preview, typeName, sev, busy, error, onBack, onSend, onCancel, checkWarnings = [] }) {
  const places = preview.affected_barangays.length
    ? preview.affected_barangays.join(', ')
    : 'Talisay City';
  const held = preview.needs_approval;
  // An active zone of the same type already covers half or more of this
  // drawing: most likely the same event. The server refuses it unless the
  // officer says it is a separate one.
  const major = preview.duplicates.filter((d) => d.major);
  const pct = (d) => `${Math.round((d.overlap || 0) * 100)}%`;

  return (
    <div className="pub db-scope" role="dialog" aria-label="Check before sending">
      <div className="pub-head">
        <h3>Check before sending</h3>
        <button type="button" className="pub-close" onClick={onCancel} aria-label="Cancel">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>

      <dl className="pub-summary">
        <dt>Hazard</dt>
        <dd>
          <span className="pub-sev-dot" style={{ background: sev.color }} /> {typeName}, {sev.label.toLowerCase()}
        </dd>
        {preview.area_m2 != null && (
          <>
            <dt>Area</dt>
            <dd>{formatArea(preview.area_m2)}{' '}<small>(after cutting at the city boundary)</small></dd>
          </>
        )}
        <dt>Barangays</dt>
        <dd>{places}</dd>
        <dt>Shape</dt>
        <dd>The green area on the map is what will be saved.</dd>
        <dt>Notifies</dt>
        <dd><strong>{plural(preview.recipients, 'account')}</strong></dd>
      </dl>

      {preview.duplicates.length > 0 && (
        <div className={`pub-dupes ${major.length ? 'is-major' : ''}`} role="alert">
          {major.length ? (
            <>
              <strong>Probably the same event.</strong> An active {major[0].type.toLowerCase()} zone
              already covers <strong>{pct(major[0])}</strong> of this area:
            </>
          ) : (
            <>
              <strong>Already active nearby.</strong> This overlaps{' '}
              {preview.duplicates.length === 1 ? 'a zone' : `${preview.duplicates.length} zones`} of the same type:
            </>
          )}
          <ul>
            {preview.duplicates.map((d) => (
              <li key={d.id}>
                <strong>{pct(d)}</strong> covered by {d.type.toLowerCase()},{' '}
                {(SEVERITY[d.severity]?.label || d.severity).toLowerCase()}
                {d.barangay ? ` in ${d.barangay}` : ''}
                {d.activated_at ? `, published ${timeOf(d.activated_at)}` : ''}
                {d.published_by ? ` by ${d.published_by}` : ''}
                {d.status === 'Awaiting_Approval' ? ' (waiting for approval)' : ''}
                {d.status === 'Active' && (
                  <>
                    {' '}
                    <a href={`/map?zone=${d.id}`} target="_blank" rel="noreferrer">
                      {d.major ? 'Update that zone instead' : 'Show it'}
                    </a>
                  </>
                )}
              </li>
            ))}
          </ul>
          {major.length
            ? 'Publishing sends the same barangays a second alert. Publish only if this is a separate event.'
            : 'Publishing again sends a second alert for the same hazard. Publish only if this is a separate event.'}
        </div>
      )}

      {checkWarnings.length > 0 && (
        <div className="pub-check" role="note">
          <strong>Map check</strong>
          <ul>{checkWarnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}

      {held && (
        <p className="db-callout" style={{ margin: '0 0 12px' }}>
          Extreme alerts need a second officer. It stays off the public map
          until another officer approves it. If nobody answers within{' '}
          {preview.approval_minutes} minutes, it goes out on its own.
        </p>
      )}

      {error && <p className="db-error" role="alert">{error}</p>}

      <div className="db-btn-row">
        <button
          type="button"
          className="db-btn db-btn-primary"
          disabled={busy}
          onClick={onSend}
          style={busy ? undefined : { background: sev.color, borderColor: sev.color }}
        >
          {busy
            ? 'Sending…'
            : major.length
              ? 'Separate event: publish anyway'
              : held
                ? 'Send for approval'
                : `Send to ${plural(preview.recipients, 'account')}`}
        </button>
        <button type="button" className="db-btn db-btn-outline" onClick={onBack} disabled={busy}>
          Back to edit
        </button>
      </div>
    </div>
  );
}

/**
 * The form DRRMO fills in while outlining a hazard on the map. Sits in a
 * floating card so the outline stays visible while corners are added — a
 * modal would cover the thing being drawn.
 *
 * The zone is drawn as a polygon, not a circle: floods follow low ground and
 * creeks, landslides follow slopes, and a circle around a pin both misses
 * houses just past its edge and alarms dry ones inside it.
 *
 * Props:
 *   points            [lat, lng] corners tapped so far, controlled by the
 *                     parent so the map can draw them
 *   onUndo()          remove the last corner
 *   onClear()         start the outline again
 *   barangay          { id, name } around the middle of the outline, or null.
 *                     Only a preview: the server files the zone under
 *                     whichever barangay holds most of it.
 *   outsideCorners    how many corners fall outside every barangay
 *   boundariesReady   false when the barangay outlines failed to load, in
 *                     which case "outside" can't be told from "unknown"
 *   onCancel()
 *   onPublished(zone)
 *   onPreviewShape(g) the GeoJSON the server will save, for the map to
 *                     show during the check; null when there is none
 *   onReplacePoints(pts)
 *                     replace the whole outline at once. Hand drawing never
 *                     uses this; a generating method (slide path, flood
 *                     fill) hands over its finished corners this way.
 *   onMethodChange(key)
 *                     which shaping method is active, so the map can route
 *                     taps. Hand drawing treats a tap as a corner; a
 *                     generating method treats it as a seed to grow from.
 *   seed              [lat, lng] of the officer's last tap, the starting
 *                     point for a generating method, or null
 *   susceptibilityIndex
 *                     the hazard-index metadata (terrain for the water-depth
 *                     method, layers for the map check), or null
 */
export default function PublishHazardPanel({
  points, onUndo, onClear, barangay, outsideCorners = 0, boundariesReady = true,
  onCancel, onPublished, onPreviewShape,
  onReplacePoints, onMethodChange, seed = null, susceptibilityIndex = null,
}) {
  const [types, setTypes] = useState([]);
  const [hazardTypeId, setHazardTypeId] = useState('');
  const [severity, setSeverity] = useState('Orange');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // The server's answer to "what would publishing this do?", shown for the
  // officer to confirm before anything goes out. Null while still editing.
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    hazardsApi.types()
      .then((list) => {
        setTypes(list || []);
        if (list?.length) setHazardTypeId((prev) => prev || list[0].id);
      })
      .catch(() => setError('Could not load hazard types. Check the backend is running.'));
  }, []);

  const typeName = types.find((t) => String(t.id) === String(hazardTypeId))?.name;

  // What the generating methods read: an observed water depth, the terrain
  // to flood it over, reports pinned on the map, past zones near the tap.
  const [depthM, setDepthM] = useState(0.5);
  const [terrain, setTerrain] = useState(null);
  const [elevation, setElevation] = useState(null);
  const [reports, setReports] = useState([]);
  const [pastZones, setPastZones] = useState(null);
  const [pastPick, setPastPick] = useState(0);
  const [methodNote, setMethodNote] = useState('');
  const methodCtx = {
    hasTerrain: Boolean(susceptibilityIndex?.terrain), terrain, depthM, reports, pastZones, pastPick,
  };

  // Which shaping method is in use. Each hazard type opens on its own best
  // method; hand drawing is always available as the failsafe.
  const [method, setMethod] = useState(HAND);
  const choices = methodsFor(typeName, methodCtx);
  const active = methodByKey(method);

  // Picking a hazard type opens on that type's own best method (water depth
  // for a flood, hand drawing otherwise), so a method meant for another
  // type never stays selected doing nothing.
  useEffect(() => {
    setMethod(defaultMethodFor(typeName, methodCtx));
  }, [typeName]); // eslint-disable-line react-hooks/exhaustive-deps -- methodCtx is read once per type

  // Terrain for the water-depth method, fetched the first time it is used
  useEffect(() => {
    if (method !== FLOOD_DEPTH || terrain) return undefined;
    let cancelled = false;
    loadTerrain(susceptibilityIndex).then((t) => { if (!cancelled) setTerrain(t); });
    return () => { cancelled = true; };
  }, [method, susceptibilityIndex, terrain]);

  // Ground height for the "Where you tapped" reading, fetched alongside it
  useEffect(() => {
    if (method !== FLOOD_DEPTH || elevation) return undefined;
    let cancelled = false;
    loadElevation(susceptibilityIndex).then((e) => { if (!cancelled) setElevation(e); });
    return () => { cancelled = true; };
  }, [method, susceptibilityIndex, elevation]);

  // The same words the public map's "This spot" uses, for the officer's tap
  const seedReading = method === FLOOD_DEPTH && seed ? readSpot(terrain, elevation, seed[0], seed[1]) : null;
  const seedText = seedReading?.inCity ? describeSpot(seedReading) : null;
  const seedLines = seedText ? [seedText.ground && `Ground: ${seedText.ground}`, seedText.waterway].filter(Boolean) : [];

  // Reports of this hazard type pinned on the map in the last three days
  useEffect(() => {
    setReports([]);
    if (!typeName) return undefined;
    let cancelled = false;
    reportsApi.located(typeName, 72)
      .then((list) => {
        if (cancelled) return;
        setReports((Array.isArray(list) ? list : []).filter((r) => r.latitude != null && r.longitude != null));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [typeName]);

  // Past zones of this type near the tapped spot
  useEffect(() => {
    setPastZones(null);
    setPastPick(0);
    if (method !== PAST || !seed || !typeName) return undefined;
    let cancelled = false;
    hazardsApi.pastZones({ type: typeName, lat: seed[0], lng: seed[1], radius: 600 })
      .then((d) => { if (!cancelled) setPastZones(d?.results || []); })
      .catch(() => { if (!cancelled) setPastZones([]); });
    return () => { cancelled = true; };
  }, [method, seed, typeName]);

  // Run a generating method whenever something it reads changes. It hands
  // back corners only; they land on the map like hand-tapped ones.
  useEffect(() => {
    if (!active.generate || (active.seed && !seed)) {
      setMethodNote('');
      return;
    }
    const { corners, note } = runMethod(active, seed ? [seed] : [], methodCtx);
    setMethodNote(note || '');
    if (corners && corners.length >= MIN_CORNERS) onReplacePoints?.(corners);
  }, [method, seed, depthM, terrain, reports, pastZones, pastPick]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    onMethodChange?.(method);
  }, [method]); // eslint-disable-line react-hooks/exhaustive-deps

  // Switching method throws away a part-drawn outline, so ask first.
  function pickMethod(key) {
    if (key === method) return;
    if (points.length && !window.confirm('Start the outline again with this method?')) return;
    if (points.length) onClear();
    setMethodNote('');
    setMethod(key);
  }

  const typical = TYPICAL_SIZE[typeName];
  const corners = points.length;
  const closed = corners >= MIN_CORNERS;
  const area = areaSqM(points);

  // Corners outside the city are fine: the server cuts the zone off at the
  // city boundary, so the officer can trace along it loosely. A zone that
  // misses the city completely is refused.
  //
  // Only warn when the outlines actually loaded. If they failed, every
  // corner looks "outside", and saying so would be noise.
  const spills = boundariesReady && outsideCorners > 0;
  const allOutside = boundariesReady && closed && outsideCorners === corners && !barangay;
  const blocked = busy || !hazardTypeId || !closed || allOutside;

  // A second look at the outline against the susceptibility map: drawn on
  // safe ground, or stopping short of risky ground. Advice only.
  const [checkWarnings, setCheckWarnings] = useState([]);
  useEffect(() => {
    setCheckWarnings([]);
    if (!closed || !typeName || !susceptibilityIndex) return undefined;
    let cancelled = false;
    const timer = setTimeout(() => {
      checkZone(points, typeName, susceptibilityIndex)
        .then((r) => { if (!cancelled) setCheckWarnings(r?.warnings || []); })
        .catch(() => {});
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [points, typeName, susceptibilityIndex, closed]);

  function payload() {
    return {
      hazard_type: hazardTypeId,
      barangay: barangay?.id ?? null,
      severity,
      description: description.trim(),
      geometry: pointsToPolygon(points),
    };
  }

  // Step one: ask the server what publishing would do, and show it.
  async function submit(e) {
    e.preventDefault();
    if (!hazardTypeId) {
      setError('Pick a hazard type first.');
      return;
    }
    // The button is disabled in this case, but pressing Enter in a field can
    // still reach here on some browsers.
    if (!closed) {
      setError(`Tap at least ${MIN_CORNERS} corners on the map to outline the area.`);
      return;
    }

    setBusy(true);
    setError('');
    try {
      setPreview(await hazardsApi.preview(payload()));
    } catch (err) {
      setError(err?.message || 'Could not check this hazard zone.');
    } finally {
      setBusy(false);
    }
  }

  // Step two: the officer has seen who it reaches. Send it.
  async function send() {
    setBusy(true);
    setError('');
    try {
      // The officer saw the overlap in the check and chose to publish
      const zone = await hazardsApi.create({
        ...payload(),
        ...(preview?.major_duplicate ? { confirm_duplicate: true } : {}),
      });
      onPublished?.(zone);
    } catch (err) {
      setError(err?.message || 'Could not publish this hazard zone.');
      setBusy(false);
    }
  }

  // Show the map what will really be saved, cut at the city boundary
  useEffect(() => {
    if (!preview?.geometry) {
      onPreviewShape?.(null);
      return;
    }
    onPreviewShape?.({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', properties: { part: 'hazard' }, geometry: preview.geometry }],
    });
  }, [preview]); // eslint-disable-line react-hooks/exhaustive-deps

  // Anything changed after the check makes the summary stale
  useEffect(() => {
    setPreview(null);
  }, [points, hazardTypeId, severity, description]);

  const sev = SEVERITY[severity];

  if (preview) {
    return (
      <ConfirmStep
        preview={preview}
        typeName={typeName || 'Hazard'}
        sev={sev}
        busy={busy}
        error={error}
        onBack={() => { setPreview(null); setError(''); }}
        onSend={send}
        onCancel={onCancel}
        checkWarnings={checkWarnings}
      />
    );
  }

  return (
    <div className="pub db-scope" role="dialog" aria-label="Publish a hazard zone">
      <form onSubmit={submit}>
        <div className="pub-head">
          <h3>Publish hazard zone</h3>
          <button type="button" className="pub-close" onClick={onCancel} aria-label="Cancel">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>

        <div className="pub-draw">
          <p className="pub-draw-status" aria-live="polite">
            {closed
              ? <><strong>{formatArea(area)}</strong> outlined with {corners} corners</>
              : <>Tap the map to add corners: <strong>{corners} of {MIN_CORNERS}</strong></>}
          </p>
          {/* Only worth showing once a hazard type has a choice to make. With
              hand drawing alone there is nothing to pick. */}
          {choices.length > 1 && (
            <div className="pub-methods" role="group" aria-label="How to shape the zone">
              {choices.map((m) => (
                <button
                  key={m.key}
                  type="button"
                  className={`pub-method ${method === m.key ? 'is-active' : ''}`}
                  aria-pressed={method === m.key}
                  onClick={() => pickMethod(m.key)}
                  disabled={busy}
                >
                  {m.label}
                </button>
              ))}
            </div>
          )}
          <p className="pub-draw-help">{active.help}</p>

          {method === FLOOD_DEPTH && (
            <div className="pub-depth" role="group" aria-label="How deep was the water">
              <span className="pub-depth-label">Water depth where you tapped</span>
              <div className="pub-depth-row">
                {DEPTH_PRESETS.map((d) => (
                  <button
                    key={d.label}
                    type="button"
                    className={`pub-method ${Math.abs(depthM - d.value) < 0.001 ? 'is-active' : ''}`}
                    aria-pressed={Math.abs(depthM - d.value) < 0.001}
                    onClick={() => setDepthM(d.value)}
                    disabled={busy}
                  >
                    {d.label}
                  </button>
                ))}
                <label className="pub-depth-custom">
                  <input
                    type="number"
                    min={0.05}
                    max={5}
                    step={0.05}
                    value={depthM}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      if (v > 0 && v <= 5) setDepthM(v);
                    }}
                    disabled={busy}
                  />
                  m
                </label>
              </div>
              {seedLines.length > 0 && (
                <p className="pub-spot">
                  <strong>Where you tapped</strong>
                  {seedLines.map((line) => <span key={line}>{line}</span>)}
                </p>
              )}
              <small className="pub-size-hint">
                Estimated from Copernicus elevation data (about 30 m detail). Heights can be off by about 1 m,
                more among buildings. Check the edge against what you see.
              </small>
            </div>
          )}

          {method === REPORTS && (
            <small className="pub-size-hint">
              {reports.length} pinned report{reports.length === 1 ? '' : 's'} of this type in the last three days.
            </small>
          )}

          {method === PAST && pastZones && pastZones.length > 1 && (
            <div className="pub-past" role="radiogroup" aria-label="Past zones near this spot">
              {pastZones.map((z, i) => (
                <label key={z.id} className="pub-past-row">
                  <input
                    type="radio"
                    name="pub-past"
                    checked={pastPick === i}
                    onChange={() => setPastPick(i)}
                    disabled={busy}
                  />
                  <span>
                    {new Date(z.activated_at).toLocaleDateString([], { year: 'numeric', month: 'short' })}
                    {', '}{(SEVERITY[z.severity]?.label || z.severity).toLowerCase()}
                    {z.barangay ? `, ${z.barangay}` : ''}
                    {`, ${z.distance_m} m away`}
                    {z.is_sample ? ' (sample)' : ''}
                  </span>
                </label>
              ))}
            </div>
          )}

          {methodNote && <p className="pub-draw-note" role="status">{methodNote}</p>}

          {checkWarnings.length > 0 && (
            <div className="pub-check" role="note">
              <strong>Map check</strong>
              <ul>{checkWarnings.map((w) => <li key={w}>{w}</li>)}</ul>
            </div>
          )}
          <div className="pub-draw-tools">
            <button type="button" className="pub-tool" onClick={onUndo} disabled={!corners || busy}>
              Undo corner
            </button>
            <button type="button" className="pub-tool" onClick={onClear} disabled={!corners || busy}>
              Start over
            </button>
          </div>
          {typical && <small className="pub-size-hint">Typical size: {typical}.</small>}
        </div>

        <p className="pub-where">
          {barangay && <>Mostly in <strong>{barangay.name}</strong>. </>}
          {allOutside && (
            <span className="pub-warn">
              The outline is outside Talisay City. Draw it over the affected barangays.
            </span>
          )}
          {spills && !allOutside && (
            <span className="pub-note">Parts outside Talisay City will be cut off.</span>
          )}
          {!boundariesReady && (
            <span className="pub-warn">
              Barangay outlines didn't load, so the barangay can't be checked.
            </span>
          )}
        </p>

        <label className="db-field" htmlFor="pub-type">
          Hazard type
          <select
            id="pub-type"
            value={hazardTypeId}
            onChange={(e) => setHazardTypeId(e.target.value)}
            required
          >
            {types.length === 0 && <option value="">Loading…</option>}
            {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>

        <fieldset className="pub-sev">
          <legend>Severity</legend>
          <div className="pub-sev-row">
            {SEVERITY_ORDER.map((code) => (
              <button
                key={code}
                type="button"
                className={`pub-sev-btn ${severity === code ? 'is-active' : ''}`}
                style={severity === code
                  ? { background: SEVERITY[code].tint, borderColor: SEVERITY[code].color, color: SEVERITY[code].text }
                  : undefined}
                aria-pressed={severity === code}
                onClick={() => setSeverity(code)}
              >
                <span className="pub-sev-dot" style={{ background: SEVERITY[code].color }} />
                {SEVERITY[code].label}
              </button>
            ))}
          </div>
        </fieldset>

        <label className="db-field" htmlFor="pub-desc">
          What is happening here?
          <textarea
            id="pub-desc"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Water rising along the creek, roads near the market impassable"
          />
        </label>

        {/* Extreme alerts are held for a second officer when there is one to
            ask, so promising the map "straight away" would be wrong here.
            Whether a hold actually applies depends on who else is on duty,
            which only the server knows — the check step says for certain. */}
        <p className="db-callout" style={{ margin: '4px 0 12px' }}>
          {severity === 'Red'
            ? 'Extreme alerts usually wait for a second officer before going '
              + 'out. The next step says for certain, and who it reaches.'
            : 'Publishing puts this on the public map straight away and '
              + 'notifies every other account.'}
        </p>

        {error && <p className="db-error" role="alert">{error}</p>}

        <div className="db-btn-row">
          <button
            className="db-btn db-btn-primary"
            disabled={blocked}
            title={!closed ? `Outline the area with at least ${MIN_CORNERS} corners first` : undefined}
            style={blocked ? undefined : { background: sev.color, borderColor: sev.color }}
          >
            {busy ? 'Publishing…' : `Publish ${sev.label.toLowerCase()}`}
          </button>
          <button type="button" className="db-btn db-btn-outline" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
