import React, { useEffect, useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';
import { MIN_CORNERS, areaSqM, formatArea, pointsToPolygon } from '../../utils/drawnZone';
import { SEVERITY } from '../Map/hazardInfo';
import './css/PublishHazard.css';

const SEVERITY_ORDER = ['Green', 'Orange', 'Red'];

// What sizes are usual for each hazard, as a guide while outlining.
// A burned block is small (40 razed houses cover ~0.25 ha); floods spread wide.
const TYPICAL_SIZE = {
  Flood:     'street ponding 100-250 m across, river overflow 500 m to 1.5 km',
  Landslide: 'rockfall 20-50 m across, slope failure with houses below 100-300 m',
  Fire:      'house fire 30-80 m across, block of 50+ houses 80-200 m',
};

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
 */
export default function PublishHazardPanel({
  points, onUndo, onClear, barangay, outsideCorners = 0, boundariesReady = true,
  onCancel, onPublished,
}) {
  const [types, setTypes] = useState([]);
  const [hazardTypeId, setHazardTypeId] = useState('');
  const [severity, setSeverity] = useState('Orange');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    hazardsApi.types()
      .then((list) => {
        setTypes(list || []);
        if (list?.length) setHazardTypeId((prev) => prev || list[0].id);
      })
      .catch(() => setError('Could not load hazard types. Check the backend is running.'));
  }, []);

  const typeName = types.find((t) => String(t.id) === String(hazardTypeId))?.name;
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
      const zone = await hazardsApi.create({
        hazard_type: hazardTypeId,
        barangay: barangay?.id ?? null,
        severity,
        description: description.trim(),
        geometry: pointsToPolygon(points),
      });
      onPublished?.(zone);
    } catch (err) {
      setError(err?.message || 'Could not publish this hazard zone.');
    } finally {
      setBusy(false);
    }
  }

  const sev = SEVERITY[severity];

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
          <p className="pub-draw-help">
            Follow the edge of the affected area. Drag a corner to move it.
          </p>
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

        <p className="db-callout" style={{ margin: '4px 0 12px' }}>
          Publishing puts this on the public map straight away and notifies
          every other account.
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
