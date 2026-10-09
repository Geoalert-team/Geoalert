import React, { useEffect, useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';
import { circleToPolygon } from '../../utils/circlePolygon';
import { SEVERITY } from '../Map/hazardInfo';
import './css/PublishHazard.css';

const SEVERITY_ORDER = ['Green', 'Orange', 'Red'];

/**
 * The form DRRMO fills in after tapping a point on the map. Sits in a
 * floating card so the draft circle stays visible while the radius is
 * adjusted — a modal would cover the thing being adjusted.
 *
 * Props:
 *   center        [lat, lng] of the tapped point
 *   radius        metres, controlled by the parent so the map can draw it
 *   onRadius(n)   radius changed
 *   barangay      { id, name } detected from the point, or null
 *   onCancel()
 *   onPublished(zone)
 */
export default function PublishHazardPanel({
  center, radius, onRadius, barangay, onCancel, onPublished,
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

  async function submit(e) {
    e.preventDefault();
    if (!hazardTypeId) {
      setError('Pick a hazard type first.');
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
        geometry: circleToPolygon(center, radius),
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

        <p className="pub-where">
          {barangay
            ? <>Inside <strong>{barangay.name}</strong></>
            : <span className="pub-warn">The point isn't inside any barangay boundary</span>}
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

        <label className="db-field" htmlFor="pub-radius">
          Affected radius — {radius} m
          <input
            id="pub-radius"
            type="range"
            min="50"
            max="1000"
            step="25"
            value={radius}
            onChange={(e) => onRadius(Number(e.target.value))}
          />
        </label>

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
            disabled={busy || !hazardTypeId}
            style={!busy && hazardTypeId ? { background: sev.color, borderColor: sev.color } : undefined}
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