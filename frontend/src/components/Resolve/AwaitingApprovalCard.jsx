import React, { useCallback, useEffect, useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';
import RetractHazardForm from './RetractHazardForm';

// Matches the bell's polling, so a held alert shows up about as fast as the
// notification asking for approval.
const POLL_MS = 30000;

function timeOf(iso) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '';
}

function minutesLeft(iso, now) {
  if (!iso) return null;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - now) / 60000));
}

const LEVEL = { Green: 'Low', Orange: 'Moderate', Red: 'Extreme' };

/**
 * Refusing a held raise to Extreme: the zone stays live at its level, and
 * the officer who asked gets the reason.
 */
function RefuseRaiseForm({ zone, own, onCancel, onDone }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit() {
    setBusy(true);
    setError('');
    try {
      await hazardsApi.refuseRaise(zone.id, reason.trim());
      onDone();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="db-resolve">
      <h3>{own ? 'Withdraw your request' : 'Keep the current level'}</h3>
      <p className="db-hint">{zoneTitle(zone)}</p>
      <p className="db-callout">
        The hazard stays on the map as {LEVEL[zone.severity] || zone.severity}. No Extreme
        alert is sent{own ? '.' : ', and the officer who asked is told why.'}
      </p>
      <label className="db-field" htmlFor="db-rr-reason">
        Why? (required)
        <textarea
          id="db-rr-reason"
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Water is going down; Moderate still fits"
        />
      </label>
      {error && <p className="db-error" role="alert">{error}</p>}
      <div className="db-btn-row">
        <button type="button" className="db-btn db-btn-primary" onClick={submit} disabled={busy || reason.trim().length < 5}>
          {busy ? 'Saving…' : own ? 'Withdraw request' : `Keep it ${LEVEL[zone.severity] || ''}`.trim()}
        </button>
        <button type="button" className="db-btn db-btn-outline" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function zoneTitle(z) {
  const type = z.hazard_type?.name || 'Hazard';
  const where = (z.affected_barangays || []).join(', ') || z.barangay_name || 'Talisay City';
  return `${type} · ${where}`;
}

/**
 * Extreme alerts waiting for a second DRRMO officer. Renders nothing when
 * there are none, so it only takes space on the dashboard when someone is
 * waiting on an answer.
 *
 * Another officer approves (the alert goes out) or refuses with a reason
 * (it never goes out, and the publisher is told why). The officer who
 * published it can only wait or withdraw their own. If nobody answers, the
 * server sends it on its own when the countdown runs out.
 *
 * Props:
 *   onChanged()  optional — after an approval or refusal, so the dashboard
 *                can refresh its own counters
 */
export default function AwaitingApprovalCard({ onChanged }) {
  const [zones, setZones] = useState([]);
  const [now, setNow] = useState(Date.now());
  const [approving, setApproving] = useState(null); // zone id awaiting "Yes, send it"
  const [refusing, setRefusing] = useState(null);   // zone being refused
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await hazardsApi.awaiting();
      setZones(res.results || []);
    } catch {
      // Keep what we had; the next poll tries again
    }
    setNow(Date.now());
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  // Keep the countdown honest between polls
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(id);
  }, []);

  async function approve(zone) {
    setBusy(true);
    setError('');
    try {
      const res = await hazardsApi.approve(zone.id);
      const sent = res.alert?.recipients_notified ?? 0;
      setDone(zone.kind === 'raise'
        ? `Raised to Extreme and sent to ${sent} accounts.`
        : `Approved and sent to ${sent} accounts.`);
      setApproving(null);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message);
      setApproving(null);
      await load(); // it may have gone out on its own meanwhile
    } finally {
      setBusy(false);
    }
  }

  function handleRefused() {
    const wasRaise = refusing?.kind === 'raise';
    setRefusing(null);
    setDone(wasRaise
      ? 'Not raised. It stays on the map at its current level.'
      : 'Not sent. The officer who published it has been told why.');
    load();
    onChanged?.();
  }

  if (zones.length === 0 && !done) return null;

  return (
    <div className="db-card db-awaiting">
      <h2>Waiting for your approval</h2>
      <p className="db-card-sub">
        New Extreme alerts, and raising a live hazard to Extreme, need a
        second officer. If nobody answers, each one goes ahead on its own
        when its time runs out.
      </p>

      {done && <p className="db-success" role="status">{done}</p>}
      {error && <p className="db-error" role="alert">{error}</p>}

      {zones.length === 0 ? (
        <p className="db-empty">Nothing is waiting for approval.</p>
      ) : (
        <div className="db-list">
          {zones.map((z) => {
            const left = minutesLeft(z.approval_due_at, now);
            const isRaise = z.kind === 'raise';
            return (
              <div key={z.id} className="db-item">
                <div className="db-item-head">
                  <span className="db-item-title">{zoneTitle(z)}</span>
                  <div className="db-btn-row">
                    {z.can_approve ? (
                      approving === z.id ? (
                        <>
                          <button
                            type="button"
                            className="db-btn db-btn-primary db-btn-sm"
                            onClick={() => approve(z)}
                            disabled={busy}
                          >
                            {busy ? 'Sending…' : 'Yes, send it'}
                          </button>
                          <button
                            type="button"
                            className="db-btn db-btn-outline db-btn-sm"
                            onClick={() => setApproving(null)}
                            disabled={busy}
                          >
                            Go back
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="db-btn db-btn-primary db-btn-sm"
                            onClick={() => { setDone(''); setError(''); setApproving(z.id); }}
                          >
                            {isRaise ? 'Approve raise' : 'Approve and send'}
                          </button>
                          <button
                            type="button"
                            className="db-btn db-btn-outline db-btn-sm"
                            onClick={() => { setDone(''); setError(''); setRefusing(z); }}
                          >
                            {isRaise ? 'Keep current level' : <>Don&apos;t send</>}
                          </button>
                        </>
                      )
                    ) : (
                      <button
                        type="button"
                        className="db-btn db-btn-outline db-btn-sm"
                        onClick={() => { setDone(''); setError(''); setRefusing(z); }}
                        title="You published this one, so another officer has to approve it"
                      >
                        {isRaise ? 'Withdraw my request' : 'Withdraw mine'}
                      </button>
                    )}
                  </div>
                </div>
                <div className="db-item-meta">
                  {isRaise ? (
                    <>
                      <span className="db-chip db-chip-danger">Raise to Extreme</span>
                      {' '}Now {LEVEL[z.severity] || z.severity}, asked {timeOf(z.requested_at)}
                      {z.requested_by_name ? ` by ${z.requested_by_name}` : ''}
                    </>
                  ) : (
                    <>
                      <span className="db-chip db-chip-danger">Extreme</span>
                      {' '}Published {timeOf(z.activated_at)}
                      {z.published_by_name ? ` by ${z.published_by_name}` : ''}
                    </>
                  )}
                  {' · '}
                  <strong>
                    {left > 0
                      ? `${isRaise ? 'Raised' : 'Goes out'} on its own at ${timeOf(z.approval_due_at)} (${left} min)`
                      : isRaise ? 'Being raised now' : 'Going out now'}
                  </strong>
                </div>
                {z.description && <p className="db-hint" style={{ marginTop: 6 }}>{z.description}</p>}
                {!z.can_approve && (
                  <p className="db-hint" style={{ marginTop: 6 }}>
                    {isRaise
                      ? 'You asked for this raise, so another officer has to approve it.'
                      : 'You published this one, so another officer has to approve it.'}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {refusing && (
        <div
          className="db-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Don't send this alert"
          onClick={(e) => { if (e.target === e.currentTarget) setRefusing(null); }}
        >
          <div className="db-modal">
            {refusing.kind === 'raise' ? (
              <RefuseRaiseForm
                zone={refusing}
                own={!refusing.can_approve}
                onCancel={() => setRefusing(null)}
                onDone={handleRefused}
              />
            ) : (
              <RetractHazardForm
                held
                zoneId={refusing.id}
                title={zoneTitle(refusing)}
                onCancel={() => setRefusing(null)}
                onRetracted={handleRefused}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
