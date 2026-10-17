import React, { useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';

/**
 * The form DRRMO fills in when a hazard zone was published by mistake —
 * wrong barangay, wrong shape, a duplicate, a drill that went out live.
 *
 * Deliberately a separate action from ResolveHazardForm, which sits beside
 * it. Resolving means the hazard happened and is over, and it files a
 * historical record that then counts in the reports and the trend charts.
 * A zone nobody meant to publish never happened, so resolving it would
 * invent an incident in Talisay City.
 *
 * Styles itself with db- classes from Dashboard.css and brings no
 * stylesheet of its own; outside a .db page, wrap it in .db-scope.
 *
 * Props:
 *   zoneId             hazard zone UUID
 *   title              what's being withdrawn, e.g. "Flood · Tabunok"
 *   onCancel()         close without doing anything
 *   onRetracted(zone)  called with the updated zone after a successful POST
 *   held               true for an Extreme alert still waiting for approval:
 *                      nothing went out yet, so this is refusing to send it
 */

// Matches HazardZoneRetractView.MIN_REASON
const MIN_REASON = 5;

export default function RetractHazardForm({ zoneId, title, onCancel, onRetracted, held = false }) {
  const [reason, setReason] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const trimmed = reason.trim();
  const ready = trimmed.length >= MIN_REASON;

  async function submit() {
    setBusy(true);
    setError('');
    try {
      const zone = await hazardsApi.retract(zoneId, trimmed);
      onRetracted?.(zone);
    } catch (err) {
      // axiosClient's response interceptor flattens the server's error into
      // err.message — there is no err.response here.
      setError(err?.message || 'Could not withdraw this hazard. Check your connection and try again.');
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="db-resolve">
      <h3>{held ? "Don't send this alert" : 'Withdraw this hazard'}</h3>
      {title && <p className="db-hint">{title}</p>}

      {held ? (
        <p className="db-callout">
          This Extreme alert hasn&apos;t gone out yet, so nobody else is told.
          The officer who published it gets your reason, and it stays on the
          record as withdrawn.
        </p>
      ) : (
        <p className="db-callout">
          For a hazard published in error. This takes the zone off the public map
          and files <strong>no</strong> historical record, so it is never counted
          as an incident that happened. The alert that already went out stays on
          the record, and everyone who received it is told it was withdrawn.
        </p>
      )}

      <label className="db-field" htmlFor="db-rt-reason">
        {held ? "Why shouldn't it be sent? (required)" : 'Why is it being withdrawn? (required)'}
        <textarea
          id="db-rt-reason"
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Drawn over the wrong barangay — meant Lawaan III, not Tabunok"
        />
      </label>

      <p className="db-hint">
        {held
          ? 'This reason is kept permanently with the zone, written to the activity log, and sent to the officer who published it.'
          : 'This reason is kept permanently with the zone, written to the activity log, and included in the withdrawal notice sent to recipients.'}
      </p>

      {error && <p className="db-error" role="alert">{error}</p>}

      {confirming ? (
        <div className="db-confirm">
          <p>
            {held
              ? "Stop this alert? It won't be sent, and it cannot be undone. If the hazard is real, it has to be published again."
              : 'Withdraw this hazard? It cannot be undone — if the hazard turns out to be real, publish it again as a new zone.'}
          </p>
          <div className="db-btn-row">
            <button type="button" className="db-btn db-btn-primary" onClick={submit} disabled={busy}>
              {busy ? 'Withdrawing…' : held ? "Yes, don't send it" : 'Yes, withdraw it'}
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
            disabled={busy || !ready}
            title={ready ? undefined : 'Type a reason first'}
          >
            {held ? "Don't send" : 'Withdraw as published in error'}
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
