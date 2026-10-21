import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { authApi } from '../api/authApi';
import logo from '../assets/images/logo1.png';
import './css/Login.css';

const BAD_LINK = 'This link has expired or was already used.';
const DONE = 'Password changed. Log in with your new password.';

/**
 * Choose a new password from an emailed reset link
 * (/reset-password/:uid/:token). The link is checked first, so an expired
 * or used one says so before anything is typed. Saving does not sign the
 * person in: they log in next, 2FA included.
 */
export default function ResetPassword() {
  const { uid, token } = useParams();
  const [stage, setStage] = useState('checking'); // checking | invalid | form | done
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    authApi.checkResetLink(uid, token)
      .then((d) => { if (!cancelled) setStage(d?.valid ? 'form' : 'invalid'); })
      .catch(() => { if (!cancelled) setStage('invalid'); }); // a link that can't be checked can't be used
    return () => { cancelled = true; };
  }, [uid, token]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (password !== confirm) {
      setError("The passwords don't match.");
      return;
    }
    setBusy(true);
    setError('');
    try {
      await authApi.confirmPasswordReset(uid, token, password);
      setStage('done');
    } catch (err) {
      if (err?.message === BAD_LINK) setStage('invalid'); // expired while the form was open
      else setError(err?.message || 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lg">
      <Link to="/login" className="lg-back">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
        Back to log in
      </Link>

      <main className="lg-card">
        <div className="lg-brand">
          <span className="lg-logo"><img src={logo} alt="" /></span>
          <span className="lg-brand-name">GeoAlert</span>
        </div>

        <div className="lg-head">
          <h1>Choose a new password</h1>
          {stage === 'form' && <p>Pick a password you don't use anywhere else.</p>}
        </div>

        {stage === 'checking' && <p className="lg-note">Checking your link…</p>}

        {stage === 'invalid' && (
          <>
            <p className="lg-error" role="alert">{BAD_LINK}</p>
            <Link to="/forgot-password" className="lg-submit lg-submit-link">Send a new link</Link>
          </>
        )}

        {stage === 'done' && (
          <>
            <p className="lg-done" role="status">{DONE}</p>
            <Link to="/login" className="lg-submit lg-submit-link">Log in</Link>
          </>
        )}

        {stage === 'form' && (
          <form onSubmit={handleSubmit}>
            <div className="lg-field">
              <label htmlFor="new-password">New password</label>
              <div className="lg-password">
                <input
                  id="new-password"
                  type={show ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
                <button type="button" className="lg-show" aria-pressed={show} onClick={() => setShow((s) => !s)}>
                  {show ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>

            <div className="lg-field">
              <label htmlFor="confirm-password">Confirm new password</label>
              <input
                id="confirm-password"
                type={show ? 'text' : 'password'}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            {error && <p className="lg-error" role="alert">{error}</p>}

            <button type="submit" className="lg-submit" disabled={busy}>
              {busy ? 'Saving…' : 'Save new password'}
            </button>
          </form>
        )}
      </main>
    </div>
  );
}
