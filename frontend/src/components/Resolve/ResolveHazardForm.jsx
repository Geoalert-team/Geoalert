import React, { useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';

/**
 * The form DRRMO fills in when a hazard is over. Used in two places —
 * inside the map's hazard panel and inside the DRRMO dashboard — so it
 * styles itself entirely with db- classes from Dashboard.css and brings
 * no stylesheet of its own. Outside a .db page, wrap it in .db-scope so
 * the tokens resolve.
 *
 * Props:
 *   zoneId            hazard zone UUID
 *   title             what's being resolved, e.g. "Flood · Tabunok"
 *   onCancel()        close without doing anything
 *   onResolved(zone)  called with the updated zone after a successful PATCH
 */
export default function ResolveHazardForm({ zoneId, title, onCancel, onResolved }) {
  const [summary, setSummary] = useState('');
  const [casualties, setCasualties] = useState('');
  const [displaced, setDisplaced] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Blank is deliberately allowed and stored as "not recorded" rather than
  // 0 — an uncounted incident shouldn't read as a casualty-free one.
  function validate() {
    for (const [label, value] of [['Casualties', casualties], ['People displaced', displaced]]) {
      if (value === '') continue;
      const n = Number(value);
      if (!Number.isInteger(n) || n < 0) return `${label} must be a whole number of 0 or more.`;
    }
    return '';
  }

  async function submit() {
    const problem = validate();
    if (problem) {
      setError(problem);
      setConfirming(false);
      return;
    }

    setBusy(true);
    setError('');
    try {
      const zone = await hazardsApi.update(zoneId, {
        status: 'Resolved',
        summary: summary.trim(),
        total_casualties: casualties,
        total_displaced: displaced,
      });
      onResolved?.(zone);
    } catch (err) {
      // axiosClient's response interceptor already flattens the server's
      // error/detail into err.message — there is no err.response here.
      setError(err?.message || 'Could not resolve this hazard. Check your connection and try again.');
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="db-resolve">
      <h3>Resolve and archive</h3>
      {title && <p className="db-hint">{title}</p>}

      <p className="db-callout">
        This removes the zone from the public map and files it as a historical
        record, so it still counts in reports and trend analysis.
      </p>

      <label className="db-field" htmlFor="db-rz-summary">
        What happened? (archived with the record)
        <textarea
          id="db-rz-summary"
          rows={3}
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="How it developed, what response was carried out, when it cleared"
        />
      </label>

      <div className="db-field-row">
        <label className="db-field" htmlFor="db-rz-casualties">
          Casualties
          <input
            id="db-rz-casualties"
            type="number"
            min="0"
            step="1"
            inputMode="numeric"
            value={casualties}
            onChange={(e) => setCasualties(e.target.value)}
            placeholder="—"
          />
        </label>
        <label className="db-field" htmlFor="db-rz-displaced">
          People displaced
          <input
            id="db-rz-displaced"
            type="number"
            min="0"
            step="1"
            inputMode="numeric"
            value={displaced}
            onChange={(e) => setDisplaced(e.target.value)}
            placeholder="—"
          />
        </label>
      </div>

      <p className="db-hint">
        Leave a box empty if the count isn't in yet — empty is recorded as
        "not counted", which is not the same as zero.
      </p>

      {error && <p className="db-error" role="alert">{error}</p>}

      {confirming ? (
        <div className="db-confirm">
          <p>Resolve this hazard? The public map will stop showing it.</p>
          <div className="db-btn-row">
            <button type="button" className="db-btn db-btn-primary" onClick={submit} disabled={busy}>
              {busy ? 'Resolving…' : 'Yes, resolve it'}
            </button>
            <button type="button" className="db-btn db-btn-outline" onClick={() => setConfirming(false)} disabled={busy}>
              Go back
            </button>
          </div>
        </div>
      ) : (
        <div className="db-btn-row">
          <button type="button" className="db-btn db-btn-primary" onClick={() => setConfirming(true)} disabled={busy}>
            Resolve and archive
          </button>
          {onCancel && (
            <button type="button" className="db-btn db-btn-outline" onClick={onCancel} disabled={busy}>
              Cancel
            </button>
          )}
        </div>
      )}
    </div>
  );
}