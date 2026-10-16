import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { hazardsApi } from '../../api/hazardsApi';

/**
 * Ground confirmation, where the barangay actually works.
 *
 * A hazard zone is drawn in the DRRMO office, often from a forecast or a
 * phoned-in report. Nobody has necessarily been out to look. This card pushes
 * the open ones at the barangay rather than making anyone hunt for them on
 * the map, and records what they found.
 *
 * Styled with db- classes, so it must sit inside .db or .db-scope.
 *
 * Props:
 *   onAnswered(zone)  optional, called after a successful confirm or dispute
 */

const SEVERITY = {
  Red:    { label: 'Extreme risk',  tone: 'db-badge-high' },
  Orange: { label: 'Moderate risk', tone: 'db-badge-medium' },
  Green:  { label: 'Low risk',      tone: 'db-badge-low' },
};

const ANSWERED = {
  Confirmed: { label: 'You confirmed this', tone: 'db-badge-validated' },
  Disputed:  { label: 'You disputed this',  tone: 'db-badge-rejected' },
};

function formatWhen(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleString('en-PH', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

function hazardName(zone) {
  return zone.hazard_type?.name || zone.hazard_type_name || 'Hazard';
}

export default function ConfirmHazardCard({ onAnswered }) {
  const [zones, setZones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  // Which zone is being answered, and how: { id, status }
  const [answering, setAnswering] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    return hazardsApi.forBarangay()
      .then((data) => {
        setZones(data?.results || []);
        setFailed(false);
      })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  function start(zone, status) {
    setAnswering({ id: zone.id, status });
    setNote('');
    setError('');
  }

  function cancel() {
    setAnswering(null);
    setNote('');
    setError('');
  }

  async function submit() {
    if (!answering) return;
    setBusy(true);
    setError('');
    try {
      const updated = await hazardsApi.verify(answering.id, {
        status: answering.status,
        note: note.trim(),
      });
      setZones((prev) => prev.map((z) => (z.id === updated.id ? updated : z)));
      cancel();
      onAnswered?.(updated);
    } catch (err) {
      // axiosClient flattens the server's error into err.message — there is
      // no err.response to read here.
      setError(err?.message || 'Could not save that. Check your connection and try again.');
    } finally {
      setBusy(false);
    }
  }

  const pending = zones.filter((z) => (z.verification_status || 'Pending') === 'Pending');
  const answered = zones.filter((z) => (z.verification_status || 'Pending') !== 'Pending');

  return (
    <div className="db-card">
      <div className="db-item-head">
        <div>
          <h2>Hazards in your barangay</h2>
          <p className="db-card-sub" style={{ marginBottom: 0 }}>
            DRRMO publishes these from the office. You are the one who can say
            whether they are really there.
          </p>
        </div>
        {!loading && (
          <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={load}>
            Refresh
          </button>
        )}
      </div>

      {loading && <p className="db-empty">Loading…</p>}

      {!loading && failed && (
        <>
          <p className="db-error" role="alert">
            Could not load the hazards for your barangay right now.
          </p>
          <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={load}>
            Try again
          </button>
        </>
      )}

      {!loading && !failed && zones.length === 0 && (
        <p className="db-empty">
          No active hazards in your barangay. Nothing needs confirming.
        </p>
      )}

      {!loading && !failed && zones.length > 0 && (
        <>
          {pending.length > 0 && (
            <p className="db-callout">
              <strong>
                {pending.length === 1
                  ? 'One hazard is waiting for your confirmation.'
                  : `${pending.length} hazards are waiting for your confirmation.`}
              </strong>{' '}
              Say what you can see on the ground. If it is not there as described,
              dispute it — that is as useful as confirming.
            </p>
          )}

          <div className="db-list">
            {[...pending, ...answered].map((zone) => {
              const sev = SEVERITY[zone.severity] || { label: zone.severity, tone: '' };
              const state = ANSWERED[zone.verification_status];
              const isAnswering = answering?.id === zone.id;

              return (
                <div key={zone.id} className="db-item">
                  <div className="db-item-head">
                    <span className="db-item-title">
                      {hazardName(zone)}
                      {zone.barangay_name ? ` · ${zone.barangay_name}` : ''}
                      {zone.is_sample && (
                        <span className="db-badge" style={{ marginLeft: 8 }}>Sample</span>
                      )}
                    </span>
                    <span className={`db-badge ${sev.tone}`}>{sev.label}</span>
                  </div>

                  {zone.description && (
                    <div className="db-item-meta">{zone.description}</div>
                  )}
                  <div className="db-item-meta">
                    Active since {formatWhen(zone.activated_at) || 'not recorded'}
                  </div>

                  {state && (
                    <div style={{ marginTop: 8 }}>
                      <span className={`db-badge ${state.tone}`}>{state.label}</span>
                      {zone.verification_note && (
                        <p className="db-item-meta" style={{ marginTop: 6 }}>
                          “{zone.verification_note}”
                        </p>
                      )}
                      <p className="db-hint">
                        {zone.verified_by_name || 'Recorded'}
                        {zone.verified_at ? ` · ${formatWhen(zone.verified_at)}` : ''}
                      </p>
                    </div>
                  )}

                  {isAnswering ? (
                    <div className="db-confirm" style={{ marginTop: 10 }}>
                      <p>
                        {answering.status === 'Confirmed'
                          ? 'Confirm that this hazard is on the ground as described?'
                          : 'Report that this hazard is not there as described?'}
                      </p>
                      <label className="db-field" htmlFor={`cf-note-${zone.id}`}>
                        What did you see? (optional)
                        <textarea
                          id={`cf-note-${zone.id}`}
                          rows={2}
                          value={note}
                          onChange={(e) => setNote(e.target.value)}
                          placeholder={answering.status === 'Confirmed'
                            ? 'Water about knee deep along the national road'
                            : 'Road is clear, no flooding seen as of this morning'}
                        />
                      </label>
                      {error && <p className="db-error" role="alert">{error}</p>}
                      <div className="db-btn-row">
                        <button
                          type="button"
                          className="db-btn db-btn-primary db-btn-sm"
                          onClick={submit}
                          disabled={busy}
                        >
                          {busy
                            ? 'Saving…'
                            : answering.status === 'Confirmed' ? 'Yes, confirm' : 'Yes, dispute'}
                        </button>
                        <button
                          type="button"
                          className="db-btn db-btn-outline db-btn-sm"
                          onClick={cancel}
                          disabled={busy}
                        >
                          Go back
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="db-btn-row" style={{ marginTop: 10 }}>
                      <button
                        type="button"
                        className="db-btn db-btn-outline db-btn-sm"
                        onClick={() => start(zone, 'Confirmed')}
                      >
                        {state ? 'Change to confirmed' : 'Confirm it is there'}
                      </button>
                      <button
                        type="button"
                        className="db-btn db-btn-outline db-btn-sm"
                        onClick={() => start(zone, 'Disputed')}
                      >
                        {state ? 'Change to disputed' : 'Dispute'}
                      </button>
                      <Link
                        className="db-btn db-btn-outline db-btn-sm"
                        to={`/map?zone=${zone.id}`}
                      >
                        See on the map
                      </Link>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}