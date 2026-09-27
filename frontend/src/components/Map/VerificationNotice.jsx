import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { hazardsApi } from '../../api/hazardsApi';
import { verificationInfo } from './hazardInfo';

// Roles allowed by IsBarangayPersonnel on POST /api/hazards/<id>/verify/
const VERIFIER_ROLES = ['Barangay_Personnel', 'DRRMO_Officer', 'System_Admin'];

function formatDateTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-PH', {
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

// Shows whether barangay personnel have confirmed this zone, reminds the public
// that the map is a guide, and lets signed-in barangay staff confirm or dispute it.
export default function VerificationNotice({ item, onVerified }) {
  const auth = useAuth();
  const roleName = auth?.user?.role?.name || auth?.user?.role;
  const canVerify = !item.sample && VERIFIER_ROLES.includes(roleName);

  const [disputing, setDisputing] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Start fresh whenever a different hazard is opened
  useEffect(() => {
    setDisputing(false);
    setNote('');
    setError('');
  }, [item.id]);

  const status = item.verificationStatus || 'Pending';
  const v = verificationInfo(status);

  async function submit(verificationStatus) {
    setBusy(true);
    setError('');
    try {
      const feature = await hazardsApi.verify(item.id, {
        verification_status: verificationStatus,
        verification_note: verificationStatus === 'Disputed' ? note : '',
      });
      onVerified?.(feature);
      setDisputing(false);
      setNote('');
    } catch (err) {
      setError(err.data?.verification_note?.[0] || err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="pm-verify" style={{ background: v.tint, borderColor: v.color }}>
      <p className="pm-verify-status" style={{ color: v.text }}>
        <span className="pm-badge-dot" style={{ background: v.color }} />
        {v.label}
      </p>

      {status !== 'Pending' && item.verifiedAt && (
        <p className="pm-verify-meta">
          {item.verifiedByName || 'Barangay personnel'}, {formatDateTime(item.verifiedAt)}
        </p>
      )}

      {status === 'Disputed' && item.verificationNote && (
        <blockquote className="pm-verify-note">{item.verificationNote}</blockquote>
      )}

      <p className="pm-verify-disclaimer">
        This map is a guide. Zones are drawn from DRRMO data and conditions can change
        quickly, so always follow instructions from your barangay officials.
      </p>

      {canVerify && !disputing && (
        <div className="pm-verify-actions">
          <button
            type="button"
            className="pm-btn pm-btn-primary"
            disabled={busy}
            onClick={() => submit('Confirmed')}
          >
            {busy ? 'Saving…' : 'Confirm conditions'}
          </button>
          <button
            type="button"
            className="pm-btn pm-btn-outline"
            disabled={busy}
            onClick={() => setDisputing(true)}
          >
            Report different conditions
          </button>
        </div>
      )}

      {canVerify && disputing && (
        <div className="pm-verify-form">
          <label htmlFor={`pm-verify-note-${item.id}`}>What are conditions like on the ground?</label>
          <textarea
            id={`pm-verify-note-${item.id}`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Example: Water has receded along the main road, but the riverside purok is still flooded."
            maxLength={1000}
          />
          <div className="pm-verify-actions">
            <button
              type="button"
              className="pm-btn pm-btn-primary"
              disabled={busy || !note.trim()}
              onClick={() => submit('Disputed')}
            >
              {busy ? 'Sending…' : 'Send report'}
            </button>
            <button
              type="button"
              className="pm-btn pm-btn-outline"
              disabled={busy}
              onClick={() => setDisputing(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && <p className="pm-verify-error" role="alert">{error}</p>}
    </section>
  );
}