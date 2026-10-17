import React, { useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';
import { MIN_CORNERS, areaSqM, formatArea, pointsToPolygon } from '../../utils/drawnZone';
import './css/PublishHazard.css';

/**
 * Redraw the outline of a live hazard zone, instead of withdrawing it and
 * publishing a new one. Same floating card as publishing, so the outline
 * stays visible while it is changed.
 *
 * Props:
 *   zone        the map item being reshaped ({ id, type, location })
 *   points      [lat, lng] corners, controlled by the parent so the map can draw them
 *   canUndo     whether there is an earlier version of the outline to go back to
 *   onUndo()    go back one change
 *   onReset()   back to the zone's current outline
 *   onCancel()
 *   onSaved(zone)
 */
export default function ReshapeZonePanel({ zone, points, canUndo, onUndo, onReset, onCancel, onSaved }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);
  const closed = points.length >= MIN_CORNERS;

  async function save() {
    setBusy(true);
    setError('');
    try {
      const updated = await hazardsApi.reshape(zone.id, pointsToPolygon(points));
      onSaved?.(updated);
    } catch (err) {
      setError(err?.message || 'Could not save the new area.');
      setConfirming(false);
      setBusy(false);
    }
  }

  return (
    <div className="pub db-scope" role="dialog" aria-label="Edit hazard area">
      <div className="pub-head">
        <h3>Edit hazard area</h3>
        <button type="button" className="pub-close" onClick={onCancel} aria-label="Cancel">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
      <p className="pub-where">{zone.type} · {zone.location}</p>

      <div className="pub-draw">
        <p className="pub-draw-status" aria-live="polite">
          <strong>{formatArea(areaSqM(points))}</strong> with {points.length} corners
        </p>
        <p className="pub-draw-help">
          Drag a corner to move it. Tap the map to add a corner on the nearest
          edge. Right-click a corner to remove it.
        </p>
        <div className="pub-draw-tools">
          <button type="button" className="pub-tool" onClick={onUndo} disabled={!canUndo || busy}>
            Undo
          </button>
          <button type="button" className="pub-tool" onClick={onReset} disabled={!canUndo || busy}>
            Back to current area
          </button>
        </div>
      </div>

      <p className="db-callout" style={{ margin: '4px 0 12px' }}>
        Saving asks every barangay to confirm the hazard again, since the area
        changed. Barangays the new area reaches for the first time are notified.
      </p>

      {error && <p className="db-error" role="alert">{error}</p>}

      {confirming ? (
        <div className="db-confirm">
          <p>Save the new area for this hazard?</p>
          <div className="db-btn-row">
            <button type="button" className="db-btn db-btn-primary" onClick={save} disabled={busy}>
              {busy ? 'Saving…' : 'Yes, save it'}
            </button>
            <button type="button" className="db-btn db-btn-outline" onClick={() => setConfirming(false)} disabled={busy}>
              Go back
            </button>
          </div>
        </div>
      ) : (
        <div className="db-btn-row">
          <button
            type="button"
            className="db-btn db-btn-primary"
            onClick={() => setConfirming(true)}
            disabled={!closed || !canUndo || busy}
            title={!canUndo ? 'Change the outline first' : undefined}
          >
            Save new area
          </button>
          <button type="button" className="db-btn db-btn-outline" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
